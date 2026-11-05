"""Synthetic production-service regressions; no real cloud accounts or data."""
import asyncio
import gzip
import hashlib
import io
import time
from datetime import datetime, timedelta, timezone
from bson import ObjectId, json_util
import httpx
import mongomock
import pytest
from fastapi import HTTPException
from test_role_security_local import ctx, auth, server
from private_media import PrivateMediaStore
from backup_crypto import seal, unseal, CHUNK
from backups import Backups
from cleaning_retention import POLICY


@pytest.fixture(autouse=True)
def synthetic_retention_cloud(monkeypatch):
    async def verify(mid):
        return True
    async def expire(mid):
        return None
    monkeypatch.setattr(server.cleaning_retention, "verify_backup", verify)
    monkeypatch.setattr(server.cleaning_retention, "expire_backup", expire)


async def enable_retention(ctx, pid=None, enabled=True):
    pid = pid or ctx["p1"]
    await ctx["db"].settings.update_one({"_id": "cleaning_photo_retention:" + pid}, {"$set": {
        "property_id": pid, "policy": POLICY, "enabled": enabled}}, upsert=True)


class ObjectClient:
    def __init__(self):
        self.objects = {}
    def head_bucket(self, **kwargs):
        return {}
    def list_objects_v2(self, Bucket, Prefix, MaxKeys):
        return {"Contents": [{"Key": key} for key in self.objects if key.startswith(Prefix)][:MaxKeys]}
    def put_object(self, Bucket, Key, Body, ContentType, **kwargs):
        self.objects[Key] = (Body.read() if hasattr(Body, "read") else Body, ContentType)
    def get_object(self, Bucket, Key):
        data, content_type = self.objects[Key]
        return {"Body": io.BytesIO(data), "ContentType": content_type}
    def delete_object(self, Bucket, Key):
        self.objects.pop(Key, None)


@pytest.fixture
def objects(monkeypatch):
    monkeypatch.setenv("MEDIA_BUCKET", "synthetic-media")
    monkeypatch.setenv("MEDIA_ENDPOINT", "https://" + "a" * 32 + ".r2.cloudflarestorage.com")
    legacy = type("Legacy", (), {"get": lambda self, p: (b"legacy", "image/jpeg"), "delete": lambda self, p: None})()
    db = mongomock.MongoClient().isolated
    client = ObjectClient()
    return PrivateMediaStore(db, legacy, client=client), client, db


def media_path():
    return f"britsmaid/uploads/{ObjectId()}/{ObjectId()}-{'a' * 32}.jpg"


def test_private_store_retry_quota_legacy_and_delete(objects):
    store, client, db = objects
    path = media_path()
    result = store.put(path, b"sample", "image/jpeg")
    assert store.put(path, b"sample", "image/jpeg") == result
    assert store.get(result["path"]) == (b"sample", "image/jpeg")
    assert store.get("mongo:" + str(ObjectId()))[0] == b"legacy"
    key = store.bucket + ":" + store.prefix
    assert db.media_usage.find_one({"_id": key})["bytes"] == 6
    store.delete(result["path"])
    store.delete(result["path"])
    assert db.media_usage.find_one({"_id": key})["bytes"] == 0


def test_photo_capacity_and_request_limits_stop_cloud_calls(objects):
    store, client, db = objects
    store.budget = 3
    with pytest.raises(HTTPException) as exc:
        store.put(media_path(), b"too-large", "image/jpeg")
    assert exc.value.status_code == 507 and not client.objects
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    db.media_usage.insert_one({"_id": f"{store.bucket}:{store.prefix}:{month}:read", "count": 1000000})
    with pytest.raises(HTTPException):
        store.ready()


@pytest.mark.parametrize("path", ["guest-ids/private.jpg", "../secret", "britsmaid/uploads/../../invoice"])
def test_private_store_rejects_other_data(objects, path):
    with pytest.raises(HTTPException):
        objects[0].put(path, b"data", "image/jpeg")


@pytest.mark.parametrize("data", [b"", b"small", b"x" * (CHUNK + 50)], ids=["empty", "small", "multiple-blocks"])
def test_backup_encryption_restores_exact_bytes(data):
    encrypted = io.BytesIO()
    seal(io.BytesIO(data), encrypted, "test-backup-secret-" * 3)
    restored = io.BytesIO()
    encrypted.seek(0)
    unseal(encrypted, restored, "test-backup-secret-" * 3)
    assert restored.getvalue() == data
    broken = encrypted.getvalue()[:-1]
    with pytest.raises(Exception):
        unseal(io.BytesIO(broken), io.BytesIO(), "test-backup-secret-" * 3)
    with pytest.raises(Exception):
        unseal(io.BytesIO(encrypted.getvalue()), io.BytesIO(), "different-backup-secret-" * 3)


async def cleaning_sets(ctx, count=3):
    tasks, media = [], []
    for i in range(count):
        cid, before, after = ObjectId(), ObjectId(), ObjectId()
        row = {"_id": cid, "property_id": ctx["p1"], "status": "completed", "photos_ready_at": f"2026-10-{i+1:02}T10:00:00+00:00",
            "rooms": [{"name": "Room", "before": [str(before)], "after": [str(after)]}], "review_notes": "Keep history"}
        await ctx["db"].cleaning.insert_one(row)
        tasks.append(row)
        for mid, phase in [(before, "before"), (after, "after")]:
            await ctx["db"].media.insert_one({"_id": mid, "kind": "image", "is_deleted": False, "size": 20,
                "attachment_binding": f"{cid}:0:{phase}", "storage_path": "r2:synthetic/" + str(mid),
                "created_at": (datetime.now(timezone.utc) - timedelta(days=46 if i == 0 else i)).isoformat()})
            await ctx["db"].backup_objects.insert_one({"_id": str(mid), "media_id": str(mid), "verified": True})
            media.append(mid)
    return tasks, media


@pytest.mark.asyncio
async def test_45_day_expiry_preserves_cleaning_records_and_is_idempotent(ctx, monkeypatch):
    tasks, media = await cleaning_sets(ctx)
    removed = []
    monkeypatch.setattr(server, "delete_object", lambda path: removed.append(path))
    before = await ctx["db"].bookings.find_one({})
    await ctx["db"].invoices.insert_one({"invoice_number": "SAMPLE", "amount": 100})
    assert len(await server.cleaning_retention.plan()) == 2
    assert (await server.cleaning_retention.run("test", "preview"))["deleted"] == 0
    await enable_retention(ctx)
    result = await server.cleaning_retention.run("test", "Synthetic policy")
    assert result["deleted"] == 2 and len(removed) == 2
    assert (await server.cleaning_retention.run("test", "Retry"))["deleted"] == 0
    kept = await ctx["db"].cleaning.find_one({"_id": tasks[0]["_id"]})
    assert kept["review_notes"] == "Keep history" and len(kept["expired_media_ids"]) == 2
    assert await ctx["db"].invoices.count_documents({}) == 1
    assert await ctx["db"].bookings.find_one({}) == before
    assert await ctx["db"].media.count_documents({"is_deleted": False}) == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("protection", ["hold", "report", "cover", "other_property", "no_backup", "recent", "reopened"])
async def test_retention_preserves_protected_evidence(ctx, protection):
    tasks, media = await cleaning_sets(ctx)
    if protection == "hold":
        await ctx["db"].cleaning.update_one({"_id": tasks[0]["_id"]}, {"$set": {"photo_hold": True}})
    elif protection == "report":
        await ctx["db"].owner_reports.insert_one({"media_ids": [str(x) for x in media[:2]]})
    elif protection == "cover":
        await ctx["db"].properties.update_one({"_id": ObjectId(ctx["p1"])}, {"$set": {"cover_media_id": str(media[0])}})
    elif protection == "other_property":
        await ctx["db"].cleaning.insert_one({"property_id": ctx["p2"], "rooms": tasks[0]["rooms"]})
    elif protection == "recent":
        await ctx["db"].media.update_many({"_id": {"$in": media[:2]}}, {"$set": {"created_at": datetime.now(timezone.utc).isoformat()}})
    elif protection == "reopened":
        await ctx["db"].cleaning.update_one({"_id": tasks[0]["_id"]}, {"$set": {"status": "pending"}})
    elif protection == "no_backup":
        await ctx["db"].backup_objects.delete_many({})
        await enable_retention(ctx)
        assert (await server.cleaning_retention.run("test", "No backup"))["deleted"] == 0
        return
    assert len(await server.cleaning_retention.plan()) == (1 if protection == "cover" else 0)


@pytest.mark.asyncio
async def test_failed_deletion_keeps_metadata_for_retry(ctx, monkeypatch):
    tasks, media = await cleaning_sets(ctx)
    await enable_retention(ctx)
    def fail(path):
        raise RuntimeError("Synthetic unavailable storage")
    monkeypatch.setattr(server, "delete_object", fail)
    with pytest.raises(RuntimeError):
        await server.cleaning_retention.run("test", "Retry later")
    assert await ctx["db"].media.count_documents({"is_deleted": False}) == 6
    assert not await ctx["db"].maintenance_locks.find_one({"_id": "media-references"})


@pytest.mark.asyncio
async def test_browser_cookie_csrf_and_logout(ctx):
    password = "Synthetic-password-2026!"
    await ctx["db"].users.update_one({"_id": ctx["users"]["admin"]["_id"]}, {"$set": {"password_hash": server.hash_pw(password)}})
    result = await ctx["client"].post("https://test/api/auth/login", json={"email": "admin@example.com", "password": password, "browser_session": True})
    assert result.status_code == 200 and "access_token" not in result.json()
    cookie = result.headers["set-cookie"].lower()
    assert all(flag in cookie for flag in ("httponly", "secure", "samesite=strict", "path=/api"))
    assert (await ctx["client"].get("https://test/api/auth/me")).status_code == 200
    assert (await ctx["client"].post("https://test/api/auth/logout", headers={"Origin": "https://evil.invalid"})).status_code == 403
    assert (await ctx["client"].post("https://test/api/auth/logout", headers={"Origin": "https://test"})).status_code == 200
    assert (await ctx["client"].get("https://test/api/auth/me")).status_code == 401


@pytest.mark.asyncio
async def test_admin_mfa_enrollment_recovery_and_secret_redaction(ctx):
    password = "Synthetic-password-2026!"
    uid = ctx["users"]["admin"]["_id"]
    await ctx["db"].users.update_one({"_id": uid}, {"$set": {"password_hash": server.hash_pw(password)}})
    setup = await ctx["client"].post("/api/auth/mfa/setup", headers=auth(ctx), json={"password": password})
    secret = setup.json()["setup_key"]
    counter = int(time.time()) // 30
    code = server.admin_mfa.code(secret, counter)
    confirmed = await ctx["client"].post("/api/auth/mfa/confirm", headers=auth(ctx), json={"password": password, "code": code})
    assert confirmed.status_code == 200, confirmed.text
    recovery = confirmed.json()["recovery_codes"][0]
    body = {"email": "admin@example.com", "password": password}
    assert (await ctx["client"].post("/api/auth/login", json=body)).json()["code"] == "MFA_REQUIRED"
    assert (await ctx["client"].post("/api/auth/login", json={**body, "mfa_code": code})).status_code == 401
    result = await ctx["client"].post("/api/auth/login", json={**body, "mfa_code": recovery})
    assert result.status_code == 200 and "mfa_secret" not in result.text and "mfa_recovery_hashes" not in result.text
    assert (await ctx["client"].post("/api/auth/login", json={**body, "mfa_code": recovery})).status_code == 401
    user = await ctx["db"].users.find_one({"_id": uid})
    assert secret not in user["mfa_secret"]


class MemoryBackups:
    def __init__(self):
        self.objects = {}
    def put(self, key, stream):
        self.objects[key] = stream.read()
    def read(self, key):
        return io.BytesIO(self.objects[key])
    def delete(self, key):
        self.objects.pop(key, None)


@pytest.mark.asyncio
async def test_encrypted_database_backup_roundtrip_includes_invoices_not_sessions(ctx, monkeypatch):
    monkeypatch.setenv("BACKUP_ENCRYPTION_KEY", "synthetic-backup-encryption-key-2026!")
    await ctx["db"].invoices.insert_one({"number": "SAMPLE-1", "amount": 125})
    await ctx["db"].user_sessions.insert_one({"session_token": "SAMPLE-secret"})
    store = MemoryBackups()
    service = Backups(ctx["db"], store, lambda p: (b"sample", "image/jpeg"))
    result = await service.run()
    assert result["verified"]
    encrypted = store.objects["database/" + result["backup"] + ".bmbak"]
    assert b"SAMPLE-1" not in encrypted
    restored = io.BytesIO()
    unseal(io.BytesIO(encrypted), restored, "synthetic-backup-encryption-key-2026!")
    documents = [json_util.loads(line) for line in gzip.decompress(restored.getvalue()).decode().splitlines()]
    assert any(row["collection"] == "invoices" and row["document"]["amount"] == 125 for row in documents)
    assert not any(row["collection"] == "user_sessions" for row in documents)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["owner", "cleaner", "supervisor", "other_owner"])
async def test_non_admin_cannot_manage_retention_mfa_or_backups(ctx, role):
    for path in ["/system/photo-retention", "/system/readiness", "/auth/mfa"]:
        assert (await ctx["client"].get("/api" + path, headers=auth(ctx, role))).status_code == 403
    assert (await ctx["client"].post("/api/system/backups/run", headers=auth(ctx, role))).status_code == 403


@pytest.mark.asyncio
async def test_serialized_api_writes_return_retry_without_duplicate_booking(ctx, monkeypatch):
    entered, release = asyncio.Event(), asyncio.Event()
    original = server.check_overlap
    async def delayed(body, exclude=None):
        entered.set()
        await release.wait()
        return await original(body, exclude)
    monkeypatch.setattr(server, "check_overlap", delayed)
    day = (datetime.now(timezone.utc).date() + timedelta(days=20)).isoformat()
    checkout = (datetime.now(timezone.utc).date() + timedelta(days=22)).isoformat()
    body = {"property_id": ctx["p1"], "guest_name": "Synthetic", "check_in": day, "check_out": checkout}
    first = asyncio.create_task(ctx["client"].post("/api/bookings", headers=auth(ctx), json=body))
    await entered.wait()
    second = await ctx["client"].post("/api/bookings", headers=auth(ctx), json=body)
    assert second.status_code == 409
    release.set()
    assert (await first).status_code == 200


@pytest.mark.asyncio
async def test_partial_photo_deletion_retries_remaining_photo(ctx, monkeypatch):
    tasks, media = await cleaning_sets(ctx)
    await enable_retention(ctx)
    calls = []
    def sometimes(path):
        calls.append(path)
        if len(calls) == 2:
            raise RuntimeError("Synthetic interruption")
    monkeypatch.setattr(server, "delete_object", sometimes)
    with pytest.raises(RuntimeError):
        await server.cleaning_retention.run("test", "Interrupted")
    assert await ctx["db"].media.count_documents({"is_deleted": True}) == 1
    monkeypatch.setattr(server, "delete_object", lambda path: None)
    assert (await server.cleaning_retention.run("test", "Resume"))["deleted"] == 1
    assert await ctx["db"].media.count_documents({"is_deleted": True}) == 2


@pytest.mark.asyncio
async def test_age_policy_is_independent_of_newer_set_count(ctx):
    tasks, media = await cleaning_sets(ctx)
    await ctx["db"].media.update_one({"_id": media[-1]}, {"$set": {"is_deleted": True}})
    assert len(await server.cleaning_retention.plan()) == 2


def test_cloud_photo_integrity_failure_is_reported(objects):
    store, client, db = objects
    result = store.put(media_path(), b"sample", "image/jpeg")
    client.objects[result["path"][3:]] = (b"tampered", "image/jpeg")
    with pytest.raises(HTTPException) as exc:
        store.get(result["path"])
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_media_migration_preserves_id_and_old_copy_until_verified(ctx, objects):
    from media_migration import MediaMigration
    store, client, db = objects
    mid = ObjectId()
    original = "mongo:" + str(ObjectId())
    await ctx["db"].media.insert_one({"_id": mid, "owner_id": str(ctx["users"]["admin"]["_id"]), "storage_path": original, "is_deleted": False})
    migration = MediaMigration(ctx["db"])
    migration.store = store
    assert await migration.batch() == 1
    row = await ctx["db"].media.find_one({"_id": mid})
    assert row["storage_path"].startswith("r2:") and row["legacy_storage_path"] == original
    assert row["migration_verified"]
    assert await migration.batch() == 0


@pytest.mark.asyncio
async def test_database_recovery_preserves_ids_amounts_and_refuses_overwrite(ctx, monkeypatch):
    from restore_tools import restore_database
    key = "synthetic-recovery-encryption-secret-2026!"
    monkeypatch.setenv("BACKUP_ENCRYPTION_KEY", key)
    invoice_id = ObjectId()
    await ctx["db"].invoices.insert_one({"_id": invoice_id, "amount": 456, "property_id": ctx["p1"]})
    store = MemoryBackups()
    result = await Backups(ctx["db"], store, lambda p: (b"sample", "image/jpeg")).run()
    encrypted = store.objects["database/" + result["backup"] + ".bmbak"]
    target = server.client["synthetic_" + str(ObjectId()) + "_restore"]
    counts = await restore_database(io.BytesIO(encrypted), key, target)
    assert counts["invoices"] == 1
    restored = await target.invoices.find_one({"_id": invoice_id})
    assert restored["amount"] == 456 and restored["property_id"] == ctx["p1"]
    with pytest.raises(ValueError, match="empty"):
        await restore_database(io.BytesIO(encrypted), key, target)
    with pytest.raises(ValueError, match="_restore"):
        await restore_database(io.BytesIO(encrypted), key, ctx["db"])


@pytest.mark.asyncio
async def test_wrong_recovery_key_cannot_write_any_records(ctx, monkeypatch):
    from restore_tools import restore_database
    key = "synthetic-recovery-encryption-secret-2026!"
    monkeypatch.setenv("BACKUP_ENCRYPTION_KEY", key)
    store = MemoryBackups()
    result = await Backups(ctx["db"], store, lambda p: (b"sample", "image/jpeg")).run()
    encrypted = store.objects["database/" + result["backup"] + ".bmbak"]
    target = server.client["synthetic_" + str(ObjectId()) + "_restore"]
    with pytest.raises(Exception):
        await restore_database(io.BytesIO(encrypted), "incorrect-secret-" * 4, target)
    assert await target.list_collection_names() == []


@pytest.mark.asyncio
async def test_unsigned_upload_cannot_acquire_write_lease(ctx):
    result = await ctx["client"].post("/api/upload", files={"file": ("sample.jpg", b"not-an-image", "image/jpeg")})
    assert result.status_code == 401
    assert not await ctx["db"].maintenance_locks.find_one({"_id": "media-references"})


@pytest.mark.asyncio
async def test_photo_recovery_verifies_bytes_and_refuses_reuse(ctx, objects):
    from restore_tools import restore_photos
    key = "synthetic-photo-recovery-secret-2026!"
    destination, client, db = objects
    destination.bucket = "synthetic-staging-media"
    backups = MemoryBackups()
    backups.bucket = "synthetic-backups"
    mid = ObjectId()
    encrypted = io.BytesIO()
    seal(io.BytesIO(b"synthetic-photo"), encrypted, key)
    backups.objects["media/" + str(mid) + ".bmbak"] = encrypted.getvalue()
    target = server.client["synthetic_" + str(ObjectId()) + "_restore"]
    await target.media.insert_one({"_id": mid, "owner_id": str(ObjectId()), "is_deleted": False,
        "content_type": "image/jpeg", "storage_path": "mongo:old"})
    assert await restore_photos(target, backups, destination, key) == 1
    row = await target.media.find_one({"_id": mid})
    assert destination.get(row["storage_path"])[0] == b"synthetic-photo"
    with pytest.raises(ValueError, match="empty"):
        await restore_photos(target, backups, destination, key)


@pytest.mark.asyncio
async def test_retention_configuration_requires_a_note_and_does_not_delete(ctx):
    await cleaning_sets(ctx)
    result = await ctx["client"].put("/api/system/photo-retention", headers=auth(ctx), json={"property_id": ctx["p1"], "enabled": True, "note": " "})
    assert result.status_code == 422
    result = await ctx["client"].put("/api/system/photo-retention", headers=auth(ctx), json={"property_id": ctx["p1"], "enabled": True, "note": "Synthetic policy approval"})
    assert result.status_code == 200 and result.json()["enabled"]
    assert await ctx["db"].media.count_documents({"is_deleted": False}) == 6


def test_staging_free_guard_clamps_capacity(objects, monkeypatch):
    original, client, db = objects
    monkeypatch.setenv("APP_ENV", "staging")
    stage = PrivateMediaStore(db, original.legacy, client=client)
    assert stage.budget == 512 * 1024**2


@pytest.mark.asyncio
async def test_cleanup_revalidates_cloud_recovery_bytes_before_deletion(ctx, monkeypatch):
    key = "synthetic-recovery-verification-key-2026!"
    monkeypatch.setenv("BACKUP_ENCRYPTION_KEY", key)
    store = MemoryBackups()
    mid = str(ObjectId())
    encrypted = io.BytesIO()
    seal(io.BytesIO(b"recovery-photo"), encrypted, key)
    store.objects["media/" + mid + ".bmbak"] = encrypted.getvalue()
    await ctx["db"].backup_objects.insert_one({"media_id": mid, "verified": True, "sha256": hashlib.sha256(b"recovery-photo").hexdigest()})
    service = Backups(ctx["db"], store, lambda p: (b"photo", "image/jpeg"))
    assert await service.verify_media(mid)
    await ctx["db"].backup_objects.update_one({"media_id": mid}, {"$set": {"sha256": "wrong"}})
    with pytest.raises(RuntimeError, match="retained"):
        await service.verify_media(mid)

@pytest.mark.asyncio
@pytest.mark.parametrize("age,eligible", [(0, False), (44, False), (44.99999, False), (45, True), (46, True)])
async def test_photo_45_day_boundary_from_own_upload(ctx, monkeypatch, age, eligible):
    tasks, media = await cleaning_sets(ctx, count=1)
    now = datetime(2026, 12, 1, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(server.cleaning_retention, "now_iso", lambda: now.isoformat())
    uploaded = now - timedelta(days=age)
    await ctx["db"].media.update_many({}, {"$set": {"created_at": uploaded.isoformat()}})
    assert len(await server.cleaning_retention.plan()) == (2 if eligible else 0)
    # Completion time and the absence of a third log cannot change photo age.
    await ctx["db"].cleaning.update_one({"_id": tasks[0]["_id"]}, {"$set": {"completed_at": now.isoformat()}})
    assert len(await server.cleaning_retention.plan()) == (2 if eligible else 0)

@pytest.mark.asyncio
@pytest.mark.parametrize("stamp", [None, "unknown", "2020-01-01T00:00:00", "2999-01-01T00:00:00+00:00"])
async def test_unknown_naive_or_future_photo_dates_are_protected(ctx, stamp):
    await cleaning_sets(ctx, count=1)
    await ctx["db"].media.update_many({}, {"$set": {"created_at": stamp}})
    assert await server.cleaning_retention.plan() == []

@pytest.mark.asyncio
async def test_timezones_and_mixed_before_after_upload_dates(ctx, monkeypatch):
    tasks, media = await cleaning_sets(ctx, count=1)
    now = datetime(2026, 12, 1, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(server.cleaning_retention, "now_iso", lambda: now.isoformat())
    india = timezone(timedelta(hours=5, minutes=30))
    await ctx["db"].media.update_one({"_id": media[0]}, {"$set": {"created_at": (now - timedelta(days=45)).astimezone(india).isoformat()}})
    await ctx["db"].media.update_one({"_id": media[1]}, {"$set": {"created_at": now.isoformat()}})
    assert [c["media_id"] for c in await server.cleaning_retention.plan()] == [str(media[0])]

@pytest.mark.asyncio
async def test_every_property_defaults_off_and_legacy_global_opt_in_is_ignored(ctx, monkeypatch):
    await cleaning_sets(ctx, count=1)
    await ctx["db"].settings.insert_one({"_id": "cleaning_photo_retention", "enabled": True})
    monkeypatch.setattr(server, "delete_object", lambda p: pytest.fail("Default-off must not delete"))
    response = await ctx["client"].get("/api/system/photo-retention", headers=auth(ctx))
    assert response.status_code == 200 and response.json()["retention_days"] == 45
    assert all(not p["enabled"] for p in response.json()["properties"])
    assert (await server.cleaning_retention.run("test", "Default off"))["deleted"] == 0
    # Old clients cannot accidentally enable the new policy globally.
    assert (await ctx["client"].put("/api/system/photo-retention", headers=auth(ctx), json={"enabled": True, "note": "Old client"})).status_code == 422

@pytest.mark.asyncio
async def test_admin_property_opt_in_and_off_are_isolated_and_audited(ctx, monkeypatch):
    tasks, media = await cleaning_sets(ctx, count=1)
    await ctx["db"].cleaning.update_one({"_id": tasks[0]["_id"]}, {"$set": {"property_id": ctx["p2"]}})
    await enable_retention(ctx, ctx["p1"])
    monkeypatch.setattr(server, "delete_object", lambda p: pytest.fail("Wrong property must not delete"))
    assert (await server.cleaning_retention.run("test", "Other property"))["deleted"] == 0
    response = await ctx["client"].put("/api/system/photo-retention", headers=auth(ctx), json={"property_id": ctx["p1"], "enabled": False, "note": "Owner review"})
    assert response.status_code == 200
    assert not await server.cleaning_retention.enabled(ctx["p1"])
    assert await ctx["db"].media_retention_audit.find_one({"event": "policy_changed", "note": "Owner review", "enabled": False})
    assert not await server.cleaning_retention.enabled(ctx["p2"])

@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["owner", "cleaner", "supervisor", "other_owner"])
async def test_non_admin_cannot_change_property_retention_or_holds(ctx, role):
    assert (await ctx["client"].put("/api/system/photo-retention", headers=auth(ctx, role), json={"property_id": ctx["p1"], "enabled": True, "note": "Unauthorized"})).status_code == 403
    assert (await ctx["client"].put(f'/api/cleaning/{ctx["cid"]}/photo-hold', headers=auth(ctx, role), json={"hold": False, "note": "Unauthorized"})).status_code == 403

@pytest.mark.asyncio
@pytest.mark.parametrize("pid,status", [("bad", 422), ("000000000000000000000000", 404)])
async def test_retention_rejects_invalid_or_missing_properties(ctx, pid, status):
    response = await ctx["client"].put("/api/system/photo-retention", headers=auth(ctx), json={"property_id": pid, "enabled": True, "note": "Synthetic"})
    assert response.status_code == status

@pytest.mark.asyncio
@pytest.mark.parametrize("protection", ["mongo", "rollback", "damage_record", "damage_purpose", "damage_notes", "room_damage", "media_hold", "training", "invoice", "expense"])
async def test_non_cleaning_or_legacy_evidence_is_never_expired(ctx, protection):
    tasks, media = await cleaning_sets(ctx, count=1)
    ids = [str(m) for m in media]
    if protection == "mongo":
        await ctx["db"].media.update_many({}, {"$set": {"storage_path": "mongo:" + str(ObjectId())}})
    elif protection == "rollback":
        await ctx["db"].media.update_many({}, {"$set": {"legacy_storage_path": "mongo:" + str(ObjectId())}})
    elif protection == "damage_record":
        await ctx["db"].damage_records.insert_one({"media_ids": ids, "description": "Preserve damage evidence"})
    elif protection == "damage_purpose":
        await ctx["db"].media.update_many({}, {"$set": {"purpose": "damage"}})
    elif protection == "damage_notes":
        await ctx["db"].cleaning.update_one({"_id": tasks[0]["_id"]}, {"$set": {"notes": "Damage found; keep evidence"}})
    elif protection == "room_damage":
        await ctx["db"].cleaning.update_one({"_id": tasks[0]["_id"]}, {"$set": {"rooms.0.damage_notes": "Broken item"}})
    elif protection == "media_hold":
        await ctx["db"].media.update_many({}, {"$set": {"photo_hold": True}})
    elif protection == "training":
        await ctx["db"].training_lessons.insert_one({"published": {"media_ids": ids}})
    elif protection in ("invoice", "expense"):
        await ctx["db"]["invoices" if protection == "invoice" else "expenses"].insert_one({"media_ids": ids})
    assert await server.cleaning_retention.plan() == []

@pytest.mark.asyncio
async def test_switching_off_during_verification_stops_deletion(ctx, monkeypatch):
    await cleaning_sets(ctx, count=1)
    await enable_retention(ctx)
    async def verify(mid):
        await enable_retention(ctx, enabled=False)
        return True
    monkeypatch.setattr(server.cleaning_retention, "verify_backup", verify)
    monkeypatch.setattr(server, "delete_object", lambda p: pytest.fail("Paused property must not delete"))
    assert (await server.cleaning_retention.run("test", "Pause race"))["deleted"] == 0

@pytest.mark.asyncio
async def test_cloud_recovery_removal_retries_and_respects_property_pause(ctx, monkeypatch):
    tasks, media = await cleaning_sets(ctx, count=1)
    await enable_retention(ctx)
    calls = []
    monkeypatch.setattr(server, "delete_object", lambda p: calls.append(p))
    attempts = []
    async def expire(mid):
        attempts.append(mid)
        if len(attempts) == 1:
            raise RuntimeError("Synthetic recovery bucket interruption")
    monkeypatch.setattr(server.cleaning_retention, "expire_backup", expire)
    with pytest.raises(RuntimeError):
        await server.cleaning_retention.run("test", "Recovery deletion retry")
    assert await ctx["db"].media.count_documents({"is_deleted": True}) == 1
    await enable_retention(ctx, enabled=False)
    assert (await server.cleaning_retention.run("test", "Paused"))["deleted"] == 0
    assert len(attempts) == 1
    await enable_retention(ctx)
    await server.cleaning_retention.run("test", "Resume")
    assert len(calls) == 2  # No live file is deleted twice.
    assert await ctx["db"].media.count_documents({"recovery_purged_at": {"$exists": True}}) == 2

@pytest.mark.asyncio
async def test_only_expired_cleaning_recovery_copy_can_be_removed(ctx):
    store = MemoryBackups()
    service = Backups(ctx["db"], store, lambda p: (b"sample", "image/jpeg"))
    mid, cover = ObjectId(), ObjectId()
    await ctx["db"].media.insert_many([
        {"_id": mid, "is_deleted": True, "expiry_reason": POLICY, "created_at": (datetime.now(timezone.utc) - timedelta(days=46)).isoformat()},
        {"_id": cover, "is_deleted": False, "purpose": "cover"}])
    for item in (mid, cover):
        key = "media/" + str(item) + ".bmbak"
        store.objects[key] = b"synthetic encrypted bytes"
        await ctx["db"].backup_objects.insert_one({"_id": key, "media_id": str(item), "verified": True})
    await service.expire_media(str(mid))
    assert "media/" + str(mid) + ".bmbak" not in store.objects
    with pytest.raises(RuntimeError):
        await service.expire_media(str(cover))
    assert "media/" + str(cover) + ".bmbak" in store.objects

@pytest.mark.asyncio
async def test_expiry_fails_closed_without_cloud_backup_callbacks(ctx, monkeypatch):
    await cleaning_sets(ctx, count=1)
    await enable_retention(ctx)
    monkeypatch.setattr(server.cleaning_retention, "verify_backup", None)
    monkeypatch.setattr(server, "delete_object", lambda p: pytest.fail("No verified recovery adapter"))
    result = await server.cleaning_retention.run("test", "Missing adapter")
    assert result["deleted"] == 0 and "required" in result["reason"]

@pytest.mark.asyncio
async def test_recovery_copy_cannot_be_expired_before_45_days(ctx):
    service = Backups(ctx["db"], MemoryBackups(), lambda p: (b"sample", "image/jpeg"))
    mid = ObjectId()
    await ctx["db"].media.insert_one({"_id": mid, "is_deleted": True, "expiry_reason": POLICY, "created_at": datetime.now(timezone.utc).isoformat()})
    with pytest.raises(RuntimeError):
        await service.expire_media(str(mid))

@pytest.mark.asyncio
async def test_hold_protects_recovery_copy_after_interrupted_expiry(ctx, monkeypatch):
    tasks, media = await cleaning_sets(ctx, count=1)
    await enable_retention(ctx)
    await ctx["db"].media.update_many({"_id": {"$in": media}}, {"$set": {"is_deleted": True, "expiry_reason": POLICY, "property_id": ctx["p1"]}})
    await ctx["db"].cleaning.update_one({"_id": tasks[0]["_id"]}, {"$set": {"photo_hold": True}})
    async def fail(mid):
        pytest.fail("Held recovery must be preserved")
    monkeypatch.setattr(server.cleaning_retention, "expire_backup", fail)
    assert (await server.cleaning_retention.run("test", "Evidence hold"))["deleted"] == 0

@pytest.mark.asyncio
async def test_admin_can_place_and_release_a_cleaning_hold_with_a_note(ctx):
    path = f'/api/cleaning/{ctx["cid"]}/photo-hold'
    response = await ctx["client"].put(path, headers=auth(ctx), json={"hold": True, "note": "Owner damage review"})
    assert response.status_code == 200, response.text
    assert (await ctx["db"].cleaning.find_one({"_id": ObjectId(ctx["cid"])}))["photo_hold"] is True
    response = await ctx["client"].put(path, headers=auth(ctx), json={"hold": False, "note": "Review complete"})
    assert response.status_code == 200 and response.json()["hold"] is False
    assert (await ctx["client"].put(path, headers=auth(ctx), json={"hold": False, "note": " "})).status_code == 422
