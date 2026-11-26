"""Invitation regressions: local fake DB/storage only, no live accounts."""
import asyncio
from urllib.parse import urlsplit, parse_qs
import pytest
from bson import ObjectId
from test_role_security_local import ctx, auth, server, upload_id


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
    # Creating a replacement invitation intentionally revokes the previous link.
    fresh = (await c.post(f'/api/bookings/{bid}/guest-link', headers=auth(ctx))).json()
    assert (await c.get('/api/guest/check-in', headers=guest)).status_code == 401
    assert len((await c.get('/api/guest/check-in', headers={'Authorization':'Bearer '+fresh['token']})).json()['documents']) == 5
