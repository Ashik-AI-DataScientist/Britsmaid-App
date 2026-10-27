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
                "attachment_binding": f"{cid}:0:{phase}", "storage_path": "mongo:" + str(mid)})
            await ctx["db"].backup_objects.insert_one({"_id": str(mid), "media_id": str(mid), "verified": True})
            media.append(mid)
    return tasks, media


@pytest.mark.asyncio
async def test_third_set_expires_first_photos_only_and_is_idempotent(ctx, monkeypatch):
    tasks, media = await cleaning_sets(ctx)
    removed = []
    monkeypatch.setattr(server, "delete_object", lambda path: removed.append(path))
    before = await ctx["db"].bookings.find_one({})
    await ctx["db"].invoices.insert_one({"invoice_number": "SAMPLE", "amount": 100})
    assert len(await server.cleaning_retention.plan()) == 2
    assert (await server.cleaning_retention.run("test", "preview"))["deleted"] == 0
    await ctx["db"].settings.insert_one({"_id": "cleaning_photo_retention", "enabled": True})
    result = await server.cleaning_retention.run("test", "Synthetic policy")
    assert result["deleted"] == 2 and len(removed) == 2
    assert (await server.cleaning_retention.run("test", "Retry"))["deleted"] == 0
    kept = await ctx["db"].cleaning.find_one({"_id": tasks[0]["_id"]})
    assert kept["review_notes"] == "Keep history" and len(kept["expired_media_ids"]) == 2
    assert await ctx["db"].invoices.count_documents({}) == 1
    assert await ctx["db"].bookings.find_one({}) == before
    assert await ctx["db"].media.count_documents({"is_deleted": False}) == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("protection", ["hold", "report", "cover", "other_property", "no_backup", "incomplete_third", "reopened"])
async def test_retention_preserves_protected_evidence(ctx, protection):
    tasks, media = await cleaning_sets(ctx)
    if protection == "hold":
        await ctx["db"].cleaning.update_one({"_id": tasks[0]["_id"]}, {"$set": {"photo_hold": True}})
    elif protection == "report":
        await ctx["db"].owner_reports.insert_one({"media_ids": [str(x) for x in media[:2]]})
    elif protection == "cover":
        await ctx["db"].properties.update_one({"_id": ObjectId(ctx["p1"])}, {"$set": {"cover_media_id": str(media[0])}})
    elif protection == "other_property":
        await ctx["db"].cleaning.update_one({"_id": tasks[2]["_id"]}, {"$set": {"property_id": ctx["p2"]}})
    elif protection == "incomplete_third":
        await ctx["db"].cleaning.update_one({"_id": tasks[2]["_id"]}, {"$set": {"rooms.0.after": []}})
    elif protection == "reopened":
        await ctx["db"].cleaning.update_one({"_id": tasks[0]["_id"]}, {"$set": {"status": "pending"}})
    elif protection == "no_backup":
        await ctx["db"].backup_objects.delete_many({})
        await ctx["db"].settings.insert_one({"_id": "cleaning_photo_retention", "enabled": True})
        assert (await server.cleaning_retention.run("test", "No backup"))["deleted"] == 0
        return
    assert len(await server.cleaning_retention.plan()) == (1 if protection == "cover" else 0)


@pytest.mark.asyncio
async def test_failed_deletion_keeps_metadata_for_retry(ctx, monkeypatch):
    tasks, media = await cleaning_sets(ctx)
    await ctx["db"].settings.insert_one({"_id": "cleaning_photo_retention", "enabled": True})
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
    await ctx["db"].settings.insert_one({"_id": "cleaning_photo_retention", "enabled": True})
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
async def test_missing_newer_photo_never_expires_old_evidence(ctx):
    tasks, media = await cleaning_sets(ctx)
    await ctx["db"].media.update_one({"_id": media[-1]}, {"$set": {"is_deleted": True}})
    assert await server.cleaning_retention.plan() == []


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
    result = await ctx["client"].put("/api/system/photo-retention", headers=auth(ctx), json={"enabled": True, "note": " "})
    assert result.status_code == 422
    result = await ctx["client"].put("/api/system/photo-retention", headers=auth(ctx), json={"enabled": True, "note": "Synthetic policy approval"})
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
