"""Synthetic activity summaries and push payloads; no external push delivery."""
import json
from datetime import date, timedelta
from bson import ObjectId
import pytest
from test_role_security_local import ctx, auth, server, invitation, upload_id
from activity import Activity
from activity_details import describe, snapshot


@pytest.mark.asyncio
@pytest.mark.parametrize('suffix,method,expected', [('', 'PUT', 'Booking updated'),
    ('/cancel', 'POST', 'Booking cancelled'), ('/revenue', 'POST', 'Additional revenue saved'),
    ('/guest-link', 'POST', 'Guest upload link created'), ('/guest-link', 'DELETE', 'Guest upload link revoked')])
async def test_booking_context(ctx, suffix, method, expected):
    await ctx['db'].properties.update_one({'_id': ObjectId(ctx['p1'])}, {'$set': {'name': 'BM-001 Divya Villa'}})
    details = await describe(ctx['db'], method, '/api/bookings/'+ctx['bid']+suffix)
    assert details['title'] == expected+' · BM-001 Divya Villa'
    assert 'Stay:' in details['body'] and '20' in details['body']
    assert details['url'] == '/booking/'+ctx['bid']


@pytest.mark.asyncio
@pytest.mark.parametrize('status,title', [('completed','Cleaning completed'), ('awaiting_review','Cleaning ready for review'),
    ('in_progress','Cleaning in progress'), ('cancelled','Cleaning cancelled'), ('pending','Cleaning scheduled')])
async def test_cleaning_state_descriptions(ctx, status, title):
    await ctx['db'].cleaning.update_one({'_id':ObjectId(ctx['cid'])}, {'$set': {'status':status}})
    d = await describe(ctx['db'], 'PUT', '/api/cleaning/'+ctx['cid'], before={'status':'old'})
    assert d['title'] == title+' · '+ctx['p1'] and 'Cleaning date:' in d['body']
    pending = await describe(ctx['db'], 'PUT', '/api/cleaning/'+ctx['cid'], action='Cleaning pending')
    assert pending['title'].startswith('Cleaning pending · ') and 'Cleaning date:' in pending['body']


@pytest.mark.asyncio
async def test_context_handles_deleted_records_and_keeps_secrets_out(ctx):
    db=ctx['db']; eid=ObjectId()
    await db.expenses.insert_one({'_id':eid,'property_id':ctx['p1'],'month':'2026-11','title':'Electricity',
        'notes':'PRIVATE-NOTES','password':'SECRET-PASSWORD','share_token':'SECRET-TOKEN','amount':123})
    before=await snapshot(db,'expenses',str(eid)); await db.expenses.delete_one({'_id':eid})
    d=await describe(db,'DELETE','/api/expenses/'+str(eid),before=before)
    assert d['title']=='Expense removed · '+ctx['p1'] and 'November 2026' in d['body'] and 'Electricity' in d['body']
    assert 'PRIVATE' not in json.dumps(d) and 'SECRET' not in json.dumps(before,default=str)
    missing=await describe(db,'PUT','/api/bookings/'+str(ObjectId()))
    assert missing['title']=='Booking updated' and missing['body']==''


@pytest.mark.asyncio
async def test_actual_booking_notification_is_contextual_and_only_successful(ctx):
    c=ctx['client']; start=date.today()+timedelta(days=10)
    r=await c.post('/api/bookings',headers=auth(ctx),json={'property_id':ctx['p2'],'guest_name':'Synthetic guest',
        'check_in':start.isoformat(),'check_out':(start+timedelta(days=2)).isoformat(),'ota':'Direct','amount':1000,'status':'confirmed'})
    assert r.status_code==200,r.text
    rows=(await c.get('/api/notifications',headers=auth(ctx))).json()
    assert len(rows)==1 and rows[0]['title']=='Booking recorded · '+ctx['p2']
    assert 'Stay:' in rows[0]['body'] and rows[0]['url']=='/booking/'+r.json()['id']
    await c.post('/api/bookings',headers=auth(ctx),json={})
    assert len((await c.get('/api/notifications',headers=auth(ctx))).json())==1


@pytest.mark.asyncio
async def test_member_details_no_password_and_verification_is_not_activity(ctx):
    uid=ctx['users']['cleaner']['_id']; pw='Synthetic-password-123'
    await ctx['db'].users.update_one({'_id':uid},{'$set':{'password_hash':server.hash_pw(pw)}})
    d=await describe(ctx['db'],'PUT','/api/users/'+str(uid),data={'password':pw,'temp_password':pw})
    assert d['title']=='Team member updated · cleaner' and 'Role: cleaner' in d['body'] and ctx['p1'] in d['body']
    assert pw not in json.dumps(d) and 'password_hash' not in json.dumps(d)
    r=await ctx['client'].post('/api/users/'+str(uid)+'/verify-invite-password',headers=auth(ctx),json={'password':pw})
    assert r.status_code==200
    assert await ctx['db'].activities.count_documents({})==0


@pytest.mark.asyncio
async def test_guest_id_submission_notification_is_booking_bound_without_document_details(ctx,monkeypatch):
    monkeypatch.setattr(server.app,'middleware_stack',None)
    h=await invitation(ctx)
    await ctx['db'].activities.delete_many({})
    r=await upload_id(ctx,h,guest_name='PRIVATE-ID-NAME')
    assert r.status_code==200
    row=await ctx['db'].activities.find_one({})
    assert row['title']=='Guest ID submitted · '+ctx['p1']
    assert row['url']=='/guests?booking_id='+ctx['bid'] and 'Guest 1' in row['body'] and 'Stay:' in row['body']
    assert 'PRIVATE-ID-NAME' not in json.dumps(row) and 'storage_key' not in json.dumps(row)


@pytest.mark.asyncio
async def test_push_includes_context_activity_time_and_destination(ctx,monkeypatch):
    db=ctx['db']; calls=[]
    await db.settings.insert_one({'_id':'admin-web-push','private':'synthetic-key'})
    await db.push_subscriptions.insert_one({'_id':'device','user_id':str(ctx['users']['admin']['_id']),
        'created_at':'2000-01-01T00:00:00+00:00','subscription':{'endpoint':'synthetic'}})
    a=Activity(db)
    await a.record('event','Cleaning completed · BM-001 Divya Villa','/cleaning/'+ctx['cid'],'Cleaning date: 26 Nov 2026')
    monkeypatch.setattr('pywebpush.webpush',lambda **kwargs:calls.append(json.loads(kwargs['data'])))
    await a.deliver(); await a.deliver()
    assert len(calls)==1
    payload=calls[0]
    assert 'BM-001 Divya Villa' in payload['title'] and 'Cleaning date:' in payload['details']
    assert 'Activity:' in payload['details'] and 'IST' in payload['details'] and payload['url']=='/cleaning/'+ctx['cid']
    assert payload['title'] in payload['body'] # Backward-compatible installed workers.


@pytest.mark.asyncio
async def test_old_inbox_events_still_work(ctx):
    a=Activity(ctx['db']);await a.record('legacy','Recorded bookings')
    r=await ctx['client'].get('/api/notifications',headers=auth(ctx))
    assert r.status_code==200 and r.json()[0]['title']=='Recorded bookings' and 'body' not in r.json()[0]


@pytest.mark.asyncio
async def test_training_details_and_calendar_sync(ctx):
    aid=ObjectId()
    await ctx['db'].training_assignments.insert_one({'_id':aid,'cleaner_name':'Synthetic Cleaner','lesson':{'title':'Room preparation','private_note':'SECRET'}})
    d=await describe(ctx['db'],'POST','/api/training/assignments/'+str(aid)+'/complete')
    assert d['title']=='Training completed' and 'Room preparation' in d['body'] and 'Synthetic Cleaner' in d['body']
    assert 'SECRET' not in json.dumps(d)
    sync=await describe(ctx['db'],'POST','/api/properties/'+ctx['p1']+'/ical-sync')
    assert sync['title']=='Calendar sync completed · '+ctx['p1']


@pytest.mark.asyncio
async def test_context_is_bounded_handles_unusual_names_and_months(ctx):
    pid=ObjectId(ctx['p1']);eid=ObjectId()
    await ctx['db'].properties.update_one({'_id':pid},{'$set':{'name':'BM-001\n'+'Villa ' * 200}})
    await ctx['db'].expenses.insert_one({'_id':eid,'property_id':ctx['p1'],'month':'invalid','title':'Bad\nspacing'})
    d=await describe(ctx['db'],'PUT','/api/expenses/'+str(eid))
    assert len(d['title'])<=240 and len(d['body'])<=600 and '\n' not in d['title']
    assert 'Invalid' not in d['body'] and 'Bad spacing' in d['body']


@pytest.mark.asyncio
async def test_saved_response_context_wins_over_a_later_database_edit(ctx):
    d=await describe(ctx['db'],'PUT','/api/bookings/'+ctx['bid'],data={
        'property_id':ctx['p2'],'check_in':'2026-12-22','check_out':'2026-12-24','password':'SECRET'})
    assert d['title']=='Booking updated · '+ctx['p2']
    assert '22 Dec 2026' in d['body'] and '24 Dec 2026' in d['body']
    assert 'SECRET' not in json.dumps(d)
