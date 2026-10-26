"""Approval-stage edge audit. Isolated DB/storage; expected failures document defects."""
import asyncio
from datetime import datetime, timedelta
import httpx
import pytest
import pytest_asyncio
from bson import ObjectId
from test_role_security_local import ctx, auth, invitation, upload_id, server, guest_ids

@pytest_asyncio.fixture(autouse=True)
async def audit_context(ctx):
    await ctx['db'].bookings.update_many({}, {'$set': {'ota':'Direct','ota_commission':0}})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app, raise_app_exceptions=False), base_url='http://test') as client:
        ctx['client'] = client
        yield

@pytest.mark.asyncio
@pytest.mark.parametrize('path', ['/properties','/bookings','/cleaning','/users','/guest-ids','/payouts','/owner/dashboard','/dashboard'])
async def test_unauthenticated_access_denied(ctx,path):
    assert (await ctx['client'].get('/api'+path)).status_code == 401

@pytest.mark.asyncio
@pytest.mark.parametrize('path', ['/properties/bad','/bookings/bad','/cleaning/bad','/invoices/bad'])
async def test_invalid_ids_return_helpful_4xx(ctx,path):
    r=await ctx['client'].get('/api'+path,headers=auth(ctx))
    assert r.status_code == 404 and isinstance(r.json()['detail'],str)

@pytest.mark.asyncio
@pytest.mark.parametrize('month',['2026-00','2026-13','wrong','2026-02-01'])
@pytest.mark.parametrize('endpoint',['calendar','reports/settlement'])
async def test_invalid_month_is_validation_error_not_crash(ctx,month,endpoint):
    r=await ctx['client'].get(f'/api/{endpoint}',params={'month':month,'property_id':ctx['p1']},headers=auth(ctx,'owner'))
    assert 400 <= r.status_code < 500, f'{endpoint}: {month} returned {r.status_code}'
    assert isinstance(r.json().get('detail'),str)

@pytest.mark.asyncio
@pytest.mark.parametrize('field,value',[('amount',-1),('month','2026-13'),('property_id','not-a-property')])
async def test_expense_rejects_invalid_data(ctx,field,value):
    body={'property_id':ctx['p1'],'month':'2026-10','amount':100,field:value}
    r=await ctx['client'].post('/api/expenses',headers=auth(ctx),json=body)
    assert 400 <= r.status_code < 500, f'Invalid {field} accepted: {r.status_code}'

@pytest.mark.asyncio
@pytest.mark.parametrize('field,value',[('tax_percent',-1),('discount',-1),('issue_date','not-a-date'),('property_id','not-a-property')])
async def test_invoice_rejects_invalid_data(ctx,field,value):
    body={'type':'guest','bill_to_name':'Sample','items':[{'description':'Stay','qty':1,'rate':100}],'issue_date':'2026-10-16',field:value}
    r=await ctx['client'].post('/api/invoices',headers=auth(ctx),json=body)
    assert 400 <= r.status_code < 500, f'Invalid {field} accepted: {r.status_code}'

@pytest.mark.asyncio
@pytest.mark.parametrize('item',[{'description':'Stay','qty':-1,'rate':100},{'description':'Stay','qty':1,'rate':-100}])
async def test_invoice_rejects_negative_lines(ctx,item):
    r=await ctx['client'].post('/api/invoices',headers=auth(ctx),json={'type':'guest','bill_to_name':'Sample','items':[item],'issue_date':'2026-10-16'})
    assert 400 <= r.status_code < 500

@pytest.mark.asyncio
async def test_booking_back_to_back_dates_allowed_and_overlap_rejected(ctx):
    b=await ctx['db'].bookings.find_one({'_id':ObjectId(ctx['bid'])})
    body={'property_id':ctx['p1'],'guest_name':'Next guest','check_in':b['check_out'],'check_out':(datetime.fromisoformat(b['check_out'])+timedelta(days=1)).date().isoformat()}
    assert (await ctx['client'].post('/api/bookings',headers=auth(ctx),json=body)).status_code == 200
    body.update(check_in=b['check_in'],check_out=b['check_out'])
    assert (await ctx['client'].post('/api/bookings',headers=auth(ctx),json=body)).status_code == 409

@pytest.mark.asyncio
async def test_booking_reactivation_creates_cleaning(ctx):
    today=datetime.now(guest_ids.INDIA_TZ).date()+timedelta(days=10)
    body={'property_id':ctx['p1'],'guest_name':'Reactivated guest','check_in':today.isoformat(),'check_out':(today+timedelta(days=2)).isoformat(),'status':'cancelled'}
    created=(await ctx['client'].post('/api/bookings',headers=auth(ctx),json=body)).json()
    body['status']='confirmed'
    assert (await ctx['client'].put('/api/bookings/'+created['id'],headers=auth(ctx),json=body)).status_code == 200
    assert await ctx['db'].cleaning.count_documents({'booking_id':created['id']}) == 1, 'Confirmed booking has no cleaning task'

@pytest.mark.asyncio
async def test_new_assignment_removes_old_cleaner_access_immediately(ctx):
    uid=ctx['users']['other_cleaner']['_id']
    await ctx['db'].users.update_one({'_id':uid},{'$set':{'property_ids':[ctx['p1']]}})
    await ctx['client'].put('/api/cleaning/'+ctx['cid'],headers=auth(ctx,'supervisor'),json={'assigned_to':str(uid)})
    assert (await ctx['client'].get('/api/cleaning/'+ctx['cid'],headers=auth(ctx,'cleaner'))).status_code == 404
    assert (await ctx['client'].get('/api/cleaning/'+ctx['cid'],headers=auth(ctx,'other_cleaner'))).status_code == 200

@pytest.mark.asyncio
async def test_password_reset_invalidates_old_login_token(ctx):
    old=auth(ctx,'cleaner')
    r=await ctx['client'].post('/api/users/'+str(ctx['users']['cleaner']['_id'])+'/reset-password',headers=auth(ctx))
    assert r.status_code == 200
    assert (await ctx['client'].get('/api/auth/me',headers=old)).status_code == 401, 'Old session remains usable after password reset'

@pytest.mark.asyncio
async def test_expired_retention_allows_replacement_id(ctx):
    invite=await invitation(ctx)
    did=(await upload_id(ctx,invite)).json()['id']
    await ctx['db'].guest_ids.update_one({'_id':ObjectId(did)},{'$set':{'delete_after':'2000-01-01'}})
    assert (await ctx['client'].get('/api/guest/check-in',headers=invite)).json()['documents'] == []
    r=await upload_id(ctx,invite)
    assert r.status_code == 200, f'Expired invisible ID prevents replacement: {r.status_code}'

@pytest.mark.asyncio
async def test_rejected_id_undo_does_not_replace_newer_active_submission(ctx):
    invite=await invitation(ctx)
    first=(await upload_id(ctx,invite)).json()['id']
    await ctx['client'].post('/api/guest-ids/'+first+'/review',headers=auth(ctx),json={'status':'rejected','reason':'Unreadable'})
    assert (await upload_id(ctx,invite)).status_code == 200
    r=await ctx['client'].post('/api/bookings/'+ctx['bid']+'/guest-admin-action',headers=auth(ctx),json={'action':'reset_id','document_id':first,'note':'Correction'})
    assert r.status_code == 409

@pytest.mark.asyncio
async def test_partial_upload_rejects_non_image_media(ctx,monkeypatch):
    monkeypatch.setattr(server,'put_object',lambda path,data,ctype:{'path':path,'size':len(data)})
    r=await ctx['client'].post('/api/upload',headers=auth(ctx,'cleaner'),files={'file':('fake.jpg',b'<script>test</script>','text/html')})
    assert r.status_code in (415,422), 'Non-image content accepted as a cleaning image'

@pytest.mark.asyncio
async def test_owner_empty_assignments_is_not_an_error(ctx):
    await ctx['db'].users.update_one({'_id':ctx['users']['owner']['_id']},{'$set':{'property_ids':[]}})
    r=await ctx['client'].get('/api/owner/dashboard',headers=auth(ctx,'owner'))
    assert r.status_code == 200 and r.json()['villas'] == []

@pytest.mark.asyncio
async def test_storage_outage_returns_structured_error(ctx,monkeypatch):
    def failed(*args): raise RuntimeError('simulated storage outage')
    monkeypatch.setattr(guest_ids,'read_image',failed)
    did=(await upload_id(ctx,await invitation(ctx))).json()['id']
    r=await ctx['client'].get('/api/guest-ids/'+did+'/image',headers=auth(ctx))
    assert r.status_code == 503 and 'detail' in r.json(), f'Storage outage returned {r.status_code} {r.headers.get("content-type")}'

@pytest.mark.asyncio
async def test_double_tap_admin_reassign_is_idempotent(ctx):
    url='/api/cleaning/'+ctx['cid']+'/admin-action'
    body={'action':'reopen','note':'Duplicate tap test'}
    for _ in range(2): assert (await ctx['client'].post(url,headers=auth(ctx),json=body)).status_code == 200
    c=await ctx['db'].cleaning.find_one({'_id':ObjectId(ctx['cid'])})
    assert len(c['admin_history']) == 1, 'Same action executed twice without a request key'

@pytest.mark.asyncio
@pytest.mark.parametrize('role',['owner','cleaner','supervisor'])
@pytest.mark.parametrize('endpoint',['properties','bookings','users','expenses','invoices','owner-reports','payouts'])
async def test_non_admin_cannot_create_admin_records(ctx,role,endpoint):
    r=await ctx['client'].post('/api/'+endpoint,headers=auth(ctx,role),json={})
    assert r.status_code == 403

@pytest.mark.asyncio
async def test_owner_report_and_dashboard_are_scoped(ctx):
    month=datetime.now(guest_ids.INDIA_TZ).date().isoformat()[:7]
    r=await ctx['client'].get('/api/owner/dashboard',headers=auth(ctx,'owner'))
    assert r.status_code == 200 and [v['id'] for v in r.json()['villas']] == [ctx['p1']]
    r=await ctx['client'].get('/api/reports/settlement',params={'property_id':ctx['p1'],'month':month},headers=auth(ctx,'owner'))
    assert r.status_code == 200 and r.json()['gross'] == 1000 and r.json()['owner_payout'] == 700
    assert (await ctx['client'].get('/api/reports/settlement',params={'property_id':ctx['p2'],'month':month},headers=auth(ctx,'owner'))).status_code == 404

@pytest.mark.asyncio
async def test_supervisor_sees_only_eligible_team_and_cleanings(ctx):
    r=await ctx['client'].get('/api/cleaning-team',headers=auth(ctx,'supervisor'))
    assert r.status_code == 200 and [u['id'] for u in r.json()] == [str(ctx['users']['cleaner']['_id'])]
    r=await ctx['client'].get('/api/cleaning',headers=auth(ctx,'supervisor'))
    assert r.status_code == 200 and [c['id'] for c in r.json()] == [ctx['cid']]

@pytest.mark.asyncio
async def test_booking_changed_to_cancelled_not_left_in_cleaner_todo(ctx):
    b=await ctx['db'].bookings.find_one({'_id':ObjectId(ctx['bid'])})
    await ctx['db'].cleaning.update_one({'_id':ObjectId(ctx['cid'])},{'$set':{'booking_id':ctx['bid']}})
    body={k:b[k] for k in ('property_id','guest_name','guests','check_in','check_out','amount','ota')}
    body['status']='cancelled'
    assert (await ctx['client'].put('/api/bookings/'+ctx['bid'],headers=auth(ctx),json=body)).status_code == 200
    r=await ctx['client'].get('/api/cleaning?status=open',headers=auth(ctx,'cleaner'))
    assert r.json() == [], 'Cancelled stay still instructs cleaner to do checkout cleaning'

@pytest.mark.asyncio
async def test_concurrent_overlapping_bookings_are_not_both_accepted(ctx,monkeypatch):
    original=server.check_overlap
    barrier=asyncio.Event()
    reads=0
    async def racing_check(body,exclude=None):
        nonlocal reads
        await original(body,exclude)
        reads+=1
        if reads==2: barrier.set()
        await asyncio.wait_for(barrier.wait(),timeout=3)
    monkeypatch.setattr(server,'check_overlap',racing_check)
    today=datetime.now(guest_ids.INDIA_TZ).date()+timedelta(days=10)
    body={'property_id':ctx['p1'],'guest_name':'Concurrent guest','check_in':today.isoformat(),'check_out':(today+timedelta(days=2)).isoformat()}
    results=await asyncio.gather(*(ctx['client'].post('/api/bookings',headers=auth(ctx),json=body) for _ in range(2)))
    assert sorted(r.status_code for r in results) == [200,409], f'Concurrent booking responses: {[r.status_code for r in results]}'

@pytest.mark.asyncio
async def test_cross_month_occupancy_counts_nights_in_each_month(ctx):
    await ctx['db'].bookings.update_one({'_id':ObjectId(ctx['bid'])},{'$set':{'check_in':'2026-01-31','check_out':'2026-02-02'}})
    for month in ('2026-01','2026-02'):
        r=await ctx['client'].get('/api/reports/settlement',params={'property_id':ctx['p1'],'month':month},headers=auth(ctx,'owner'))
        assert r.status_code==200 and r.json()['nights']==1, f'{month}: expected 1 occupied night, got {r.json().get("nights")}'

@pytest.mark.asyncio
@pytest.mark.parametrize('paid_on',['not-a-date','2026-02-30'])
async def test_payout_date_is_validated(ctx,paid_on):
    month=datetime.now(guest_ids.INDIA_TZ).date().isoformat()[:7]
    r=await ctx['client'].post('/api/payouts',headers=auth(ctx),json={'property_id':ctx['p1'],'month':month,'amount':700,'paid_on':paid_on})
    assert 400<=r.status_code<500, f'Invalid payout date accepted: {r.status_code}'

@pytest.mark.asyncio
async def test_service_issue_is_private_and_recovers(ctx,monkeypatch):
    did=(await upload_id(ctx,await invitation(ctx))).json()['id']
    original=guest_ids.read_image
    def unavailable(doc): raise RuntimeError('do-not-record-sensitive-detail')
    monkeypatch.setattr(guest_ids,'read_image',unavailable)
    r=await ctx['client'].get('/api/guest-ids/'+did+'/image',headers=auth(ctx))
    assert r.status_code==503
    for role in ('owner','cleaner','supervisor'):
        assert (await ctx['client'].get('/api/system/issues',headers=auth(ctx,role))).status_code==403
    notices=(await ctx['client'].get('/api/system/issues',headers=auth(ctx))).json()
    assert notices[0]['status']=='open' and 'do-not-record' not in str(notices)
    monkeypatch.setattr(guest_ids,'read_image',original)
    assert (await ctx['client'].get('/api/guest-ids/'+did+'/image',headers=auth(ctx))).status_code==200
    assert (await ctx['client'].get('/api/system/issues',headers=auth(ctx))).json()[0]['status']=='recovered'

@pytest.mark.asyncio
async def test_cancel_releases_atomic_night_claims(ctx):
    today=datetime.now(guest_ids.INDIA_TZ).date()+timedelta(days=10)
    body={'property_id':ctx['p1'],'guest_name':'First','check_in':today.isoformat(),'check_out':(today+timedelta(days=2)).isoformat()}
    first=(await ctx['client'].post('/api/bookings',headers=auth(ctx),json=body)).json()
    assert await ctx['db'].reserved_nights.count_documents({'booking_id':first['id']})==2
    body['status']='cancelled'
    assert (await ctx['client'].put('/api/bookings/'+first['id'],headers=auth(ctx),json=body)).status_code==200
    assert await ctx['db'].reserved_nights.count_documents({'booking_id':first['id']})==0
    body.update(status='confirmed',guest_name='Replacement')
    assert (await ctx['client'].post('/api/bookings',headers=auth(ctx),json=body)).status_code==200

@pytest.mark.asyncio
async def test_calendar_does_not_disclose_admin_id_notes_to_owner(ctx):
    await ctx['db'].bookings.update_one({'_id':ObjectId(ctx['bid'])},{'$set':{'admin_history':[{'note':'private ID decision'}]}})
    month=datetime.now(guest_ids.INDIA_TZ).date().isoformat()[:7]
    r=await ctx['client'].get('/api/calendar',params={'month':month},headers=auth(ctx,'owner'))
    assert r.status_code==200 and 'private ID decision' not in r.text

@pytest.mark.asyncio
async def test_calendar_feed_failure_and_recovery_create_notice(ctx,monkeypatch):
    class Feed:
        text='BEGIN:VCALENDAR\nVERSION:2.0\nBEGIN:VEVENT\nUID:sample\nDTSTART;VALUE=DATE:20261201\nDTEND;VALUE=DATE:20261203\nSUMMARY:Sample stay\nEND:VEVENT\nEND:VCALENDAR'
        def raise_for_status(self): pass
    p=await ctx['db'].properties.find_one({'_id':ObjectId(ctx['p1'])})
    p['ical_feeds']=[{'ota':'Other','url':'https://example.invalid/calendar'}]
    def fail(*args,**kwargs): raise RuntimeError('simulated network failure')
    monkeypatch.setattr(server,'fetch_calendar',fail)
    assert (await server.sync_property(p))[0]['ok'] is False
    monkeypatch.setattr(server,'fetch_calendar',lambda *a,**kw:Feed.text)
    assert (await server.sync_property(p))[0]['ok'] is True
    issue=await ctx['db'].system_issues.find_one({'route':'Calendar sync '+ctx['p1']})
    assert issue['status']=='recovered'
