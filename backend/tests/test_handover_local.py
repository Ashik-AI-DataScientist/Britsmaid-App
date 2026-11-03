"""Handover regressions. Isolated Mongo mock, synthetic calendars, no live writes."""
import hashlib
from datetime import date
from bson import ObjectId
import pytest
from test_role_security_local import ctx, auth, server


async def imported(ctx):
    url = "https://example.invalid/feed.ics"
    uid = hashlib.sha256(url.encode()).hexdigest()[:16] + ":test-event"
    await ctx["db"].bookings.update_one({"_id": ObjectId(ctx["bid"])}, {"$set": {
        "source": "ical", "ical_uid": uid, "ota": "Airbnb", "notes": "Admin entered bill", "ota_commission": 100}})
    prop = await ctx["db"].properties.find_one({"_id": ObjectId(ctx["p1"])})
    prop["ical_feeds"] = [{"ota": "Airbnb", "url": url}]
    return prop


@pytest.mark.asyncio
@pytest.mark.parametrize("summary,cancelled", [("Airbnb (Not available)", False), ("Reserved", True), ("Other guest", False)])
async def test_calendar_cannot_overwrite_entered_booking(ctx, monkeypatch, summary, cancelled):
    prop = await imported(ctx)
    before = await ctx["db"].bookings.find_one({"_id": ObjectId(ctx["bid"])})
    monkeypatch.setattr(server, "fetch_calendar", lambda _: "synthetic")
    monkeypatch.setattr(server, "parse_ical", lambda _: [{"uid": "test-event", "summary": summary,
        "check_in": before["check_in"], "check_out": before["check_out"], "cancelled": cancelled}])
    for _ in range(3):
        assert (await server.sync_property(prop))[0]["conflicts"] == 1
    after = await ctx["db"].bookings.find_one({"_id": before["_id"]})
    for key in ("amount", "ota_commission", "notes", "guest_name", "status", "check_in", "check_out"):
        assert after[key] == before[key]
    assert after["calendar_review_required"]
    response = await ctx["client"].get(f'/api/reports/settlement?property_id={ctx["p1"]}&month={before["check_in"][:7]}', headers=auth(ctx, "owner"))
    assert response.status_code == 200, response.text
    assert response.json()["gross"] == 1000
    assert response.json()["ota_commission"] == 100
    assert response.json()["bookings"][0]["id"] == ctx["bid"]


@pytest.mark.asyncio
async def test_admin_save_protects_zero_amount_import_and_stale_save_rejected(ctx):
    await imported(ctx)
    await ctx["db"].bookings.update_one({"_id": ObjectId(ctx["bid"])}, {"$set": {"amount": 0, "ota_commission": 0}})
    body = (await ctx["client"].get('/api/bookings/' + ctx["bid"], headers=auth(ctx))).json()
    body["revision"] = 0
    body["notes"] = "Intentionally complimentary booking"
    first = await ctx["client"].put('/api/bookings/' + ctx["bid"], headers=auth(ctx), json=body)
    assert first.status_code == 200, first.text
    assert first.json()["manual_protected"]
    assert (await ctx["client"].put('/api/bookings/' + ctx["bid"], headers=auth(ctx), json=body)).status_code == 409
    assert await ctx["db"].booking_history.count_documents({"booking_id": ctx["bid"]}) == 1


@pytest.mark.asyncio
async def test_deduction_arithmetic_notes_scope_and_soft_delete(ctx):
    month = date.today().isoformat()[:7]
    await ctx["db"].bookings.update_one({"_id": ObjectId(ctx["bid"])}, {"$set": {"ota": "Direct", "amount": 10000, "ota_commission": 1000}})
    async def add(kind, amount, title, notes):
        return await ctx["client"].post('/api/expenses', headers=auth(ctx), json={"property_id": ctx["p1"], "month": month, "type": kind, "amount": amount, "title": title, "notes": notes})
    shared = await add("pre_split", 1000, "Replacement linen", "Agreed shared property cost")
    assert shared.status_code == 200, shared.text
    assert (await add("other", 300, "Owner purchase", "Requested by owner")).status_code == 200
    url = f'/api/reports/settlement?property_id={ctx["p1"]}&month={month}'
    admin = (await ctx["client"].get(url, headers=auth(ctx))).json()
    owner = (await ctx["client"].get(url, headers=auth(ctx, "owner"))).json()
    assert admin == owner
    assert owner["net_revenue"] == 8000
    assert owner["owner_share"] == 5600
    assert owner["owner_payout"] == 5300
    assert owner["britsmaid_net"] == 2400
    assert owner["deduction_items"][0]["notes"] == "Agreed shared property cost"
    assert (await ctx["client"].get(url, headers=auth(ctx, "other_owner"))).status_code == 404
    assert (await add("pre_split", 10, "", "")).status_code == 422
    assert (await add("pre_split", -1, "Bad", "Bad")).status_code == 422
    await ctx["client"].delete('/api/expenses/' + shared.json()["id"], headers=auth(ctx))
    assert (await ctx["db"].expenses.find_one({"_id": ObjectId(shared.json()["id"])}))["is_deleted"]
    assert (await ctx["client"].get(url, headers=auth(ctx))).json()["net_revenue"] == 9000


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["owner", "cleaner", "supervisor"])
async def test_nonadmin_cannot_change_deductions_or_accounts(ctx, role):
    body = {"property_id": ctx["p1"], "month": "2026-11", "type": "pre_split", "amount": 10, "title": "Cost", "notes": "Explained"}
    assert (await ctx["client"].post('/api/expenses', headers=auth(ctx, role), json=body)).status_code == 403
    assert (await ctx["client"].post('/api/users', headers=auth(ctx, role), json={})).status_code == 403


@pytest.mark.asyncio
async def test_username_phone_email_login_and_access_revocation(ctx):
    await ctx["db"].users.create_index("email", unique=True, sparse=True)
    await ctx["db"].users.create_index("phone_login", unique=True, sparse=True)
    await ctx["db"].users.create_index("username_login", unique=True, sparse=True)
    body = {"name": "Synthetic owner", "username": "owner.one", "phone": "+91 98765 43210", "password": "Synthetic-Only-2026!", "role": "owner", "property_ids": [ctx["p1"]]}
    created = await ctx["client"].post('/api/users', headers=auth(ctx), json=body)
    assert created.status_code == 200, created.text
    uid = created.json()["id"]
    for login in ("OWNER.ONE", "9876543210", "+919876543210"):
        response = await ctx["client"].post('/api/auth/login', json={"email": login, "password": body["password"]})
        assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    assert (await ctx["client"].post('/api/users', headers=auth(ctx), json={**body, "username": "other.name"})).status_code == 409
    second = await ctx["client"].post('/api/users', headers=auth(ctx), json={**body, "username": "second.owner", "phone": "", "property_ids": [ctx["p2"]]})
    assert second.status_code == 200, second.text
    result = await ctx["client"].put('/api/users/' + uid, headers=auth(ctx), json={"property_ids": [ctx["p2"]]})
    assert result.status_code == 200, result.text
    assert (await ctx["client"].get('/api/auth/me', headers={"Authorization": "Bearer " + token})).status_code == 401
    bad = await ctx["client"].post('/api/auth/login', json={"email": "owner.one", "password": "Wrong"})
    assert bad.status_code == 401


@pytest.mark.asyncio
async def test_legacy_shared_contact_phone_never_selects_arbitrary_user(ctx):
    for role in ("owner", "other_owner"):
        await ctx["db"].users.update_one({"_id": ctx["users"][role]["_id"]}, {"$set": {"phone": "+919876543210", "password_hash": server.hash_pw("Synthetic-Only-2026!")}})
    result = await ctx["client"].post('/api/auth/login', json={"email": "9876543210", "password": "Synthetic-Only-2026!"})
    assert result.status_code == 401


@pytest.mark.asyncio
async def test_expense_retry_no_duplicate_and_report_snapshot_preserves_notes(ctx):
    month = date.today().isoformat()[:7]
    await ctx["db"].bookings.update_one({"_id": ObjectId(ctx["bid"])}, {"$set": {"ota": "Direct"}})
    body = {"property_id": ctx["p1"], "month": month, "type": "pre_split", "amount": 100,
        "title": "Linen <script>bad()</script>", "notes": "Owner & manager agreed", "request_key": "synthetic-retry-123"}
    first = await ctx["client"].post('/api/expenses', headers=auth(ctx), json=body)
    second = await ctx["client"].post('/api/expenses', headers=auth(ctx), json=body)
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert await ctx["db"].expenses.count_documents({}) == 1
    assert (await ctx["client"].post('/api/expenses', headers=auth(ctx), json={**body, "amount": 101})).status_code == 409
    report = await ctx["client"].post('/api/owner-reports', headers=auth(ctx), json={"property_id": ctx["p1"], "month": month})
    assert report.status_code == 200, report.text
    token = report.json()["share_token"]
    await ctx["client"].delete('/api/expenses/' + first.json()["id"], headers=auth(ctx))
    page = await ctx["client"].get('/api/public/reports/' + token)
    assert page.status_code == 200, page.text
    assert 'Linen &lt;script&gt;bad()&lt;/script&gt;' in page.text
    assert 'Owner &amp; manager agreed' in page.text
    assert '<script>bad()</script>' not in page.text
    assert (await ctx["client"].post('/api/expenses', headers=auth(ctx), json=body)).status_code == 409


@pytest.mark.asyncio
async def test_booking_review_admin_only_and_preserves_earlier_values(ctx):
    await ctx["db"].bookings.update_one({"_id": ObjectId(ctx["bid"])}, {"$set": {"status": "blocked"}})
    rows = await ctx["client"].get('/api/system/booking-integrity', headers=auth(ctx))
    assert rows.status_code == 200
    assert rows.json()[0]["id"] == ctx["bid"]
    assert rows.json()[0]["amount"] == 1000
    for role in ("owner", "cleaner", "supervisor"):
        assert (await ctx["client"].get('/api/system/booking-integrity', headers=auth(ctx, role))).status_code == 403
