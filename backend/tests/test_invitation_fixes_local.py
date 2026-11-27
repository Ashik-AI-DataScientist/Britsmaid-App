"""Invitation regressions: local fake DB/storage only, no live accounts."""
import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, parse_qs
import pytest
from bson import ObjectId
from test_role_security_local import ctx, auth, server, upload_id
from guest_links import StableGuestLinks, upload_cutoff, INDIA_TZ
import guest_ids


@pytest.mark.asyncio
async def test_invite_verifies_chosen_password_without_changing_credentials(ctx):
    uid = ctx['users']['cleaner']['_id']
    password = 'Chosen-password-123!'
    await ctx['db'].users.update_one({'_id': uid}, {'$set': {'password_hash': server.hash_pw(password)}})
    before = await ctx['db'].users.find_one({'_id': uid})
    old_session = auth(ctx, 'cleaner')
    endpoint = f'/api/users/{uid}/verify-invite-password'
    for _ in range(3):
        r = await ctx['client'].post(endpoint, headers=auth(ctx), json={'password': password})
        assert r.status_code == 200 and r.json() == {'ok': True}
    assert await ctx['db'].users.find_one({'_id': uid}) == before
    assert (await ctx['client'].get('/api/auth/me', headers=old_session)).status_code == 200
    assert (await ctx['client'].post(endpoint, headers=auth(ctx), json={'password': 'Wrong-password-123'})).status_code == 400
    assert (await ctx['client'].post(f'/api/users/{uid}/reset-password', headers=auth(ctx))).status_code == 422
    assert await ctx['db'].users.find_one({'_id': uid}) == before
    assert server.verify_pw(password, before['password_hash'])
    login = await ctx['client'].post('/api/auth/login', json={'email': before['email'], 'password': password})
    assert login.status_code == 200
    assert (await ctx['client'].post('/api/auth/login', json={'email': before['email'], 'password': 'Wrong-password-123'})).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize('role', ['owner', 'cleaner', 'supervisor'])
async def test_non_admin_cannot_verify_or_reset_member_password(ctx, role):
    uid = ctx['users']['cleaner']['_id']
    for route in ['verify-invite-password', 'reset-password']:
        assert (await ctx['client'].post(f'/api/users/{uid}/{route}', headers=auth(ctx, role), json={'password': 'Chosen-password-123'})).status_code == 403


@pytest.mark.asyncio
async def test_password_verification_missing_deleted_and_invalid_inputs(ctx):
    path = f"/api/users/{ctx['users']['cleaner']['_id']}/verify-invite-password"
    assert (await ctx['client'].post(path, json={'password': 'Chosen-password-123'})).status_code == 401
    for body in [{}, {'password': ''}, {'password': 'short'}, {'password': 'x'*73}]:
        assert (await ctx['client'].post(path, headers=auth(ctx), json=body)).status_code == 422
    assert (await ctx['client'].post(f'/api/users/{ObjectId()}/verify-invite-password', headers=auth(ctx), json={'password': 'Chosen-password-123'})).status_code == 404


@pytest.mark.asyncio
async def test_shared_link_five_guests_stays_scoped_and_only_admin_removes(ctx, monkeypatch):
    # Each pytest fixture has a new event loop, unlike the single production loop.
    # Rebuild middleware so its upload semaphore is bound to this test's loop.
    monkeypatch.setattr(server.app, 'middleware_stack', None)
    c, db, bid = ctx['client'], ctx['db'], ctx['bid']
    monkeypatch.setenv('PUBLIC_APP_URL', 'https://app.britsmaid.in')
    await db.bookings.update_one({'_id': ObjectId(bid)}, {'$set': {'guests': 5}})
    response = await c.post(f'/api/bookings/{bid}/guest-link', headers=auth(ctx))
    link = response.json()
    url = urlsplit(link['url'])
    assert url.scheme == 'https' and url.netloc == 'app.britsmaid.in' and not url.query
    assert parse_qs(url.fragment)['invite'] == [link['token']]
    guest = {'Authorization': 'Bearer ' + link['token']}
    # No app session or login; each request represents another guest's browser.
    assert (await c.get('/api/guest/check-in', headers=guest)).status_code == 200
    uploads = await asyncio.gather(*(upload_id(ctx, guest, n, guest_name=f'Synthetic guest {n}') for n in range(1,6)))
    assert all(r.status_code == 200 for r in uploads), [r.text for r in uploads]
    ids = [r.json()['id'] for r in uploads]
    roster = (await c.get('/api/guest/check-in', headers=guest)).json()
    assert roster['property_name'] == ctx['p1'] and len(roster['documents']) == 5
    assert all(set(row) == {'guest_name', 'guest_number'} for row in roster['documents'])
    docs = await db.guest_ids.find({}).to_list(20)
    assert all(d['booking_id'] == bid and d['property_id'] == ctx['p1'] for d in docs)
    assert (await upload_id(ctx, guest, 1, guest_name='Replacement attempt')).status_code == 409
    for h in [guest, auth(ctx, 'owner'), auth(ctx, 'supervisor'), auth(ctx, 'cleaner')]:
        for method, route in [('GET', f'/guest-ids/{ids[0]}/image'), ('DELETE', f'/guest-ids/{ids[0]}')]:
            assert (await c.request(method, '/api'+route, headers=h)).status_code in (401,403)
    other_bid = ObjectId()
    old = await db.bookings.find_one({'_id': ObjectId(bid)})
    await db.bookings.insert_one({**old, '_id': other_bid, 'property_id': ctx['p2']})
    other = (await c.post(f'/api/bookings/{other_bid}/guest-link', headers=auth(ctx))).json()
    other_guest = {'Authorization': 'Bearer '+other['token']}
    assert (await c.get('/api/guest/check-in', headers=other_guest)).json()['documents'] == []
    assert (await c.get('/api/guest/check-in', headers=guest)).json()['guests'] == 5
    assert (await c.get('/api/guest-ids?booking_id='+bid, headers=auth(ctx))).status_code == 200
    assert (await c.get(f'/api/guest-ids/{ids[0]}/image', headers=auth(ctx))).status_code == 200
    assert (await c.delete(f'/api/guest-ids/{ids[0]}', headers=auth(ctx))).status_code == 200
    assert len((await c.get('/api/guest/check-in', headers=guest)).json()['documents']) == 4
    assert (await upload_id(ctx, guest, 1, guest_name='Corrected guest')).status_code == 200
    assert len((await c.get('/api/guest/check-in', headers=guest)).json()['documents']) == 5
    # Sharing again retains the URL, guest roster and access.
    same = (await c.post(f'/api/bookings/{bid}/guest-link', headers=auth(ctx))).json()
    assert same == link
    # Only explicit replacement revokes previous recipients.
    fresh = (await c.post(f'/api/bookings/{bid}/guest-link', headers=auth(ctx), json={'replace': True, 'note': 'Compromised link'})).json()
    assert (await c.get('/api/guest/check-in', headers=guest)).status_code == 401
    assert len((await c.get('/api/guest/check-in', headers={'Authorization':'Bearer '+fresh['token']})).json()['documents']) == 5


@pytest.mark.asyncio
async def test_stable_token_restart_concurrency_attempts_and_encryption(ctx):
    db, bid = ctx['db'], ctx['bid']
    expiry = upload_cutoff('2026-12-30')
    service = StableGuestLinks(db, server.JWT_SECRET)
    tokens = await asyncio.gather(*(service.get(bid, expiry) for _ in range(12)))
    assert len(set(tokens)) == 1
    record = await db.guest_links.find_one({'booking_id': bid})
    assert tokens[0] not in str(record)
    await db.guest_links.update_one({'_id': record['_id']}, {'$set': {'attempts': 4}})
    assert await StableGuestLinks(db, server.JWT_SECRET).get(bid, expiry) == tokens[0]
    assert (await db.guest_links.find_one({'_id': record['_id']}))['attempts'] == 4
    with pytest.raises(Exception) as failure:
        await StableGuestLinks(db, 'different-key').get(bid, expiry)
    assert failure.value.status_code == 503
    assert await db.guest_links.count_documents({}) == 1
    assert (await db.guest_links.find_one({'_id': record['_id']}))['token_hash'] == record['token_hash']


@pytest.mark.asyncio
async def test_legacy_links_remain_valid_revoked_links_stay_revoked(ctx):
    db, c, bid = ctx['db'], ctx['client'], ctx['bid']
    for token, revoked in [('synthetic-active-legacy', False), ('synthetic-revoked-legacy', True)]:
        await db.guest_links.insert_one({'booking_id': bid, 'token_hash': hashlib.sha256(token.encode()).hexdigest(),
            'revoked': revoked, 'expires_at': '2000-01-01', 'attempts': 0})
    path = f'/api/bookings/{bid}/guest-link'
    first = await c.post(path, headers=auth(ctx))
    assert first.status_code == 200
    for token, expected in [('synthetic-active-legacy', 200), ('synthetic-revoked-legacy', 401)]:
        assert (await c.get('/api/guest/check-in', headers={'Authorization': 'Bearer '+token})).status_code == expected
    await c.delete(path, headers=auth(ctx))
    assert (await c.post(path, headers=auth(ctx))).status_code == 409
    assert (await c.post(path, headers=auth(ctx), json={'replace': True})).status_code == 422
    fresh = await c.post(path, headers=auth(ctx), json={'replace': True, 'note': 'Explicit admin replacement'})
    assert fresh.status_code == 200 and fresh.json()['url'] != first.json()['url']
    for token in ['synthetic-active-legacy', first.json()['token']]:
        assert (await c.get('/api/guest/check-in', headers={'Authorization': 'Bearer '+token})).status_code == 401


@pytest.mark.asyncio
async def test_disable_legacy_only_cannot_silently_reenable(ctx):
    path = f'/api/bookings/{ctx["bid"]}/guest-link'
    await ctx['client'].delete(path, headers=auth(ctx))
    assert (await ctx['client'].post(path, headers=auth(ctx))).status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize('seconds,expected', [(-86401, 200), (-86400, 200), (-1, 200), (0, 401), (1, 401)])
async def test_india_checkout_grace_exact_boundary(ctx, monkeypatch, seconds, expected):
    db, c, bid = ctx['db'], ctx['client'], ctx['bid']
    first = (await c.post(f'/api/bookings/{bid}/guest-link', headers=auth(ctx))).json()
    b = await db.bookings.find_one({'_id': ObjectId(bid)})
    cutoff = datetime.fromisoformat(upload_cutoff(b['check_out']))
    instant = cutoff + timedelta(seconds=seconds)
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)
    monkeypatch.setattr(server, 'datetime', Frozen)
    monkeypatch.setattr(guest_ids, 'datetime', Frozen)
    guest = {'Authorization': 'Bearer '+first['token']}
    assert (await c.get('/api/guest/check-in', headers=guest)).status_code == expected
    uploaded = await upload_id(ctx, guest)
    assert uploaded.status_code == expected
    assert await db.guest_ids.count_documents({}) == (1 if expected == 200 else 0)


def test_date_only_cutoff_month_year_leap_boundaries():
    for checkout, local_end in [('2026-11-30','2026-12-02'), ('2026-12-31','2027-01-02'), ('2028-02-28','2028-03-01')]:
        assert datetime.fromisoformat(upload_cutoff(checkout)).astimezone(INDIA_TZ).isoformat() == local_end+'T00:00:00+05:30'


@pytest.mark.asyncio
async def test_date_edits_cancel_and_checkin_preserve_link_and_ids(ctx):
    c, db, bid = ctx['client'], ctx['db'], ctx['bid']
    path = f'/api/bookings/{bid}/guest-link'
    first = (await c.post(path, headers=auth(ctx))).json()
    guest = {'Authorization': 'Bearer '+first['token']}
    did = (await upload_id(ctx, guest)).json()['id']
    doc = await db.guest_ids.find_one({'_id': ObjectId(did)})
    assert (await c.post(f'/api/bookings/{bid}/guest-admin-action', headers=auth(ctx), json={'action':'check_in','note':'Collect remaining IDs during stay'})).status_code == 200
    assert (await upload_id(ctx, guest, 2)).status_code == 200
    assert (await c.post(path, headers=auth(ctx))).json()['url'] == first['url']
    booking = await db.bookings.find_one({'_id': ObjectId(bid)})
    changed = (datetime.fromisoformat(booking['check_out']) + timedelta(days=1)).date().isoformat()
    await db.bookings.update_one({'_id': ObjectId(bid)}, {'$set': {'check_out': changed}})
    same = (await c.post(path, headers=auth(ctx))).json()
    assert same['url'] == first['url'] and same['expires_at'] == upload_cutoff(changed)
    await db.bookings.update_one({'_id': ObjectId(bid)}, {'$set': {'status':'cancelled'}})
    assert (await c.get('/api/guest/check-in', headers=guest)).status_code == 401
    assert await db.guest_ids.find_one({'_id': ObjectId(did)}) == doc
