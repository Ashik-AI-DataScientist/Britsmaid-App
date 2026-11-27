"""Synthetic regressions for the live-app improvements. No external services."""
import asyncio
from datetime import date, timedelta, datetime, timezone
from bson import ObjectId
from fastapi import HTTPException
import pytest
from test_role_security_local import ctx, auth, server
from service_lease import business_lease
from booking_finance import money, percent_amount
from additional_revenue import RevenueIn, revenue_totals
from test_role_security_local import invitation, jpeg
from pydantic import ValidationError
import io
import base64
import mongomock
from activity import SubscriptionIn
from guest_storage import EncryptedGuestStore
from test_production_services_local import MemoryBackups
from backups import Backups
import guest_ids


def revenue(ctx, **changes):
    return {'id': 'synthetic-revenue-001', 'title': 'Extra guest', 'amount': 1000.03,
            'tax': 50.01, 'fee': 10.01, 'owner_percent': 25.5,
            'service_date': date.today().isoformat(), 'revision': 0, **changes}


@pytest.mark.asyncio
async def test_short_competing_save_waits_and_runs_once(ctx):
    entered = asyncio.Event()
    executions = []

    async def first():
        async with business_lease(ctx['db']):
            entered.set()
            await asyncio.sleep(.15)
            executions.append('first')

    async def second():
        await entered.wait()
        async with business_lease(ctx['db'], wait_seconds=1):
            executions.append('second')

    await asyncio.gather(first(), second())
    assert executions == ['first', 'second']
    assert await ctx['db'].maintenance_locks.count_documents({}) == 0


@pytest.mark.asyncio
async def test_busy_rejects_before_entering_and_expired_lease_recovers(ctx):
    db = ctx['db']
    await db.maintenance_locks.insert_one({'_id': 'media-references', 'owner': 'other',
                                         'until': datetime.now(timezone.utc) + timedelta(minutes=1)})
    with pytest.raises(HTTPException) as exc:
        async with business_lease(db, wait_seconds=.02):
            pytest.fail('Busy operation entered')
    assert exc.value.headers['X-Britsmaid-Error'] == 'WRITE_BUSY'
    await db.maintenance_locks.update_one({'_id': 'media-references'}, {'$set': {
        'until': datetime.now(timezone.utc) - timedelta(seconds=1)}})
    async with business_lease(db):
        pass
    assert await db.maintenance_locks.count_documents({}) == 0


@pytest.mark.asyncio
async def test_blocked_dates_are_unavailable_without_occupancy(ctx):
    db, c = ctx['db'], ctx['client']
    await db.bookings.update_one({'_id': ObjectId(ctx['bid'])}, {'$set': {'status': 'blocked', 'ota': 'Airbnb', 'ota_commission': 0}})
    prop = (await c.get('/api/properties/' + ctx['p1'], headers=auth(ctx))).json()
    assert prop['occupied'] is False and prop['unavailable'] is True
    assert (await c.get('/api/dashboard', headers=auth(ctx))).json()['occupied_today'] == 0
    await db.bookings.update_one({'_id': ObjectId(ctx['bid'])}, {'$set': {'status': 'confirmed'}})
    prop = (await c.get('/api/properties/' + ctx['p1'], headers=auth(ctx))).json()
    assert prop['occupied'] is True and prop['unavailable'] is False
    assert (await c.get('/api/dashboard', headers=auth(ctx))).json()['occupied_today'] == 1
    await db.bookings.update_one({'_id': ObjectId(ctx['bid'])}, {'$set': {'check_out': date.today().isoformat()}})
    assert (await c.get('/api/properties/' + ctx['p1'], headers=auth(ctx))).json()['occupied'] is False


@pytest.mark.asyncio
@pytest.mark.parametrize('role', ['owner', 'other_owner', 'cleaner', 'supervisor'])
async def test_new_business_writes_and_admin_notifications_are_denied(ctx, role):
    c = ctx['client']
    for path, body in [('/bookings/' + ctx['bid'] + '/revenue', revenue(ctx)),
                       ('/bookings/' + ctx['bid'] + '/cancel', {'reason': 'Test', 'revision': 0}),
                       ('/notifications/read', {})]:
        assert (await c.post('/api' + path, headers=auth(ctx, role), json=body)).status_code == 403
    assert (await c.get('/api/notifications', headers=auth(ctx, role))).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize('split', [0, .5, 25.5, 70, 100])
@pytest.mark.parametrize('status', ['received', 'pending', 'refunded'])
async def test_additional_revenue_reconciles_without_changing_rental(ctx, split, status):
    db, c = ctx['db'], ctx['client']
    await db.bookings.update_one({'_id': ObjectId(ctx['bid'])}, {'$set': {'ota': 'Airbnb', 'ota_commission': 100}})
    prop = await db.properties.find_one({'_id': ObjectId(ctx['p1'])})
    month = date.today().isoformat()[:7]
    before = await server.compute_settlement(prop, month)
    body = revenue(ctx, owner_percent=split, status=status)
    r = await c.post('/api/bookings/' + ctx['bid'] + '/revenue', headers=auth(ctx), json=body)
    assert r.status_code == 200, r.text
    again = await c.post('/api/bookings/' + ctx['bid'] + '/revenue', headers=auth(ctx), json=body)
    assert again.status_code == 200 and len(again.json()['additional_revenue']) == 1
    after = await server.compute_settlement(prop, month)
    extra = revenue_totals([body])
    assert after['gross'] == money(before['gross'] + extra['gross'])
    assert after['owner_share'] == money(before['owner_share'] + extra['owner'])
    assert after['owner_tds'] == percent_amount(max(after['owner_before_tds'], 0), 2)
    assert money(after['owner_payout'] + after['owner_tds'] + after['britsmaid_net']) == after['net_revenue']
    saved = await db.bookings.find_one({'_id': ObjectId(ctx['bid'])})
    assert saved['amount'] == 1000 and saved['ota_commission'] == 100
    assert len(saved['revenue_history']) == 1


@pytest.mark.parametrize('changes', [{'amount': 0}, {'amount': -1}, {'amount': float('inf')},
    {'owner_percent': -1}, {'owner_percent': 101}, {'owner_amount': 10000}, {'tax': 1001},
    {'fee': -1}, {'service_date': '2026-02-30'}, {'service_date': '2026-1-1'}, {'title': ' '}])
def test_invalid_addon_inputs(changes):
    with pytest.raises(ValidationError):
        RevenueIn(**revenue({}, **changes))


@pytest.mark.asyncio
async def test_cancel_preserves_records_releases_nights_and_blocks_stale_updates(ctx):
    db, c = ctx['db'], ctx['client']
    url = '/api/bookings/' + ctx['bid'] + '/cancel'
    stale = await c.post(url, headers=auth(ctx), json={'reason': 'Changed plans', 'revision': 2})
    assert stale.status_code == 409
    good = await c.post(url, headers=auth(ctx), json={'reason': 'Changed plans', 'revision': 0})
    assert good.status_code == 200, good.text
    row = good.json()
    assert row['status'] == 'cancelled' and row['manual_protected']
    assert row['amount'] == 1000 and row['cancellation_reason'] == 'Changed plans'
    assert await db.booking_history.count_documents({'booking_id': ctx['bid']}) == 1
    assert (await c.post(url, headers=auth(ctx), json={'reason': 'Retry', 'revision': 0})).status_code == 200
    assert await db.booking_history.count_documents({'booking_id': ctx['bid']}) == 1


@pytest.mark.asyncio
async def test_chart_bounds_scope_zero_buckets_and_received_addons(ctx):
    c, db = ctx['client'], ctx['db']
    day = date.today().isoformat()
    await db.bookings.update_one({'_id': ObjectId(ctx['bid'])}, {'$set': {'ota': 'Airbnb', 'ota_commission': 100}})
    await c.post('/api/bookings/' + ctx['bid'] + '/revenue', headers=auth(ctx), json=revenue(ctx))
    url = f'/api/reports/insights?start={day}&end={day}&interval=day&property_id='
    result = await c.get(url + ctx['p1'], headers=auth(ctx, 'owner'))
    assert result.status_code == 200
    assert result.json()['points'][0]['gross'] == 2000.03
    assert (await c.get(url + ctx['p2'], headers=auth(ctx, 'owner'))).status_code == 404
    assert (await c.get(url + ctx['p1'], headers=auth(ctx, 'cleaner'))).status_code == 403
    for suffix in ['start=2026-02-30&end=2026-03-01', 'start=2027-01-01&end=2026-01-01',
                   'start=2020-01-01&end=2026-01-01', 'start=2026-01-01&end=2026-06-01&interval=day']:
        assert (await c.get('/api/reports/insights?' + suffix, headers=auth(ctx))).status_code == 422


@pytest.mark.asyncio
async def test_existing_category_survives_older_client_and_invalid_types_fail(ctx):
    db, c = ctx['db'], ctx['client']
    await db.properties.update_one({'_id': ObjectId(ctx['p1'])}, {'$set': {'property_type': 'apartment'}})
    url = '/api/properties/' + ctx['p1']
    payload = {'name': 'Synthetic apartment', 'rooms': ['Bedroom']}
    assert (await c.put(url, headers=auth(ctx), json=payload)).json()['property_type'] == 'apartment'
    assert (await c.put(url, headers=auth(ctx), json={**payload, 'property_type': 'boat'})).status_code == 422


@pytest.mark.asyncio
async def test_shared_guest_link_names_only_idempotent_upload_and_checkout_retention(ctx):
    headers = await invitation(ctx)
    c, db = ctx['client'], ctx['db']
    data = {'guest_name': 'Synthetic Guest', 'guest_number': '1', 'document_type': 'national_id',
            'consent': 'true', 'submission_key': 'synthetic-guest-retry-001'}
    first = await c.post('/api/guest/documents', headers=headers, data=data, files={'file': ('id.jpg', jpeg(), 'image/jpeg')})
    assert first.status_code == 200, first.text
    second = await c.post('/api/guest/documents', headers=headers, data=data, files={'file': ('id.jpg', jpeg(), 'image/jpeg')})
    assert second.json()['id'] == first.json()['id']
    names = (await c.get('/api/guest/check-in', headers=headers)).json()['documents']
    assert names == [{'guest_name': 'Synthetic Guest', 'guest_number': 1}]
    doc = await db.guest_ids.find_one({'_id': ObjectId(first.json()['id'])})
    booking = await db.bookings.find_one({'_id': ObjectId(ctx['bid'])})
    assert datetime.fromisoformat(doc['delete_after']).astimezone(server.INDIA_TZ if hasattr(server, 'INDIA_TZ') else timezone(timedelta(hours=5, minutes=30))).date() == date.fromisoformat(booking['check_out']) + timedelta(days=90)
    for role in ['owner', 'cleaner', 'supervisor', 'other_owner']:
        assert (await c.get('/api/guest-ids/' + first.json()['id'] + '/image', headers=auth(ctx, role))).status_code == 403


@pytest.mark.asyncio
async def test_backup_cloud_stage_releases_business_lease(ctx, monkeypatch):
    monkeypatch.setenv('BACKUP_ENCRYPTION_KEY', 'synthetic-test-encryption-key-long-enough')
    entered, release = asyncio.Event(), asyncio.Event()
    store = MemoryBackups()
    original = store.put
    loop = asyncio.get_running_loop()

    def slow_cloud(key, data):
        loop.call_soon_threadsafe(entered.set)
        asyncio.run_coroutine_threadsafe(release.wait(), loop).result(timeout=5)
        original(key, data)

    store.put = slow_cloud
    task = asyncio.create_task(Backups(ctx['db'], store, lambda path: (b'', 'image/jpeg')).run())
    await asyncio.wait_for(entered.wait(), 3)
    try:
        async with business_lease(ctx['db']):
            await ctx['db'].invoices.insert_one({'number': 'AFTER-SNAPSHOT'})
    finally:
        release.set()
    result = await task
    assert result['verified']
    assert await ctx['db'].invoices.count_documents({'number': 'AFTER-SNAPSHOT'}) == 1


def test_encrypted_guest_storage_roundtrip_wrong_key_and_idempotent_deletion(monkeypatch):
    store = MemoryBackups()
    store.bucket = 'synthetic-private'
    store.db = mongomock.MongoClient().isolated
    documents = EncryptedGuestStore(store)
    monkeypatch.setenv('BACKUP_ENCRYPTION_KEY', 'synthetic-test-encryption-key-long-enough')
    doc = documents.put('guest-ids/synthetic.jpg', b'SYNTHETIC ID CONTENT')
    assert b'SYNTHETIC ID CONTENT' not in store.objects[doc['storage_key']]
    assert documents.read(doc) == b'SYNTHETIC ID CONTENT'
    monkeypatch.setenv('BACKUP_ENCRYPTION_KEY', 'different-synthetic-test-key-long-enough')
    with pytest.raises(Exception):
        documents.read(doc)
    documents.delete(doc)
    documents.delete(doc)
    assert not store.objects
    assert store.db.media_usage.find_one({'_id': 'guest-document-capacity:synthetic-private'})['bytes'] == 0
    with pytest.raises(HTTPException):
        documents.read({**doc, 'storage_key': 'database/something.bmbak'})


@pytest.mark.parametrize('mime', ['image/jpeg', 'image/png', 'image/webp'])
def test_guest_formats_remove_metadata_and_produce_reviewable_image(mime):
    from PIL import Image
    image = Image.new('RGB', (20, 10), 'white')
    data = io.BytesIO()
    image.save(data, format={'image/jpeg': 'JPEG', 'image/png': 'PNG', 'image/webp': 'WEBP'}[mime])
    clean = guest_ids.sanitise_document(data.getvalue(), mime)
    with Image.open(io.BytesIO(clean)) as result:
        assert result.format == 'JPEG' and result.size == (20, 10)
        assert not result.getexif()


def test_pdf_ids_invalid_password_and_page_limits():
    import pypdfium2 as pdfium
    with pytest.raises(HTTPException):
        guest_ids.sanitise_document(b'not-a-pdf', 'application/pdf')
    for pages in (1, 4, 5):
        with pdfium.PdfDocument.new() as pdf:
            for _ in range(pages):
                pdf.new_page(200, 100)
            output = io.BytesIO()
            pdf.save(output)
        if pages > 4:
            with pytest.raises(HTTPException):
                guest_ids.sanitise_document(output.getvalue(), 'application/pdf')
        else:
            assert guest_ids.sanitise_document(output.getvalue(), 'application/pdf').startswith(b'\xff\xd8')


@pytest.mark.parametrize('endpoint', ['http://fcm.googleapis.com/x', 'https://127.0.0.1/x',
    'https://fcm.googleapis.com.attacker.invalid/x', 'https://fcm.googleapis.com:abc/x', 'https://user@fcm.googleapis.com/x'])
def test_push_endpoints_cannot_target_private_or_untrusted_services(endpoint):
    body = SubscriptionIn(endpoint=endpoint, keys={'p256dh': 'x', 'auth': 'y'})
    with pytest.raises(HTTPException):
        body.validate_endpoint()


@pytest.mark.asyncio
async def test_activity_only_successful_changes_and_per_admin_read_state(ctx):
    c = ctx['client']
    url = '/api/bookings/' + ctx['bid'] + '/revenue'
    await c.post(url, headers=auth(ctx), json=revenue(ctx))
    await c.post(url, headers=auth(ctx), json=revenue(ctx))
    await c.post(url, headers=auth(ctx), json=revenue(ctx, amount=-1))
    notifications = await c.get('/api/notifications', headers=auth(ctx))
    assert notifications.status_code == 200
    assert len(notifications.json()) == 1 and notifications.json()[0]['unread']
    await c.post('/api/notifications/read', headers=auth(ctx), json={})
    assert not (await c.get('/api/notifications', headers=auth(ctx))).json()[0]['unread']
    key = await c.get('/api/notifications/push-key', headers=auth(ctx))
    assert set(key.json()) == {'public_key'}
    assert len(base64.urlsafe_b64decode(key.json()['public_key'] + '===')) == 65


@pytest.mark.asyncio
async def test_stale_checklist_and_review_cannot_overwrite_evidence(ctx):
    c, db = ctx['client'], ctx['db']
    url = '/api/cleaning/' + ctx['cid']
    first = await c.put(url + '/rooms/0/checklist', headers=auth(ctx, 'cleaner'), json={'checked': ['Surfaces cleaned'], 'expected_revision': 0})
    assert first.status_code == 200
    stale = await c.put(url + '/rooms/0/checklist', headers=auth(ctx, 'cleaner'), json={'checked': ['Linen replaced'], 'expected_revision': 0})
    assert stale.status_code == 409
    await db.cleaning.update_one({'_id': ObjectId(ctx['cid'])}, {'$set': {'status': 'awaiting_review', 'revision': 2}})
    assert (await c.post(url + '/review', headers=auth(ctx, 'supervisor'), json={'approved': True, 'expected_revision': 1})).status_code == 409
    assert (await c.post(url + '/review', headers=auth(ctx, 'supervisor'), json={'approved': True, 'expected_revision': 2})).status_code == 200


@pytest.mark.asyncio
async def test_create_booking_and_changed_checkout_retention(ctx):
    c, db = ctx['client'], ctx['db']
    today = date.today()
    start = (today + timedelta(days=10)).isoformat()
    end = (today + timedelta(days=12)).isoformat()
    body = dict(property_id=ctx['p2'], guest_name='Synthetic creation', ota='Direct', check_in=start, check_out=end, amount=2000, status='confirmed', guests=1)
    created = await c.post('/api/bookings', headers=auth(ctx), json=body)
    assert created.status_code == 200, created.text
    bid = created.json()['id']
    did = (await db.guest_ids.insert_one(dict(booking_id=bid, deleted=False, retention_policy='checkout-90-days', delete_after='old'))).inserted_id
    await db.guest_links.insert_one(dict(booking_id=bid, revoked=False))
    body['check_out'] = (today + timedelta(days=13)).isoformat()
    updated = await c.put('/api/bookings/' + bid, headers=auth(ctx), json=body)
    assert updated.status_code == 200, updated.text
    document = await db.guest_ids.find_one({'_id': did})
    expected = datetime.combine(today + timedelta(days=103), datetime.min.time(), guest_ids.INDIA_TZ).astimezone(timezone.utc).isoformat()
    assert document['delete_after'] == expected
    from guest_links import upload_cutoff
    assert (await db.guest_links.find_one({'booking_id': bid}))['expires_at'] == upload_cutoff(body['check_out'])
    cancelled = await c.post('/api/bookings/' + bid + '/cancel', headers=auth(ctx), json={'reason': 'Guest request', 'revision': updated.json()['revision']})
    assert cancelled.status_code == 200, cancelled.text
    assert (await db.guest_links.find_one({'booking_id': bid}))['revoked']
    body['status'] = 'cancelled'
    assert (await c.put('/api/bookings/' + bid, headers=auth(ctx), json=body)).status_code == 200
    assert (await db.bookings.find_one({'_id': ObjectId(bid)}))['cancellation_reason'] == 'Guest request'


def test_failed_document_upload_reclaims_object_and_capacity(monkeypatch):
    store = MemoryBackups()
    store.bucket = 'synthetic-private'
    store.db = mongomock.MongoClient().isolated
    documents = EncryptedGuestStore(store)
    monkeypatch.setenv('BACKUP_ENCRYPTION_KEY', 'synthetic-test-encryption-key-long-enough')
    original = store.put
    def lost_reply(key, stream):
        original(key, stream)
        raise RuntimeError('Synthetic lost acknowledgement')
    store.put = lost_reply
    with pytest.raises(RuntimeError):
        documents.put('guest-ids/lost-reply.jpg', b'Synthetic file')
    assert not store.objects
    assert store.db.guest_document_allocations.count_documents({}) == 0
    assert store.db.media_usage.find_one({'_id': 'guest-document-capacity:synthetic-private'})['bytes'] == 0


@pytest.mark.asyncio
async def test_shared_link_seven_guests_can_upload_separately(ctx):
    await ctx['db'].bookings.update_one({'_id': ObjectId(ctx['bid'])}, {'$set': {'guests': 7}})
    headers = await invitation(ctx)
    async def upload(number):
        return await ctx['client'].post('/api/guest/documents', headers=headers, data={
            'guest_name': 'Synthetic guest ' + str(number), 'guest_number': str(number),
            'document_type': 'national_id', 'consent': 'true', 'submission_key': 'seven-guest-' + str(number)},
            files={'file': ('id.jpg', jpeg(), 'image/jpeg')})
    responses = await asyncio.gather(*(upload(number) for number in range(1, 8)))
    assert [r.status_code for r in responses] == [200] * 7
    roster = (await ctx['client'].get('/api/guest/check-in', headers=headers)).json()['documents']
    assert len(roster) == 7 and all(set(row) == {'guest_name', 'guest_number'} for row in roster)


@pytest.mark.asyncio
async def test_large_success_response_still_records_activity_without_content(ctx):
    from activity import Activity, ActivityMiddleware
    async def application(scope, receive, send):
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        await send({'type': 'http.response.body', 'body': b'{"private":"' + b'x' * 300000 + b'"}', 'more_body': False})
    async def send(message):
        pass
    async def receive():
        return {'type': 'http.request', 'body': b''}
    middleware = ActivityMiddleware(application, Activity(ctx['db']))
    await middleware({'type': 'http', 'method': 'PUT', 'path': '/api/cleaning/example'}, receive, send)
    row = await ctx['db'].activities.find_one({})
    assert row and set(row) == {'_id', 'title', 'url', 'created_at'}
    assert row['title'] == 'Cleaning updated'


@pytest.mark.asyncio
async def test_guest_cleanup_retries_busy_job_without_false_storage_alarm(ctx, monkeypatch):
    from contextlib import asynccontextmanager
    import service_lease
    records = []
    async def record(route, failed):
        records.append((route, failed))
    monkeypatch.setattr(server.issue_tracker, 'record', record)
    @asynccontextmanager
    async def busy(*args, **kwargs):
        raise HTTPException(409, 'Busy', headers={'X-Britsmaid-Error': 'WRITE_BUSY'})
        yield
    monkeypatch.setattr(service_lease, 'business_lease', busy)
    assert await server.guest_retention_step() == 60
    assert not records
    @asynccontextmanager
    async def available(*args, **kwargs):
        yield
    monkeypatch.setattr(service_lease, 'business_lease', available)
    async def purge(user):
        return {'deleted': 0}
    monkeypatch.setattr(server, 'purge_guest_ids', purge)
    assert await server.guest_retention_step() == 3600
    assert records == [('Background guest ID cleanup', False)]
    async def failed_purge(user):
        raise HTTPException(503, 'Synthetic storage failure')
    monkeypatch.setattr(server, 'purge_guest_ids', failed_purge)
    assert await server.guest_retention_step() == 3600
    assert records[-1] == ('Background guest ID cleanup', True)
