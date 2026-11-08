"""Isolated expense edits, owner transparency and bidirectional financial entry."""
import asyncio
from decimal import Decimal, ROUND_HALF_UP
from bson import ObjectId
import pytest
from fastapi import HTTPException
from test_role_security_local import ctx, auth, server
from booking_finance import calculate, allocate

@pytest.mark.parametrize('inclusive', [True, False])
@pytest.mark.parametrize('rate', [0, .01, 2, 5, 18, 50, 100])
@pytest.mark.parametrize('gross', [.01, .03, 20.15, 10500, 999999.99])
def test_rate_to_amount_and_back(inclusive, rate, gross):
    f = calculate(gross, {'gst_included': inclusive, 'gst': {'percent': rate, 'entry_mode': 'percent'}})
    amount = f['gst']['amount']
    d = {'gst_included': inclusive, 'gst': {'amount': amount, 'entry_mode': 'amount'}}
    taxable = f['guest_total'] - amount
    if amount and (taxable <= 0 or amount > round(taxable, 2)):
        with pytest.raises(HTTPException): calculate(gross, d)
    else:
        back = calculate(gross, d)
        assert back['gst']['amount'] == amount
        if taxable > 0:
            expected = float((Decimal(str(amount))*100/Decimal(str(round(taxable, 2)))).quantize(Decimal('.000001'), rounding=ROUND_HALF_UP))
            assert back['gst']['percent'] == expected
        assert calculate(gross, back)['net_revenue'] == back['net_revenue']

@pytest.mark.parametrize('base', ['gross', 'excluding_gst'])
@pytest.mark.parametrize('key', ['platform_fee', 'platform_tax'])
@pytest.mark.parametrize('amount', [0, .01, 9.99, 950, 9999.99])
def test_amount_uses_correct_base_and_stays_fixed(base, key, amount):
    d = {'gst': {'percent': 5}, key: {'amount': amount, 'base': base, 'entry_mode': 'amount', 'manual': False}}
    f = calculate(10500, d)
    assert f[key]['amount'] == amount
    assert f[key]['percent'] == float((Decimal(str(amount))*100/Decimal(10500 if base == 'gross' else 10000)).quantize(Decimal('.000001'), rounding=ROUND_HALF_UP))
    assert calculate(21000, f)[key]['amount'] == amount
    f[key].update(percent=10, entry_mode='percent', manual=True)
    assert calculate(10500, f)[key]['amount'] == (1050 if base == 'gross' else 1000)

def test_zero_base_and_gst_rejection():
    assert server.inr(123) == '\u20b9123.00'
    assert calculate(0, {'gst': {'entry_mode': 'amount'}})['gst']['percent'] is None
    for amount in [100, 101, 75]:
        with pytest.raises(HTTPException): calculate(100, {'gst': {'amount': amount, 'entry_mode': 'amount'}})
    assert allocate(1000, {'entry_mode': 'amount', 'owner_amount': 123.45, 'britsmaid_amount': 876.55})['owner_percent'] == 12.345
    assert calculate(20.15, {'platform_fee': {'percent': 50}})['platform_fee']['amount'] == 10.08

async def seed(ctx):
    await ctx['db'].bookings.update_one({'_id': ObjectId(ctx['bid'])}, {'$set': {'ota': 'Direct', 'amount': 10000, 'financials': calculate(10000, {})}})
    return (await ctx['db'].bookings.find_one({'_id': ObjectId(ctx['bid'])}))['check_in'][:7]

def body(ctx, month, treatment='after_split', owner=50):
    return dict(property_id=ctx['p1'], month=month, treatment=treatment, title='Electricity or repair', notes='Receipt checked', amount=1000,
                allocation={'owner_percent': owner, 'britsmaid_percent': 100-owner} if treatment == 'after_split' else None)

@pytest.mark.asyncio
@pytest.mark.parametrize('treatment,owner,net,payout,bm', [('before_split',50,9000,6174,2700), ('after_split',50,10000,6370,2500), ('after_split',100,10000,5880,3000), ('after_split',0,10000,6860,2000)])
async def test_examples_reconcile(ctx,treatment,owner,net,payout,bm):
    month = await seed(ctx)
    r = await ctx['client'].post('/api/expenses', headers=auth(ctx), json=body(ctx,month,treatment,owner))
    assert r.status_code == 200, r.text
    s = (await ctx['client'].get(f"/api/reports/settlement?property_id={ctx['p1']}&month={month}",headers=auth(ctx,'owner'))).json()
    assert (s['net_revenue'],s['owner_payout'],s['britsmaid_net']) == (net,payout,bm)
    assert round(s['owner_payout'] + s['owner_tds'] + s['britsmaid_net'] + s['expense_after_total'],2) == net
    assert s['deduction_items'][0]['treatment'] == treatment

@pytest.mark.asyncio
async def test_revision_history_idempotency_and_soft_removal(ctx):
    month=await seed(ctx); c=ctx['client']; b=body(ctx,month); b['request_key']='unique-expense-123'
    r=await c.post('/api/expenses',headers=auth(ctx),json=b); assert r.status_code==200,r.text
    e=r.json(); path='/api/expenses/'+e['id']
    assert (await c.post('/api/expenses',headers=auth(ctx),json=b)).json()['id']==e['id']
    update=dict(b,revision=0,change_reason='Correct receipt',amount=2000)
    results=await asyncio.gather(*[c.put(path,headers=auth(ctx),json=update) for _ in range(2)])
    assert sorted(r.status_code for r in results)==[200,409]
    history=(await c.get(path+'/history',headers=auth(ctx,'owner'))).json()
    assert len(history['entries'])==1
    assert history['entries'][0]['before']['amount']==1000
    assert history['entries'][0]['after']['amount']==2000
    assert 'actor_id' not in history['entries'][0]
    assert (await c.post('/api/expenses',headers=auth(ctx),json=b)).status_code==409
    assert (await c.request('DELETE',path,headers=auth(ctx),json={'revision':0,'change_reason':'Wrong bill'})).status_code==409
    assert (await c.request('DELETE',path,headers=auth(ctx),json={'revision':1,'change_reason':'Duplicate bill'})).status_code==200
    assert (await c.put(path,headers=auth(ctx),json=dict(update,revision=2))).status_code==404
    assert (await c.get('/api/expenses?property_id='+ctx['p1'],headers=auth(ctx,'owner'))).json()==[]
    history=(await c.get(path+'/history',headers=auth(ctx,'owner'))).json()
    assert history['is_deleted'] and len(history['entries'])==2

@pytest.mark.asyncio
@pytest.mark.parametrize('role,expected',[('owner',200),('other_owner',404),('cleaner',403),('supervisor',403)])
async def test_history_and_edit_permissions(ctx,role,expected):
    month=await seed(ctx); c=ctx['client']; b=body(ctx,month)
    e=(await c.post('/api/expenses',headers=auth(ctx),json=b)).json();path='/api/expenses/'+e['id']
    assert (await c.get(path+'/history',headers=auth(ctx,role))).status_code==expected
    assert (await c.put(path,headers=auth(ctx,role),json=dict(b,revision=0,change_reason='Tamper'))).status_code==403

@pytest.mark.asyncio
@pytest.mark.parametrize('patch',[{'title':' '},{'amount':0},{'amount':.001},{'amount':-1},{'month':'2026-13'},{'allocation':None},{'treatment':'before_split'},{'allocation':{'owner_percent':50,'britsmaid_percent':60}},{'allocation':{'manual':True,'owner_amount':10,'britsmaid_amount':10}}])
async def test_invalid_inputs_do_not_create_expense(ctx,patch):
    month=await seed(ctx); b=body(ctx,month); b.update(patch)
    assert (await ctx['client'].post('/api/expenses',headers=auth(ctx),json=b)).status_code==422
    assert await ctx['db'].expenses.count_documents({})==0

@pytest.mark.asyncio
async def test_misc_is_shown_once_and_edit_cannot_move_property(ctx):
    month=await seed(ctx); c=ctx['client'];
    await ctx['db'].bookings.update_one({'_id':ObjectId(ctx['bid'])},{'$set':{'financials':calculate(10000,{'misc_amount':100,'misc_title':'Linen'})}})
    entries=(await c.get('/api/expenses?property_id='+ctx['p1'],headers=auth(ctx,'owner'))).json()
    assert len(entries)==1 and entries[0]['booking_id']==ctx['bid']
    b=body(ctx,month); e=(await c.post('/api/expenses',headers=auth(ctx),json=b)).json()
    assert (await c.put('/api/expenses/'+e['id'],headers=auth(ctx),json=dict(b,property_id=ctx['p2'],revision=0,change_reason='Move'))).status_code==422
    s=(await c.get(f"/api/reports/settlement?property_id={ctx['p1']}&month={month}",headers=auth(ctx,'owner'))).json()
    assert s['net_revenue']==9900 and s['expense_before_total']==100 and len(s['deduction_items'])==2

@pytest.mark.asyncio
async def test_edit_reclassifies_once_and_preserves_report_and_attachment(ctx):
    month=await seed(ctx); c=ctx['client']; mid=ObjectId()
    await ctx['db'].media.insert_one({'_id':mid,'is_deleted':False,'kind':'image','owner_id':str(ctx['users']['admin']['_id']),'storage_path':'fake'})
    b=body(ctx,month,'before_split'); b['media_ids']=[str(mid)]
    e=(await c.post('/api/expenses',headers=auth(ctx),json=b)).json()
    report=(await c.post('/api/owner-reports',headers=auth(ctx),json={'property_id':ctx['p1'],'month':month})).json()
    update=dict(b,treatment='after_split',allocation={'owner_percent':50,'britsmaid_percent':50},revision=0,change_reason='Shared cost after split',media_ids=[])
    r=await c.put('/api/expenses/'+e['id'],headers=auth(ctx),json=update); assert r.status_code==200,r.text
    current=(await c.get(f"/api/reports/settlement?property_id={ctx['p1']}&month={month}",headers=auth(ctx,'owner'))).json()
    assert current['expense_before_total']==0 and current['owner_payout']==6370
    saved=await ctx['db'].owner_reports.find_one({'share_token':report['share_token']})
    assert saved['settlement']['owner_payout']==6174
    assert saved['settlement']['deduction_items'][0]['media_ids']==[str(mid)]
    assert (await c.post(f'/api/files/{mid}/ticket',headers=auth(ctx,'owner'))).status_code==200
    assert (await c.post(f'/api/files/{mid}/ticket',headers=auth(ctx,'other_owner'))).status_code==404
    rows=(await c.get('/api/expenses?property_id='+ctx['p1'],headers=auth(ctx,'owner'))).json()
    assert 'change_history' not in rows[0]

@pytest.mark.asyncio
async def test_legacy_expense_keeps_old_policy_until_explicitly_changed(ctx):
    month=await seed(ctx); c=ctx['client']; eid=ObjectId()
    await ctx['db'].bookings.update_one({'_id':ObjectId(ctx['bid'])},{'$unset':{'financials':''}})
    await ctx['db'].expenses.insert_one({'_id':eid,'property_id':ctx['p1'],'month':month,'type':'electricity','amount':1000,'notes':'Owner already paid'})
    e=(await c.get('/api/expenses?property_id='+ctx['p1'],headers=auth(ctx,'owner'))).json()[0]
    assert e['treatment']=='reference' and e['owner_amount']==0
    edit=dict(e,amount=1200,revision=0,change_reason='Correct the reference bill')
    r=await c.put('/api/expenses/'+str(eid),headers=auth(ctx),json=edit); assert r.status_code==200,r.text
    s=(await c.get(f"/api/reports/settlement?property_id={ctx['p1']}&month={month}",headers=auth(ctx,'owner'))).json()
    assert s['owner_payout']==6860 and s['owner_tds']==140 and s['expense_reference_total']==1200
