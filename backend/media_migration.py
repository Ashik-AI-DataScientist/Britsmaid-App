"""Copy and verify legacy files before switching their database pointer."""
import hashlib
from fastapi import Depends, HTTPException
from fastapi.concurrency import run_in_threadpool


class MediaMigration:
    def __init__(self, db):
        self.db, self.store = db, None

    async def batch(self):
        if not self.store:
            raise HTTPException(503, "Private cloud media storage has not been configured")
        moved = 0
        async for media in self.db.media.find({"is_deleted": False, "storage_path": {"$regex": "^mongo:"}}).limit(3):
            original = media["storage_path"]
            data, content_type = await run_in_threadpool(self.store.legacy.get, original)
            digest = hashlib.sha256(data).hexdigest()
            suffix = {"image/jpeg": "jpg", "image/png": "jpg", "video/mp4": "mp4", "video/quicktime": "mov"}.get(content_type)
            if not suffix:
                raise HTTPException(422, "A legacy file has an unsupported content type; review it before migration")
            path = f"britsmaid/uploads/{media['owner_id']}/{media['_id']}-{digest[:32]}.{suffix}"
            target = await run_in_threadpool(self.store.put, path, data, content_type)
            copied, _ = await run_in_threadpool(self.store.get, target["path"])
            if hashlib.sha256(copied).hexdigest() != digest:
                raise RuntimeError("Photo migration verification failed")
            # Keep the old object for rollback. Its later deletion requires a verified backup.
            result = await self.db.media.update_one({"_id": media["_id"], "storage_path": original, "is_deleted": False},
                {"$set": {"storage_path": target["path"], "legacy_storage_path": original, "migration_verified": True}})
            moved += result.modified_count
        return moved

    def register(self, api, admin_user):
        @api.post("/system/media/migrate")
        async def queue(user=Depends(admin_user)):
            if not self.store:
                raise HTTPException(503, "Connect private photo storage first")
            await self.db.settings.update_one({"_id": "media_migration"}, {"$set": {"requested": True}}, upsert=True)
            return {"queued": True, "legacy_files_retained_for_rollback": True}
