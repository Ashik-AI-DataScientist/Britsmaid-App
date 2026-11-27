"""Synthetic finance/attachment regressions; never contacts production services."""
import copy
from bson import ObjectId
import pytest
from fastapi import HTTPException
from test_role_security_local import ctx, auth, server
from booking_finance import calculate, allocate


def detail():
    return {'gst_included': True, 'gst': {'percent': 5}, 'platform_fee': {'percent': 10},
            'platform_tax': {'percent': 1}, 'misc_amount': 100, 'misc_title': 'Linen'}


def test_inclusive_exclusive_percent_bases_and_manual_overrides():
    f = calculate(10500, detail())
    assert [f['gst']['amount'], f['platform_fee']['amount'], f['platform_tax']['amount'], f['net_revenue']] == [500, 1000, 100, 8800]
    d = detail(); d['gst_included'] = False
    assert calculate(10000, d)['net_revenue'] == 8800
    d = detail(); d['platform_fee'] = {'percent': 10, 'manual': True, 'amount': 950}
    assert calculate(10500, d)['net_revenue'] == 8850
    assert calculate(21000, d)['platform_fee']['amount'] == 950
    d['platform_fee']['manual'] = False
    assert calculate(21000, d)['platform_fee']['amount'] == 2000
    d['platform_fee']['base'] = 'gross'
    assert calculate(10500, d)['platform_fee']['amount'] == 1050


def test_reject_over_deductions_missing_title_and_unbalanced_expenses():
    for d in [dict(detail(), misc_amount=20000), dict(detail(), misc_title='')]:
        with pytest.raises(HTTPException): calculate(10500, d)
    with pytest.raises(HTTPException):
        allocate(100, {'owner_percent': 50, 'britsmaid_percent': 60})
    with pytest.raises(HTTPException):
        allocate(100, {'owner_percent': 50, 'britsmaid_percent': 50, 'manual': True, 'owner_amount': 40, 'britsmaid_amount': 40})
    assert allocate(.03, {'owner_percent': 50, 'britsmaid_percent': 50})['owner_amount'] == .02


async def save_finance(ctx):
    b = (await ctx['client'].get('/api/bookings/' + ctx['bid'], headers=auth(ctx))).json()
    b.update(amount=10500, financials=detail(), revision=0)
    result = await ctx['client'].put('/api/bookings/' + ctx['bid'], headers=auth(ctx), json=b)
    assert result.status_code == 200, result.text
    return result.json()


@pytest.mark.asyncio
async def test_tds_after_all_expenses_reports_and_owner_access(ctx):
    b = await save_finance(ctx)
    client = ctx['client']; month = b['check_in'][:7]
    mid = ObjectId()
    await ctx['db'].media.insert_one({'_id': mid, 'owner_id': str(ctx['users']['admin']['_id']), 'is_deleted': False, 'storage_path': 'fake', 'content_type': 'image/jpeg'})
    expense = {'property_id': ctx['p1'], 'month': month, 'type': 'electricity', 'amount': 1000, 'title': 'Electricity', 'notes': '<script>unsafe</script>',
               'allocation': {'owner_percent': 60, 'britsmaid_percent': 40}, 'media_ids': [str(mid)], 'request_key': 'synthetic-expense-key'}
    first = await client.post('/api/expenses', headers=auth(ctx), json=expense)
    again = await client.post('/api/expenses', headers=auth(ctx), json=expense)
    assert first.status_code == again.status_code == 200
    assert first.json()['id'] == again.json()['id']
    url = f'/api/reports/settlement?property_id={ctx["p1"]}&month={month}'
    s = (await client.get(url, headers=auth(ctx, 'owner'))).json()
    assert s['net_revenue'] == 8800
    assert s['owner_share'] == 6160
    assert s['owner_before_tds'] == 5560
    assert s['owner_tds'] == 111.20
    assert s['owner_payout'] == 5448.80
    assert s['britsmaid_net'] == 2240
    assert s['deduction_items'][0]['media_ids'] == [str(mid)]
    assert (await client.post(f'/api/files/{mid}/ticket', headers=auth(ctx, 'owner'))).status_code == 200
    for role in ['other_owner', 'cleaner', 'supervisor']:
        assert (await client.post(f'/api/files/{mid}/ticket', headers=auth(ctx, role))).status_code == 404
    report = (await client.post('/api/owner-reports', headers=auth(ctx), json={'property_id': ctx['p1'], 'month': month})).json()
    html = (await client.get('/api/public/reports/' + report['share_token'])).text
    assert 'Owner TDS (2%)' in html and '111.20' in html and '5,448.80' in html
    assert '<script>unsafe</script>' not in html
    assert (await client.get(f'/api/public/reports/{report["share_token"]}/media/{mid}')).status_code == 200
    assert (await client.get(f'/api/public/reports/wrong/media/{mid}')).status_code == 404
    payout = await client.post('/api/payouts', headers=auth(ctx), json={'property_id': ctx['p1'], 'month': month, 'amount': 5448.8, 'paid_on': b['check_in']})
    assert payout.status_code == 200, payout.text
    assert payout.json()['owner_tds'] == 111.2
    ota = (await client.get('/api/reports/ota?month=' + month, headers=auth(ctx))).json()
    assert ota['rows'][0]['net'] == 8800


@pytest.mark.asyncio
async def test_financial_revision_validation_legacy_and_expense_scope(ctx):
    b = await save_finance(ctx)
    client = ctx['client']
    stale = copy.deepcopy(b); stale['revision'] = 0
    assert (await client.put('/api/bookings/' + ctx['bid'], headers=auth(ctx), json=stale)).status_code == 409
    invalid = copy.deepcopy(b); invalid['financials']['misc_amount'] = 50000
    assert (await client.put('/api/bookings/' + ctx['bid'], headers=auth(ctx), json=invalid)).status_code == 422
    for role in ['owner', 'cleaner', 'supervisor']:
        assert (await client.put('/api/bookings/' + ctx['bid'], headers=auth(ctx, role), json=b)).status_code == 403
    invalid = copy.deepcopy(b); invalid['financials']['gst']['percent'] = -1
    assert (await client.put('/api/bookings/' + ctx['bid'], headers=auth(ctx), json=invalid)).status_code == 422
    del b['financials']
    kept = await client.put('/api/bookings/' + ctx['bid'], headers=auth(ctx), json=b)
    assert kept.status_code == 200 and kept.json()['financials']['net_revenue'] == 8800
    assert (await client.get('/api/bookings/' + ctx['bid'], headers=auth(ctx, 'other_owner'))).status_code == 404


@pytest.mark.asyncio
async def test_negative_owner_balance_has_no_tds(ctx):
    b = await save_finance(ctx)
    r = await ctx['client'].post('/api/expenses', headers=auth(ctx), json={'property_id': ctx['p1'], 'month': b['check_in'][:7], 'type': 'other', 'amount': 10000})
    assert r.status_code == 200
    s = (await ctx['client'].get(f'/api/reports/settlement?property_id={ctx["p1"]}&month={b["check_in"][:7]}', headers=auth(ctx))).json()
    assert s['owner_before_tds'] == -3840 and s['owner_tds'] == 0 and s['owner_payout'] == -3840
