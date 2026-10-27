"""Restore helpers that refuse to overwrite any existing database."""
import gzip
import re
import tempfile
from bson import json_util
from backup_crypto import unseal


def records(stream):
    stream.seek(0)
    with gzip.GzipFile(fileobj=stream, mode="rb") as source:
        total = 0
        while line := source.readline(32 * 1024**2 + 1):
            total += len(line)
            if len(line) > 32 * 1024**2 or total > 1024**3:
                raise ValueError("Restore archive exceeds safety limits")
            row = json_util.loads(line)
            name, document = row.get("collection", ""), row.get("document")
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,80}", name) or not isinstance(document, dict) or "_id" not in document:
                raise ValueError("Invalid restore record")
            yield name, document


async def restore_database(encrypted, key, target):
    if not target.name.endswith("_restore"):
        raise ValueError("Restore destination must end with _restore")
    if await target.list_collection_names():
        raise ValueError("Restore destination must be empty; live data is never overwritten")
    with tempfile.TemporaryFile() as clear:
        unseal(encrypted, clear, key)
        counts = {}
        # Validate every record and gzip checksum before the first database write.
        for name, document in records(clear):
            counts[name] = counts.get(name, 0) + 1
        for name, document in records(clear):
            await target[name].insert_one(document)
        return counts


async def restore_photos(target_db, backup_store, target_media_store, key):
    if not target_db.name.endswith("_restore"):
        raise ValueError("Use an isolated restore database")
    if target_media_store.bucket == backup_store.bucket:
        raise ValueError("Recovery destination cannot be the backup bucket")
    if not target_media_store.bucket.endswith(("-restore", "-staging-media")):
        raise ValueError("Use a separately named restore or staging-media bucket")
    # The caller must provide a fresh, isolated target bucket and separate credentials.
    from fastapi.concurrency import run_in_threadpool
    import hashlib
    target_media_store.operation("read")
    existing = await run_in_threadpool(target_media_store.client.list_objects_v2,
        Bucket=target_media_store.bucket, Prefix=target_media_store.prefix, MaxKeys=1)
    if existing.get("Contents"):
        raise ValueError("Recovery media destination must be empty")
    restored = 0
    async for media in target_db.media.find({"is_deleted": False}):
        encrypted = await run_in_threadpool(backup_store.read, "media/" + str(media["_id"]) + ".bmbak")
        try:
            with tempfile.TemporaryFile() as clear:
                await run_in_threadpool(unseal, encrypted, clear, key)
                clear.seek(0)
                data = clear.read(100 * 1024**2 + 1)
        finally:
            encrypted.close()
        if len(data) > 100 * 1024**2:
            raise ValueError("Recovery media exceeds size limit")
        digest = hashlib.sha256(data).hexdigest()
        content_type = media.get("content_type", "image/jpeg")
        suffix = {"image/jpeg": "jpg", "image/png": "jpg", "video/mp4": "mp4", "video/quicktime": "mov"}[content_type]
        path = f"britsmaid/uploads/{media['owner_id']}/{media['_id']}-{digest[:32]}.{suffix}"
        result = await run_in_threadpool(target_media_store.put, path, data, content_type)
        copied, _ = await run_in_threadpool(target_media_store.get, result["path"])
        if hashlib.sha256(copied).digest() != hashlib.sha256(data).digest():
            raise ValueError("Restored media verification failed")
        await target_db.media.update_one({"_id": media["_id"]}, {"$set": {"storage_path": result["path"]}, "$unset": {"legacy_storage_path": ""}})
        restored += 1
    return restored
