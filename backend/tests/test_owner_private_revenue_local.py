"""Owner privacy and expense reconciliation with synthetic in-memory records."""
from copy import deepcopy
from datetime import date
import json
from bson import ObjectId
import pytest
from test_role_security_local import ctx, auth, server
from owner_finance import owner_statement, owner_allocation


async def seed(ctx):
    day=date.today().isoformat()
    private=dict(id='private-revenue-0001',title='PRIVATE-BRITSMAID-SERVICE',amount=1234,tax=24,fee=10,owner_percent=80,owner_amount=0,service_date=day,status='received',notes='PRIVATE-NOTE')
    shared=dict(id='shared-revenue-0001',title='Owner shared add-on',amount=100,tax=0,fee=0,owner_percent=50,owner_amount=None,service_date=day,status='received',notes='Shared service')
    await ctx['db'].bookings.update_one({'_id':ObjectId(ctx['bid'])},{'$set':{'ota':'Direct','additional_revenue':[private,shared],'revenue_history':[{'before':private,'after':shared}]}})
    return private,shared


@pytest.mark.asyncio
async def test_owner_booking_lists_and_detail_do_not_expose_private_revenue_or_history(ctx):
    await seed(ctx)
    c=ctx['client']
    for path in ['/api/bookings','/api/bookings/'+ctx['bid']]:
        owner=await c.get(path,headers=auth(ctx,'owner'))
        assert owner.status_code==200
        assert 'PRIVATE-' not in owner.text and 'revenue_history' not in owner.text
        assert 'Owner shared add-on' in owner.text
        assert 'PRIVATE-BRITSMAID-SERVICE' in (await c.get(path,headers=auth(ctx))).text


@pytest.mark.asyncio
async def test_owner_totals_insights_and_pdf_audience_exclude_zero_allocation(ctx):
    await seed(ctx)
    c=ctx['client'];month=date.today().isoformat()[:7]
    url='/api/reports/settlement?property_id='+ctx['p1']+'&month='+month
    admin=(await c.get(url,headers=auth(ctx))).json()
    owner=(await c.get(url,headers=auth(ctx,'owner'))).json()
    safe_pdf=(await c.get(url+'&audience=owner',headers=auth(ctx))).json()
    assert admin['gross']==2334 and owner['gross']==1100
    assert owner['net_revenue']==1100 and owner['owner_share']==750
    for key in ['owner_share','owner_before_tds','owner_tds','owner_payout']:
        assert owner[key]==admin[key]
    assert owner['gross']==safe_pdf['gross']
    assert 'PRIVATE-' not in json.dumps(owner) and 'PRIVATE-' not in json.dumps(safe_pdf)
    assert owner['additional_totals']==dict(gross=100,deductions=0,net=100,owner=50,britsmaid=50)
    extra=[r for r in owner['by_ota'] if r['ota']=='Additional revenue'][0]
    assert extra['gross']==100 and extra['net']==100
    day=date.today().isoformat()
    insight='/api/reports/insights?start='+day+'&end='+day+'&interval=day&property_id='+ctx['p1']
    assert (await c.get(insight,headers=auth(ctx,'owner'))).json()['points'][0]['gross']==1100
    assert (await c.get(insight,headers=auth(ctx))).json()['points'][0]['gross']==2334
    dashboard=(await c.get('/api/owner/dashboard',headers=auth(ctx,'owner'))).json()
    assert dashboard['villas'][0]['month_gross']==1100


@pytest.mark.asyncio
async def test_saved_reports_public_links_and_receipts_are_safe_without_rewriting_storage(ctx):
    await seed(ctx)
    c=ctx['client'];month=date.today().isoformat()[:7]
    report=await c.post('/api/owner-reports',headers=auth(ctx),json={'property_id':ctx['p1'],'month':month,'title':'Synthetic owner report','condition_notes':'All good','media_ids':[]})
    assert report.status_code==200,report.text
    r=report.json();stored=await ctx['db'].owner_reports.find_one({'_id':ObjectId(r['id'])})
    assert 'PRIVATE-BRITSMAID-SERVICE' in json.dumps(stored['settlement'])
    original=deepcopy(stored)
    for role in ['admin','owner']:
        for path in ['/api/owner-reports','/api/owner-reports/'+r['id']]:
            value=await c.get(path,headers=auth(ctx,role))
            assert value.status_code==200 and 'PRIVATE-' not in value.text
    public=await c.get('/api/public/reports/'+r['share_token'])
    assert public.status_code==200 and 'PRIVATE-' not in public.text
    assert 'Owner shared add-on' in public.text
    assert await ctx['db'].owner_reports.find_one({'_id':stored['_id']})==original
    payment=await c.post('/api/payouts',headers=auth(ctx),json={'property_id':ctx['p1'],'month':month,'amount':735,'paid_on':date.today().isoformat(),'method':'Bank transfer'})
    assert payment.status_code==200,payment.text
    saved=deepcopy(await ctx['db'].payouts.find_one({'_id':ObjectId(payment.json()['id'])}))
    assert 'PRIVATE-BRITSMAID-SERVICE' in json.dumps(saved['additional_revenue'])
    for role in ['admin','owner']:
        receipt=await c.get('/api/payouts?property_id='+ctx['p1'],headers=auth(ctx,role))
        assert 'PRIVATE-' not in receipt.text and receipt.json()[0]['gross']==1100
    assert await ctx['db'].payouts.find_one({'_id':saved['_id']})==saved


@pytest.mark.parametrize('values',[{'owner_percent':0},{'owner_percent':80,'owner_amount':0},{'amount':.01,'owner_percent':.01},{'tax':100,'owner_percent':70}])
@pytest.mark.parametrize('status',['received','pending','refunded'])
def test_effective_zero_share_and_status_boundaries_are_hidden(values,status):
    item=dict(id='private-entry',title='PRIVATE',amount=100,tax=0,fee=0,owner_percent=0,owner_amount=None,status=status,service_date='2026-11-01',**{})
    item.update(values)
    assert owner_allocation(item)==0
    from additional_revenue import revenue_totals
    total=revenue_totals([item])
    source=dict(additional_revenue=[item],additional_totals=total,gross=total['gross'],net_revenue=total['net'],britsmaid_share=total['britsmaid'],britsmaid_net=total['britsmaid'])
    original=deepcopy(source);visible=owner_statement(source)
    assert visible['additional_revenue']==[] and visible['gross']==0 and visible['net_revenue']==0
    assert source==original and owner_statement(visible)==visible


@pytest.mark.asyncio
@pytest.mark.parametrize('owner_percent',[0,25,100])
async def test_expense_registration_retry_and_owner_deductions_reconcile(ctx,owner_percent):
    await seed(ctx)
    c=ctx['client'];month=date.today().isoformat()[:7]
    url='/api/reports/settlement?property_id='+ctx['p1']+'&month='+month
    before=(await c.get(url,headers=auth(ctx))).json()
    payload=dict(property_id=ctx['p1'],month=month,type='other',treatment='after_split',title='Synthetic expense',amount=200,notes='Expense reconciliation check',allocation={'owner_percent':owner_percent,'britsmaid_percent':100-owner_percent},request_key='expense-retry-synthetic')
    first=await c.post('/api/expenses',headers=auth(ctx),json=payload)
    assert first.status_code==200,first.text
    again=await c.post('/api/expenses',headers=auth(ctx),json=payload)
    assert again.status_code==200 and again.json()['id']==first.json()['id']
    assert await ctx['db'].expenses.count_documents({'property_id':ctx['p1']})==1
    after=(await c.get(url,headers=auth(ctx))).json()
    owner=(await c.get(url,headers=auth(ctx,'owner'))).json()
    owner_cost=200*owner_percent/100
    assert after['owner_before_tds']==before['owner_before_tds']-owner_cost
    assert after['britsmaid_net']==before['britsmaid_net']-(200-owner_cost)
    assert owner['owner_payout']==after['owner_payout']
    assert owner['deduction_items'][0]['amount']==200
