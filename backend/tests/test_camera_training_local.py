"""Synthetic ASGI/MongoMock tests, never a live backend."""
import asyncio
from datetime import datetime, timedelta, timezone
from bson import ObjectId
import pytest
from test_role_security_local import ctx, auth, server
from training import utcnow

pytestmark = pytest.mark.asyncio

async def lesson(ctx, **kw):
    await server.training.indexes()
    r = await ctx['client'].post('/api/training/lessons', headers=auth(ctx), json={'title':'SAMPLE - room photo training', 'instructions':'SAMPLE ONLY. Not operationally approved. Photograph each room before and after.', **kw})
    assert r.status_code == 200, r.text
    lid = r.json()['id']
    r = await ctx['client'].post(f'/api/training/lessons/{lid}/publish', headers=auth(ctx))
    assert r.status_code == 200, r.text
    return lid

async def assign(ctx, lid, **kw):
    r = await ctx['client'].post(f'/api/training/lessons/{lid}/assign', headers=auth(ctx), json={'cleaner_ids':[str(ctx['users']['cleaner']['_id'])], 'request_id':'synthetic-request-1', **kw})
    assert r.status_code == 200, r.text
    return r.json()

@pytest.mark.parametrize('role',['owner','cleaner','supervisor'])
@pytest.mark.parametrize('method,path,body', [('GET','/training/lessons',None),('POST','/training/lessons',{'title':'Tamper','instructions':'Tamper'}),('POST','/training/schedule',{})])
async def test_admin_only_training_management(ctx,role,method,path,body):
    r=await ctx['client'].request(method,'/api'+path,headers=auth(ctx,role),json=body)
    assert r.status_code == 403

async def test_snapshot_edit_publish_archive_history(ctx):
    lid=await lesson(ctx)
    rows=await assign(ctx,lid)
    aid=rows[0]['id']
    assert rows[0]['lesson']['revision']==1
    await ctx['client'].put(f'/api/training/lessons/{lid}',headers=auth(ctx),json={'title':'Revision 2','instructions':'Changed procedure'})
    for _ in range(2):
        r=await ctx['client'].post(f'/api/training/lessons/{lid}/publish',headers=auth(ctx))
        assert r.json()['revision']==2
    r=await ctx['client'].post(f'/api/training/assignments/{aid}/complete',headers=auth(ctx,'cleaner'))
    completed=r.json()['completed_at']
    assert r.json()['lesson']['revision']==1
    r=await ctx['client'].post(f'/api/training/assignments/{aid}/complete',headers=auth(ctx,'cleaner'))
    assert r.json()['completed_at']==completed
    fresh=await assign(ctx,lid,request_id='changed-procedure-2')
    assert fresh[0]['lesson']['revision']==2
    await ctx['client'].post(f'/api/training/lessons/{lid}/archive',headers=auth(ctx))
    r=await ctx['client'].post(f'/api/training/lessons/{lid}/assign',headers=auth(ctx),json={'all_active':True,'request_id':'archive-new-3'})
    assert r.status_code==409
    assert await ctx['db'].training_assignments.count_documents({})==2
    history=(await ctx['client'].get('/api/training/assignments',headers=auth(ctx,'cleaner'))).json()
    assert any(x['completed_at']==completed for x in history)

async def test_all_active_cleaners_and_duplicate_assignments(ctx):
    lid=await lesson(ctx)
    await ctx['db'].users.insert_one({'_id':ObjectId(),'name':'Inactive','role':'cleaner','active':False})
    first=await assign(ctx,lid,all_active=True)
    second=await assign(ctx,lid,all_active=True)
    assert len(first)==2 and {x['id'] for x in first}=={x['id'] for x in second}

async def test_own_training_only_and_tampering(ctx):
    lid=await lesson(ctx)
    rows=await assign(ctx,lid)
    aid=rows[0]['id']
    assert (await ctx['client'].get('/api/training/assignments',headers=auth(ctx,'other_cleaner'))).json()==[]
    assert (await ctx['client'].post(f'/api/training/assignments/{aid}/complete',headers=auth(ctx,'other_cleaner'))).status_code==404
    for role in ['admin','owner','supervisor']:
        assert (await ctx['client'].post(f'/api/training/assignments/{aid}/complete',headers=auth(ctx,role))).status_code==403
    await ctx['db'].users.update_one({'_id':ctx['users']['cleaner']['_id']},{'$set':{'active':False}})
    assert (await ctx['client'].get('/api/training/assignments',headers=auth(ctx,'cleaner'))).status_code==401

async def test_onboarding_and_refresher_repeat_scheduler(ctx):
    lid=await lesson(ctx,onboarding=True,refresher_days=30)
    await server.training.onboarding(ctx['users']['cleaner'])
    await server.training.onboarding(ctx['users']['cleaner'])
    row=await ctx['db'].training_assignments.find_one({})
    await ctx['client'].post(f"/api/training/assignments/{row['_id']}/complete",headers=auth(ctx,'cleaner'))
    await asyncio.gather(server.training.schedule(),server.training.schedule())
    assert await ctx['db'].training_assignments.count_documents({})==2
    refresher=await ctx['db'].training_assignments.find_one({'source':'refresher'})
    assert datetime.fromisoformat(refresher['due_at']) > utcnow()+timedelta(days=29)
    await ctx['db'].users.update_one({'_id':ctx['users']['cleaner']['_id']},{'$set':{'active':False}})
    await ctx['db'].training_assignments.update_one({'_id':refresher['_id']},{'$set':{'completed_at':utcnow().isoformat()}})
    await server.training.schedule()
    assert await ctx['db'].training_assignments.count_documents({})==2

async def test_onboarding_new_cleaner_api(ctx):
    await lesson(ctx,onboarding=True)
    r=await ctx['client'].post('/api/users',headers=auth(ctx),json={'name':'SAMPLE New Cleaner','email':'new.synthetic@example.com','password':'Strong-Preview-2026!','role':'cleaner','property_ids':[ctx['p1']]})
    assert r.status_code==200,r.text
    assert await ctx['db'].training_assignments.count_documents({'cleaner_id':r.json()['id']})==1

async def test_due_date_india_utc_overdue(ctx):
    lid=await lesson(ctx)
    rows=await assign(ctx,lid,due_on='2026-01-01')
    assert rows[0]['due_at']=='2026-01-01T18:30:00+00:00'
    assert rows[0]['status']=='overdue'

@pytest.mark.parametrize('field,value',[('title','  '),('instructions',''),('refresher_days',0),('due_days',-1),('links',['javascript:alert(1)']),('links',['http://example.com/video'])])
async def test_training_validation(ctx,field,value):
    r=await ctx['client'].post('/api/training/lessons',headers=auth(ctx),json={'title':'Sample','instructions':'Sample instructions',field:value})
    assert r.status_code==422

async def test_photo_stale_wrong_room_phase_reassignment_and_cancel(ctx):
    cid=ctx['cid']; mid=ObjectId()
    await ctx['db'].media.insert_one({'_id':mid,'is_deleted':False,'kind':'image','owner_id':str(ctx['users']['cleaner']['_id'])})
    url=f'/api/cleaning/{cid}/rooms/0/media'
    for extra in [{'room_name':'Wrong room'}, {'expected_revision':99}]:
        r=await ctx['client'].post(url,headers=auth(ctx,'cleaner'),json={'phase':'before','media_id':str(mid),**extra})
        assert r.status_code==409
    body={'phase':'before','media_id':str(mid),'room_name':'Bedroom','expected_revision':0}
    first=await ctx['client'].post(url,headers=auth(ctx,'cleaner'),json=body)
    assert first.status_code==200,first.text
    r=await ctx['client'].post(url,headers=auth(ctx,'cleaner'),json=body)
    assert r.status_code==200 and r.json()['revision']==first.json()['revision']
    r=await ctx['client'].post(url,headers=auth(ctx,'cleaner'),json={**body,'phase':'after','expected_revision':first.json()['revision']})
    assert r.status_code==409
    await ctx['db'].cleaning.update_one({'_id':ObjectId(cid)},{'$set':{'status':'cancelled'}})
    assert (await ctx['client'].post(url,headers=auth(ctx,'cleaner'),json=body)).status_code==409

async def test_training_does_not_block_cleaning(ctx):
    lid=await lesson(ctx)
    await assign(ctx,lid,due_on='2020-01-01')
    assert (await ctx['client'].get(f"/api/cleaning/{ctx['cid']}",headers=auth(ctx,'cleaner'))).status_code==200
@pytest.mark.parametrize('field,value',[('name','   '),('rooms',['Room','room']),('rooms',['']),('base_rate',-1)])
async def test_property_validation(ctx,field,value):
    r=await ctx['client'].post('/api/properties',headers=auth(ctx),json={'name':'SAMPLE Property','rooms':['Room'],field:value})
    assert r.status_code==422

async def test_property_edits_preserve_existing_cleaning_room_evidence(ctx):
    await ctx['db'].cleaning.update_one({'_id':ObjectId(ctx['cid'])},{'$set':{'rooms.0.before':['synthetic-photo']}})
    r=await ctx['client'].put(f"/api/properties/{ctx['p1']}",headers=auth(ctx),json={'name':'Renamed','rooms':['New room']})
    assert r.status_code==200
    task=await ctx['db'].cleaning.find_one({'_id':ObjectId(ctx['cid'])})
    assert task['rooms'][0]['name']=='Bedroom' and task['rooms'][0]['before']==['synthetic-photo']

async def test_cancelled_cleaning_does_not_show_property_dirty(ctx):
    await ctx['db'].cleaning.update_one({'_id':ObjectId(ctx['cid'])},{'$set':{'status':'cancelled','date':'2000-01-01'}})
    assert (await server.property_status(ctx['p1'],'2026-10-19'))['needs_cleaning'] is False

async def test_report_finance_lifecycle_and_private_media_reference(ctx,monkeypatch):
    from test_role_security_local import jpeg
    monkeypatch.setattr(server,'put_object',lambda path,data,ctype:{'path':path,'size':len(data)})
    await ctx['db'].bookings.update_many({},{'$set':{'ota':'Direct','ota_commission':0}})
    r=await ctx['client'].post('/api/upload',headers=auth(ctx),files={'file':('sample.jpg',jpeg(),'image/jpeg')})
    assert r.status_code==200
    mid=r.json()['id']
    r=await ctx['client'].post('/api/owner-reports',headers=auth(ctx),json={'property_id':ctx['p1'],'month':datetime.now().strftime('%Y-%m'),'condition_notes':'SAMPLE','media_ids':[mid]})
    assert r.status_code==200,r.text
    report=r.json(); token=report['share_token']
    assert (await ctx['client'].get(f"/api/owner-reports/{report['id']}",headers=auth(ctx,'other_owner'))).status_code==404
    assert (await ctx['client'].get(f'/api/public/reports/{token}')).status_code==200
    assert (await ctx['client'].get(f'/api/public/reports/{token}/media/{mid}')).status_code==200
    assert (await ctx['client'].get(f'/api/public/reports/{token}/media/{ObjectId()}')).status_code==404
    await ctx['client'].delete(f"/api/owner-reports/{report['id']}",headers=auth(ctx))
    assert (await ctx['client'].get(f'/api/public/reports/{token}')).status_code==404

async def test_ical_changed_cancelled_duplicate_and_timezones_mocked(ctx,monkeypatch):
    # Mocked provider only: no external request, real iCalendar parser + booking reconciliation.
    await ctx['db'].bookings.delete_many({})
    p=await ctx['db'].properties.find_one({'_id':ObjectId(ctx['p1'])})
    p['ical_feeds']=[{'ota':'Direct','url':'https://synthetic.invalid/calendar.ics'}]
    class Feed:
        text=''
        def raise_for_status(self): pass
    feed=Feed()
    monkeypatch.setattr(server,'fetch_calendar',lambda *a,**kw:feed.text)
    def content(end='20261112',status='CONFIRMED'):
        return f'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:synthetic-event\r\nDTSTART;VALUE=DATE:20261110\r\nDTEND;VALUE=DATE:{end}\r\nSUMMARY:SAMPLE OTA\r\nSTATUS:{status}\r\nEND:VEVENT\r\nEND:VCALENDAR'
    feed.text=content()
    assert (await server.sync_property(p))[0]['ok']
    assert (await server.sync_property(p))[0]['ok']
    assert await ctx['db'].bookings.count_documents({})==1
    booking=await ctx['db'].bookings.find_one({})
    feed.text=content('20261113')
    assert (await server.sync_property(p))[0]['ok']
    task=await ctx['db'].cleaning.find_one({'booking_id':str(booking['_id'])})
    assert task['date']=='2026-11-13'
    feed.text=content('20261113','CANCELLED')
    assert (await server.sync_property(p))[0]['ok']
    assert (await ctx['db'].bookings.find_one({}))['status']=='cancelled'
    assert (await ctx['db'].cleaning.find_one({'booking_id':str(booking['_id'])}))['status']=='cancelled'
    assert await ctx['db'].reserved_nights.count_documents({})==0
    assert server._to_date_str(datetime(2026,11,10,22,tzinfo=timezone.utc))=='2026-11-11'

async def test_photo_claim_stops_simultaneous_cross_phase_attachment(ctx):
    mid=ObjectId()
    await ctx['db'].media.insert_one({'_id':mid,'kind':'image','owner_id':str(ctx['users']['cleaner']['_id']),'is_deleted':False})
    async def post(phase):
        return await ctx['client'].post(f"/api/cleaning/{ctx['cid']}/rooms/0/media",headers=auth(ctx,'cleaner'),json={'phase':phase,'media_id':str(mid)})
    rows=await asyncio.gather(post('before'),post('after'))
    assert sorted(x.status_code for x in rows)==[200,409]
@pytest.mark.parametrize('field,value',[('bill_to_name',' '),('due_date','2020-01-01'),('booking_id','invalid')])
async def test_invoice_reference_recipient_dates(ctx,field,value):
    body={'type':'guest','bill_to_name':'SAMPLE','items':[{'description':'Stay','qty':2,'rate':100}],'issue_date':'2026-10-19',field:value}
    r=await ctx['client'].post('/api/invoices',headers=auth(ctx),json=body)
    assert 400 <= r.status_code < 500

async def test_invoice_totals_and_status(ctx):
    r=await ctx['client'].post('/api/invoices',headers=auth(ctx),json={'type':'guest','bill_to_name':'SAMPLE','items':[{'description':'Stay','qty':2,'rate':100}],'discount':50,'tax_percent':18,'issue_date':'2026-10-19'})
    assert r.status_code==200,r.text
    assert r.json()['subtotal']==200 and r.json()['total']==177
    url=f"/api/invoices/{r.json()['id']}/status"
    assert (await ctx['client'].put(url,headers=auth(ctx),json={'status':'paid'})).json()['status']=='paid'
    assert (await ctx['client'].put(url,headers=auth(ctx,'owner'),json={'status':'unpaid'})).status_code==403

@pytest.mark.parametrize('mid',['invalid','000000000000000000000123'])
async def test_report_rejects_missing_or_private_document_reference(ctx,mid):
    r=await ctx['client'].post('/api/owner-reports',headers=auth(ctx),json={'property_id':ctx['p1'],'month':'2026-10','media_ids':[mid]})
    assert r.status_code==422

async def test_delete_booking_cancels_work_without_erasing_room_evidence(ctx):
    await ctx['db'].cleaning.update_one({'_id':ObjectId(ctx['cid'])},{'$set':{'booking_id':ctx['bid'],'status':'in_progress','rooms.0.before':['synthetic']}})
    r=await ctx['client'].delete(f"/api/bookings/{ctx['bid']}",headers=auth(ctx))
    assert r.status_code==200
    task=await ctx['db'].cleaning.find_one({'_id':ObjectId(ctx['cid'])})
    assert task['status']=='cancelled' and task['rooms'][0]['before']==['synthetic']

async def test_upload_lost_ack_retry_reuses_media_and_storage(ctx,monkeypatch):
    from test_role_security_local import jpeg
    writes=[]
    monkeypatch.setattr(server,'put_object',lambda path,data,ctype:(writes.append(path) or {'path':path,'size':len(data)}))
    result=[]
    for _ in range(2):
        r=await ctx['client'].post('/api/upload',headers=auth(ctx,'cleaner'),data={'request_key':'synthetic-photo-1'},files={'file':('sample.jpg',jpeg(),'image/jpeg')})
        assert r.status_code==200,r.text
        result.append(r.json()['id'])
    assert result[0]==result[1] and len(writes)==1
    assert await ctx['db'].media.count_documents({})==1

async def test_multiple_completed_assignments_produce_one_current_refresher(ctx):
    lid=await lesson(ctx,refresher_days=30)
    for request in ['procedure-original','procedure-update']:
        row=(await assign(ctx,lid,request_id=request))[0]
        await ctx['client'].post(f"/api/training/assignments/{row['id']}/complete",headers=auth(ctx,'cleaner'))
    await server.training.schedule()
    await server.training.schedule()
    assert await ctx['db'].training_assignments.count_documents({'source':'refresher','completed_at':None})==1


async def test_cleaner_can_save_notes_before_room_completion(ctx):
    url=f"/api/cleaning/{ctx['cid']}"
    r=await ctx['client'].put(url,headers=auth(ctx,'cleaner'),json={'notes':'SAMPLE maintenance: check the tap'})
    assert r.status_code==200 and r.json()['notes']=='SAMPLE maintenance: check the tap'
    assert r.json()['status']=='pending'
    assert (await ctx['client'].put(url,headers=auth(ctx,'cleaner'),json={'status':'completed'})).status_code==400
    assert (await ctx['client'].get(url,headers=auth(ctx,'cleaner'))).json()['notes']=='SAMPLE maintenance: check the tap'
