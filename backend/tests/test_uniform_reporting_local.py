"""Uniform owner reporting regressions using in-memory synthetic records only."""
from bson import ObjectId
import pytest
from test_role_security_local import ctx, auth, server
from booking_finance import percent_amount, money


@pytest.mark.asyncio
@pytest.mark.parametrize('split', [0, .5, 30, 50, 70, 99.5, 100])
@pytest.mark.parametrize('detailed', [False, True])
async def test_split_edit_recalculates_all_properties_without_altering_bookings(ctx, split, detailed):
    db, c = ctx['db'], ctx['client']
    original = await db.bookings.find_one({'_id': ObjectId(ctx['bid'])})
    month = original['check_in'][:7]
    await db.bookings.update_one({'_id': original['_id']}, {'$set': {'ota':'Direct', 'amount':10000.03, 'ota_commission':1000}})
    if detailed:
        detail = server.calculate_booking(10000.03, {'gst':{'percent':5}, 'platform_fee':{'amount':1000, 'manual':True}})
        await db.bookings.update_one({'_id': original['_id']}, {'$set': {'financials':detail}})
    await db.expenses.insert_many([
        {'property_id':ctx['p1'],'month':month,'type':'pre_split','treatment':'before_split','amount':100.01,'title':'Repair'},
        {'property_id':ctx['p1'],'month':month,'type':'other','treatment':'after_split','amount':200.02,'title':'Shared bill',
         'allocation':{'owner_amount':100.01,'britsmaid_amount':100.01,'owner_percent':50,'britsmaid_percent':50}}
    ])
    booking_before = await db.bookings.find_one({'_id': original['_id']})
    report = (await c.post('/api/owner-reports', headers=auth(ctx), json={'property_id':ctx['p1'],'month':month})).json()
    saved_before = await db.owner_reports.find_one({'share_token':report['share_token']})
    first = await server.compute_settlement(await db.properties.find_one({'_id':ObjectId(ctx['p1'])}), month)
    paid = (await c.post('/api/payouts',headers=auth(ctx),json={'property_id':ctx['p1'],'month':month,'amount':max(first['owner_payout'],0),
        'paid_on':original['check_in'],'reference':'SYNTHETIC-UTR','notes':'Synthetic payment only'})).json()
    p = await db.properties.find_one({'_id':ObjectId(ctx['p1'])})
    body = server.PropertyIn.model_validate(dict(p,ical_feeds=[],owner_share_percent=split)).model_dump()
    assert (await c.put('/api/properties/'+ctx['p1'],headers=auth(ctx,'owner'),json=body)).status_code==403
    changed = await c.put('/api/properties/'+ctx['p1'],headers=auth(ctx),json=body)
    assert changed.status_code==200,changed.text
    url=f"/api/reports/settlement?property_id={ctx['p1']}&month={month}"
    s=(await c.get(url,headers=auth(ctx,'owner'))).json()
    assert s==(await c.get(url,headers=auth(ctx))).json()
    assert s['owner_share']==percent_amount(s['net_revenue'],split)
    assert s['owner_before_tds']==money(s['owner_share']-100.01)
    assert s['owner_tds']==percent_amount(max(s['owner_before_tds'],0),2)
    assert s['owner_tds_percent']==2
    assert s['owner_payout']==money(s['owner_before_tds']-s['owner_tds'])
    assert money(s['owner_payout']+s['owner_tds']+s['britsmaid_net']+200.02)==s['net_revenue']
    assert s['payout']['reference']=='SYNTHETIC-UTR'
    assert s['payout']['owner_share_percent']==70
    assert await db.bookings.find_one({'_id':original['_id']})==booking_before
    assert await db.owner_reports.find_one({'_id':saved_before['_id']})==saved_before
    assert (await c.get('/api/payouts?property_id='+ctx['p1'],headers=auth(ctx,'owner'))).json()[0]==paid
    assert (await c.get(url,headers=auth(ctx,'other_owner'))).status_code==404


@pytest.mark.asyncio
@pytest.mark.parametrize('role', ['owner','other_owner','cleaner','supervisor'])
async def test_owner_calendar_scopes_and_write_permissions(ctx,role):
    b=await ctx['db'].bookings.find_one({'_id':ObjectId(ctx['bid'])})
    url='/api/calendar?month='+b['check_in'][:7]
    r=await ctx['client'].get(url,headers=auth(ctx,role))
    if role in ('cleaner','supervisor'):
        assert r.status_code==403
        return
    assert r.status_code==200
    allowed=ctx['p1'] if role=='owner' else ctx['p2']
    assert all(x['property_id']==allowed for x in r.json()['bookings']+r.json()['cleanings'])
    denied=ctx['p2'] if role=='owner' else ctx['p1']
    assert (await ctx['client'].get(url+'&property_id='+denied,headers=auth(ctx,role))).status_code==404
    if role=='owner':
        own=(await ctx['client'].get('/api/bookings/'+ctx['bid'],headers=auth(ctx,role))).json()
        assert own['amount']==b['amount']
        assert (await ctx['client'].put('/api/bookings/'+ctx['bid'],headers=auth(ctx,role),json=own)).status_code==403


@pytest.mark.asyncio
@pytest.mark.parametrize('split',[-1,100.01,'nan','inf'])
async def test_invalid_splits_rejected(ctx,split):
    p=await ctx['db'].properties.find_one({'_id':ObjectId(ctx['p1'])})
    body=server.PropertyIn.model_validate(dict(p,ical_feeds=[])).model_dump()
    body['owner_share_percent']=split
    assert (await ctx['client'].put('/api/properties/'+ctx['p1'],headers=auth(ctx),json=body)).status_code==422
    assert (await ctx['db'].properties.find_one({'_id':p['_id']}))['owner_share_percent']==70

@pytest.mark.asyncio
@pytest.mark.parametrize('cost', [.01,.03,20.15,4411.01])
async def test_older_shared_electricity_paise_matches_display_and_conserves_cost(ctx,cost):
    b=await ctx['db'].bookings.find_one({'_id':ObjectId(ctx['bid'])})
    await ctx['db'].bookings.update_one({'_id':b['_id']},{'$set':{'ota':'Direct'}})
    await ctx['db'].properties.update_one({'_id':ObjectId(ctx['p1'])},{'$set':{'electricity_mode':'split_half'}})
    await ctx['db'].expenses.insert_one({'property_id':ctx['p1'],'month':b['check_in'][:7],'type':'electricity','amount':cost})
    p=await ctx['db'].properties.find_one({'_id':ObjectId(ctx['p1'])})
    s=await server.compute_settlement(p,b['check_in'][:7])
    assert money(s['owner_electricity']+s['britsmaid_electricity'])==cost
    item=s['deduction_items'][0]
    assert s['owner_electricity']==item['owner_amount']
    assert s['britsmaid_electricity']==item['britsmaid_amount']

@pytest.mark.asyncio
@pytest.mark.parametrize('misc',[0,.01,100])
async def test_shared_ota_breakdown_explains_taxes_and_misc_separately(ctx,misc):
    b=await ctx['db'].bookings.find_one({'_id':ObjectId(ctx['bid'])})
    f=server.calculate_booking(10500,{'gst':{'percent':5},'platform_fee':{'percent':10},'platform_tax':{'percent':1},'misc_amount':misc,'misc_title':'Linen'})
    await ctx['db'].bookings.update_one({'_id':b['_id']},{'$set':{'ota':'Direct','amount':10500,'financials':f}})
    report=await ctx['client'].post('/api/owner-reports',headers=auth(ctx),json={'property_id':ctx['p1'],'month':b['check_in'][:7]})
    assert report.status_code==200,report.text
    html=(await ctx['client'].get('/api/public/reports/'+report.json()['share_token'])).text
    section=html.split('<b>Revenue by OTA</b>')[1].split('<b>Bookings</b>')[0]
    assert 'Taxes &amp; commission' in section and 'Revenue available to split' in section
    assert '1,600' in section
    assert ('Other booking expenses' in section)==bool(misc)
