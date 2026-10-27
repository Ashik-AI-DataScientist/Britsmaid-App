"""Opt-in encrypted daily exports to a separate private bucket.

Business writes are briefly serialized while exporting records. Media is immutable
and copied by content reference. Restore is an explicit offline operation.
"""
import asyncio
import gzip
import hashlib
import io
import os
import secrets
import tempfile
from datetime import datetime, timezone

from bson import json_util
from fastapi import Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from backup_crypto import seal, unseal
from service_lease import business_lease

EXCLUDED = {"user_sessions", "revoked_sessions", "maintenance_locks", "media_usage", "media_allocations", "backup_objects", "backup_allocations", "login_attempts"}


class Backups:
    def __init__(self, db, store, get_media):
        self.db, self.store, self.get_media = db, store, get_media

    async def expire_media(self, mid):
        """Only the cleaning expiry worker authorizes removal of its recovery copy."""
        from bson import ObjectId
        from cleaning_retention import POLICY, RETENTION_DAYS, aware_stamp
        media = await self.db.media.find_one({"_id": ObjectId(mid), "is_deleted": True, "expiry_reason": POLICY})
        uploaded = aware_stamp((media or {}).get("created_at"))
        if not media or not self.store or uploaded is None or (datetime.now(timezone.utc) - uploaded).total_seconds() < RETENTION_DAYS * 86400:
            raise RuntimeError("Cleaning recovery removal is not ready")
        key = "media/" + mid + ".bmbak"
        # Provider deletion is idempotent, including a lost acknowledgement/retry.
        await run_in_threadpool(self.store.delete, key)
        await self.db.backup_objects.delete_many({"media_id": mid})

    async def verify_media(self, mid):
        row = await self.db.backup_objects.find_one({"media_id": mid, "verified": True, "sha256": {"$exists": True}})
        if not self.store or not row:
            return False
        encrypted = await run_in_threadpool(self.store.read, "media/" + mid + ".bmbak")
        try:
            with tempfile.TemporaryFile() as clear:
                await run_in_threadpool(unseal, encrypted, clear, os.environ["BACKUP_ENCRYPTION_KEY"])
                clear.seek(0)
                if hashlib.file_digest(clear, "sha256").hexdigest() != row["sha256"]:
                    raise RuntimeError("Photo recovery checksum mismatch; original retained")
                return True
        finally:
            encrypted.close()

    async def run(self):
        async with business_lease(self.db, seconds=300, name="backup-job"):
            try:
                return await self._run()
            except BaseException:
                # Only this lease owner can mark interrupted exports as failed.
                await self.db.backup_runs.update_many({"media_verified": False}, {"$set": {"failed": True}})
                raise

    async def _run(self):
        if not self.store:
            raise HTTPException(503, "Private backup storage and encryption key are not configured")
        now = datetime.now(timezone.utc)
        identity = now.strftime("%Y%m%dT%H%M%S") + "-" + secrets.token_hex(4)
        # One export per day; a second caller sees the current lease rather than duplicating work.
        async with business_lease(self.db, seconds=300):
            with tempfile.TemporaryFile() as plain, tempfile.TemporaryFile() as encrypted:
                count = 0
                with gzip.GzipFile(fileobj=plain, mode="wb") as zipped:
                    for name in sorted(await self.db.list_collection_names()):
                        if name in EXCLUDED or name.startswith("app_media."):
                            continue
                        async for document in self.db[name].find({}):
                            zipped.write((json_util.dumps({"collection": name, "document": document}) + "\n").encode())
                            count += 1
                            if plain.tell() > 64 * 1024**2:
                                raise HTTPException(507, "Backup allowance reached; review storage before retrying")
                plain.seek(0)
                await run_in_threadpool(seal, plain, encrypted, os.environ["BACKUP_ENCRYPTION_KEY"])
                encrypted.seek(0)
                key = "database/" + identity + ".bmbak"
                await run_in_threadpool(self.store.put, key, encrypted)
                # Verify cloud download, authentication and exact plaintext digest.
                encrypted.seek(0)
                expected = hashlib.file_digest(encrypted, "sha256").hexdigest()
                downloaded = await run_in_threadpool(self.store.read, key)
                try:
                    if hashlib.file_digest(downloaded, "sha256").hexdigest() != expected:
                        raise RuntimeError("Backup checksum verification failed")
                    downloaded.seek(0)
                    with tempfile.TemporaryFile() as restored:
                        await run_in_threadpool(unseal, downloaded, restored, os.environ["BACKUP_ENCRYPTION_KEY"])
                finally:
                    downloaded.close()
                snapshot = {"_id": identity, "key": key, "created_at": now.isoformat(), "records": count,
                    "database_verified": True, "media_verified": False}
                await self.db.backup_runs.insert_one(snapshot)
        # Each photo backup is encrypted and addressed by immutable media ID.
        async for media in self.db.media.find({"is_deleted": False}):
            mid = str(media["_id"])
            key = "media/" + mid + ".bmbak"
            if not await self.db.backup_objects.find_one({"_id": key, "verified": True, "sha256": {"$exists": True}}):
                data, _ = await run_in_threadpool(self.get_media, media["storage_path"])
                with io.BytesIO(data) as plain, tempfile.TemporaryFile() as encrypted:
                    await run_in_threadpool(seal, plain, encrypted, os.environ["BACKUP_ENCRYPTION_KEY"])
                    encrypted.seek(0)
                    await run_in_threadpool(self.store.put, key, encrypted)
                    downloaded = await run_in_threadpool(self.store.read, key)
                    try:
                        with tempfile.TemporaryFile() as restored:
                            await run_in_threadpool(unseal, downloaded, restored, os.environ["BACKUP_ENCRYPTION_KEY"])
                            restored.seek(0)
                            if hashlib.file_digest(restored, "sha256").hexdigest() != hashlib.sha256(data).hexdigest():
                                raise RuntimeError("Photo backup verification failed")
                    finally:
                        downloaded.close()
                await self.db.backup_objects.update_one({"_id": key}, {"$set": {"verified": True,
                    "media_id": mid, "sha256": hashlib.sha256(data).hexdigest(), "at": datetime.now(timezone.utc).isoformat()}}, upsert=True)
        await self.db.backup_runs.update_one({"_id": identity}, {"$set": {"media_verified": True}})
        # Keep seven database snapshots. Photo expiry is controlled separately by
        # the 45-day worker, which respects each property's opt-in and holds.
        snapshots = await self.db.backup_runs.find({"database_verified": True, "media_verified": True}).sort("created_at", -1).to_list(None)
        for old in snapshots[7:]:
            await run_in_threadpool(self.store.delete, old["key"])
            await self.db.backup_runs.delete_one({"_id": old["_id"]})
        return {"backup": identity, "verified": True}

    def register(self, api, admin_user):
        @api.post("/system/backups/run")
        async def run(user=Depends(admin_user)):
            # The background scheduler owns execution; a request need not stay open.
            if not self.store:
                raise HTTPException(503, "Backup storage has not been configured")
            await self.db.settings.update_one({"_id": "backup_requested"}, {"$set": {"requested": True}}, upsert=True)
            return {"queued": True}
