"""All owner business-data mutation routes and multi-property viewing, in memory."""
import copy
import re
from bson import ObjectId
import pytest
from test_role_security_local import ctx, auth, server

# Login/logout and file tickets are session/view operations, not business-data edits.
# Guest uploads use a separately scoped invitation token, not an owner session.
VIEW_AND_AUTH = {'/api/auth/login','/api/auth/session','/api/auth/logout','/api/files/{media_id}/ticket','/api/guest/documents'}
WRITES = [(method,route.path) for route in server.app.routes
          if getattr(route,'path','').startswith('/api/') and route.path not in VIEW_AND_AUTH
          for method in sorted(getattr(route,'methods',set()) & {'POST','PUT','PATCH','DELETE'})]

@pytest.mark.asyncio
@pytest.mark.parametrize('role',['owner','other_owner'])
@pytest.mark.parametrize('method,path',WRITES)
async def test_all_business_writes_deny_every_owner(ctx,role,method,path):
    path=re.sub(r'\{[^}]+\}',ctx['bid'],path)
    r=await ctx['client'].request(method,path,headers=auth(ctx,role),json={})
    assert r.status_code==403,(method,path,r.status_code,r.text)

@pytest.mark.asyncio
@pytest.mark.parametrize('role',['owner','other_owner'])
async def test_each_owner_reads_complete_assigned_property_data_and_evidence(ctx,role):
    db,c=ctx['db'],ctx['client']
    b=await db.bookings.find_one({'_id':ObjectId(ctx['bid'])})
    await db.bookings.update_one({'_id':b['_id']},{'$set':{'ota':'Direct'}})
    second=copy.deepcopy(b);second.update(_id=ObjectId(),property_id=ctx['p2'],ota='Direct')
    await db.bookings.insert_one(second)
    month=b['check_in'][:7];ids={};reports={}
    for pid in [ctx['p1'],ctx['p2']]:
        mid=ObjectId();await db.media.insert_one({'_id':mid,'is_deleted':False,'kind':'image','storage_path':'fake','owner_id':str(ctx['users']['admin']['_id'])})
        ids[pid]=str(mid)
        body={'property_id':pid,'month':month,'amount':200,'title':'Detailed bill','notes':'Receipt explanation', 'type':'other','treatment':'after_split',
              'allocation':{'owner_percent':50,'britsmaid_percent':50},'media_ids':[str(mid)]}
        created=await c.post('/api/expenses',headers=auth(ctx),json=body);assert created.status_code==200,created.text
        edited=await c.put('/api/expenses/'+created.json()['id'],headers=auth(ctx),json=dict(body,notes='Reviewed receipt explanation',revision=0,change_reason='Clearer explanation'))
        assert edited.status_code==200,edited.text
        report=await c.post('/api/owner-reports',headers=auth(ctx),json={'property_id':pid,'month':month})
        assert report.status_code==200,report.text
        reports[pid]=report.json()['id']
    own=ctx['p1'] if role=='owner' else ctx['p2'];other=ctx['p2'] if role=='owner' else ctx['p1']
    expense=(await c.get('/api/expenses?property_id='+own,headers=auth(ctx,role))).json()[0]
    assert expense['title']=='Detailed bill' and expense['notes']=='Reviewed receipt explanation'
    assert expense['allocation']['owner_amount']==expense['allocation']['britsmaid_amount']==100
    assert expense['media_ids']==[ids[own]]
    history=await c.get('/api/expenses/'+expense['id']+'/history',headers=auth(ctx,role))
    assert history.status_code==200 and history.json()['entries'][0]['reason']=='Clearer explanation'
    assert (await c.post('/api/files/'+ids[own]+'/ticket',headers=auth(ctx,role))).status_code==200
    assert (await c.post('/api/files/'+ids[other]+'/ticket',headers=auth(ctx,role))).status_code==404
    for pid,status in [(own,200),(other,404)]:
        for path in [f'/api/properties/{pid}',f'/api/reports/settlement?property_id={pid}&month={month}',f'/api/calendar?month={month}&property_id={pid}',f'/api/bookings?property_id={pid}',f'/api/expenses?property_id={pid}',f'/api/owner-reports/{reports[pid]}']:
            r=await c.get(path,headers=auth(ctx,role));assert r.status_code==status,(path,r.text)
    admin=(await c.get(f'/api/reports/settlement?property_id={own}&month={month}',headers=auth(ctx))).json()
    owner=(await c.get(f'/api/reports/settlement?property_id={own}&month={month}',headers=auth(ctx,role))).json()
    assert admin==owner

@pytest.mark.asyncio
@pytest.mark.parametrize('assigned',[[],['p1'],['p2'],['p1','p2']])
async def test_owner_global_lists_follow_zero_one_or_multiple_assignments(ctx,assigned):
    db,c=ctx['db'],ctx['client'];allowed=[ctx[key] for key in assigned]
    await db.users.update_one({'_id':ctx['users']['owner']['_id']},{'$set':{'property_ids':allowed}})
    b=await db.bookings.find_one({'_id':ObjectId(ctx['bid'])})
    await db.bookings.update_one({'_id':b['_id']},{'$set':{'ota':'Direct'}})
    second=copy.deepcopy(b);second.update(_id=ObjectId(),property_id=ctx['p2'],ota='Direct')
    await db.bookings.insert_one(second)
    month=b['check_in'][:7]
    for path,field in [('/api/properties','id'),('/api/bookings','property_id'),('/api/cleaning','property_id'),('/api/payouts','property_id'),('/api/owner-reports','property_id')]:
        response=await c.get(path,headers=auth(ctx,'owner'))
        assert response.status_code==200,(path,response.text)
        assert all(row[field] in allowed for row in response.json())
    dash=await c.get('/api/owner/dashboard',headers=auth(ctx,'owner'))
    assert dash.status_code==200,dash.text
    assert {p['id'] for p in dash.json()['villas']}==set(allowed)
    cal=(await c.get('/api/calendar?month='+month,headers=auth(ctx,'owner'))).json()
    assert all(row['property_id'] in allowed for row in cal['bookings']+cal['cleanings'])
    for pid in [ctx['p1'],ctx['p2']]:
        assert (await c.get('/api/properties/'+pid,headers=auth(ctx,'owner'))).status_code==(200 if pid in allowed else 404)
