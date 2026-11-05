"""Synthetic report presentation/access tests. No live database, records or storage."""
import copy
from decimal import Decimal, ROUND_HALF_UP
from bson import ObjectId
import pytest
from test_role_security_local import ctx, auth, server
from report_presentation import report_presentation, public_payout_sections


def cents(n):
    return float(Decimal(str(n)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))


def statement(before=4000, after=2000, owner_percent=50):
    owner_cost = cents(after * owner_percent / 100)
    net = 84000 - before
    allocated = cents(net * .7)
    balance = cents(allocated - owner_cost)
    tds = cents(max(0, balance) * .02)
    entries = [None, {'amount': None}, {'amount': 0, 'title': 'Empty'}]
    if before:
        entries.append(dict(id='before', type='pre_split', treatment='before_split', title='Repair', amount=before, notes='Common cost'))
    if after:
        entries.append(dict(id='after', type='other', treatment='after_split', title='Electricity', amount=after, notes='Shared cost',
            allocation=dict(owner_amount=owner_cost, britsmaid_amount=cents(after-owner_cost), owner_percent=owner_percent, britsmaid_percent=100-owner_percent)))
    return dict(property_name='Sample', owner_name='Sample owner', month='2026-11', gross=100000, ota_commission=10000, gst_total=5000, platform_tax=1000,
        pre_split_deductions=before, booking_misc=0, expense_before_total=before, expense_after_total=after, expense_reference_total=0,
        owner_after_expenses=owner_cost, britsmaid_after_expenses=cents(after-owner_cost), net_revenue=net, owner_share=allocated, britsmaid_share=cents(net-allocated),
        owner_share_percent=70, britsmaid_share_percent=30, owner_before_tds=balance, owner_tds=tds, owner_tds_percent=2,
        owner_payout=cents(balance-tds), britsmaid_net=cents(net-allocated-after+owner_cost), deduction_items=entries, by_ota=[], bookings=[], nights=0, occupancy_percent=0)


@pytest.mark.parametrize('before', [0, .01, .03, 4000, 100000])
@pytest.mark.parametrize('after', [0, .01, .03, 2000, 100000])
@pytest.mark.parametrize('share', [0, 30, 50, 100])
def test_summary_uses_full_expenses_without_changing_payout(before, after, share):
    s = statement(before, after, share)
    original = copy.deepcopy(s)
    p, calculation, expenses, bm = public_payout_sections(s, server.inr, 'sample-token')
    assert s == original
    assert p['totalExpenses'] == cents(before+after)
    assert p['ownerAfter'] == s['owner_after_expenses']
    assert p['bmAfter'] == s['britsmaid_after_expenses']
    assert p['bookingDeductions'] == 16000
    assert len(p['groups']) == int(before > 0) + int(after > 0)
    assert ('Expenses before revenue split' in calculation) == (before > 0)
    assert ('Before revenue split' in expenses) == (before > 0)
    assert ('Owner expenses after split' in calculation) == (s['owner_after_expenses'] > 0)
    assert ('Britsmaid expenses after split' in bm) == (s['britsmaid_after_expenses'] > 0)
    assert 'Platform tax' not in calculation and 'Other tax deductions' in calculation
    assert server.inr(s['owner_payout']) in calculation
    assert cents(s['owner_payout']+s['owner_tds']+s['britsmaid_net']+p['totalExpenses']+p['bookingDeductions']) == s['gross']


def test_saved_expenses_reference_and_missing_detail_are_explained():
    s = statement(4000, 2000)
    s['deduction_items'] = []
    p = report_presentation(s)
    assert [g['total'] for g in p['groups']] == [4000, 2000]
    assert all(g['items'][0]['summary'] for g in p['groups'])
    assert all('older report' in g['items'][0]['notes'] for g in p['groups'])
    s['expense_reference_total'] = 900
    p, calculation, expenses, bm = public_payout_sections(s, server.inr, 'sample')
    assert p['totalExpenses'] == 6900
    assert 'Reference only' in expenses and 'Reference only' not in calculation
    assert s['owner_payout'] == 53900


def test_saved_total_mismatch_is_visible_and_source_is_immutable():
    s = statement(4000, 2000)
    s['expense_before_total'] = 1000
    before = copy.deepcopy(s)
    p, calculation, expenses, bm = public_payout_sections(s, server.inr, 'sample')
    assert p['groups'][0]['mismatch']
    assert 'differ from the available details' in calculation
    assert s == before


@pytest.mark.parametrize('mode,owner,bm,kind', [('owner',0,0,'reference'), ('split_half',500,500,'after_split')])
def test_legacy_electricity_keeps_saved_treatment(mode, owner, bm, kind):
    s = dict(electricity_total=1000,electricity_mode=mode,owner_electricity=owner,britsmaid_electricity=bm,other_deductions=0)
    p = report_presentation(s)
    assert p['groups'][0]['key'] == kind
    assert p['totalExpenses'] == 1000 and p['ownerAfter'] == owner


def test_html_escapes_expenses_and_loads_evidence_only_on_click():
    s = statement()
    s['deduction_items'][-1].update(title='<script>bad()</script>', notes='A & B <img src=x onerror=bad()>', media_ids=['123456789012345678901234'])
    p, calculation, expenses, bm = public_payout_sections(s, server.inr, 'sample-token')
    assert '<script>bad()</script>' not in expenses and '&lt;script&gt;' in expenses
    assert '<img ' not in expenses and '<a href="/api/public/reports/sample-token/media/' in expenses
    assert 'Edit expense' not in expenses and '<form' not in expenses


@pytest.mark.asyncio
@pytest.mark.parametrize('method,path,payload', [
    ('POST','/expenses', {'month':'2026-11','amount':1}),
    ('PUT','/expenses/{id}',{'month':'2026-11','amount':1}),
    ('DELETE','/expenses/{id}',{}),
    ('PUT','/bookings/{id}',{}),('DELETE','/bookings/{id}',{}),
    ('POST','/owner-reports',{'month':'2026-11'}),('DELETE','/owner-reports/{id}',{}),
    ('POST','/payouts',{'month':'2026-11','amount':1,'paid_on':'2026-11-01'}),('DELETE','/payouts/{id}',{}),
    ('POST','/invoices',{}),('PUT','/invoices/{id}/status',{'status':'paid'}),('DELETE','/invoices/{id}',{}),
])
async def test_owner_cannot_write_financial_records_or_documents(ctx, method, path, payload):
    response = await ctx['client'].request(method, '/api'+path.format(id=ctx['bid']), headers=auth(ctx,'owner'), json=dict(payload,property_id=ctx['p1']))
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_owner_cannot_upload_replacement_documents(ctx):
    response = await ctx['client'].post('/api/upload', headers=auth(ctx,'owner'), files={'file':('fake.jpg',b'fake','image/jpeg')})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_new_and_saved_reports_keep_scope_and_financial_values(ctx):
    await ctx['db'].bookings.update_one({'_id':ObjectId(ctx['bid'])},{'$set':{'ota':'Direct'}})
    book = await ctx['db'].bookings.find_one({'_id':ObjectId(ctx['bid'])})
    body = {'property_id':ctx['p1'],'month':book['check_in'][:7]}
    report = await ctx['client'].post('/api/owner-reports',headers=auth(ctx),json=body)
    assert report.status_code == 200, report.text
    data = report.json()
    before = copy.deepcopy(await ctx['db'].owner_reports.find_one({'_id':ObjectId(data['id'])}))
    for _ in range(2):
        public = await ctx['client'].get('/api/public/reports/'+data['share_token'])
        assert public.status_code == 200, public.text
        assert 'How the payout is calculated' in public.text and 'Your payout' not in public.text
        assert 'Expenses before revenue split' not in public.text and '<h2>Expenses</h2>' not in public.text
        assert (await ctx['client'].get('/api/owner-reports/'+data['id'],headers=auth(ctx,'owner'))).status_code == 200
        assert (await ctx['client'].get('/api/owner-reports/'+data['id'],headers=auth(ctx,'other_owner'))).status_code == 404
    assert await ctx['db'].owner_reports.find_one({'_id':ObjectId(data['id'])}) == before
