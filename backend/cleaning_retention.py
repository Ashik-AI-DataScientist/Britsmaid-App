"""Keep cleaning history; expire only unshared before/after evidence of older sets."""
import secrets
from datetime import datetime, timedelta, timezone
from bson import ObjectId
from fastapi import Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError


class RetentionAction(BaseModel):
    note: str = Field(min_length=1, max_length=1000)


class PhotoHold(RetentionAction):
    hold: bool


class RetentionConfig(RetentionAction):
    enabled: bool


class CleaningRetention:
    def __init__(self, db, delete_object, now_iso):
        self.db, self.delete_object, self.now_iso = db, delete_object, now_iso
        self.verify_backup = None

    @staticmethod
    def evidence_ids(task):
        ids = set()
        for room in task.get("rooms", []):
            ids.update(room.get("before", []))
            ids.update(room.get("after", []))
        # Reassignment preserves previous evidence in the same cleaning history.
        for event in task.get("admin_history", []):
            for room in event.get("before", {}).get("rooms", []):
                ids.update(room.get("before", []))
                ids.update(room.get("after", []))
        return ids

    async def mark_ready(self, task_id):
        task = await self.db.cleaning.find_one({"_id": task_id})
        rooms = (task or {}).get("rooms", [])
        if rooms and all(room.get("before") and room.get("after") for room in rooms):
            await self.db.cleaning.update_one({"_id": task_id, "photos_ready_at": {"$exists": False}},
                {"$set": {"photos_ready_at": self.now_iso()}})

    async def plan(self, pid=None):
        tasks = await self.db.cleaning.find({"property_id": pid} if pid else {}).to_list(None)
        current_ids = {ObjectId(mid) for task in tasks for room in task.get("rooms", [])
            for phase in ("before", "after") for mid in room.get(phase, []) if ObjectId.is_valid(mid)}
        active = {str(row["_id"]) async for row in self.db.media.find({"_id": {"$in": list(current_ids)}, "is_deleted": False}, {"_id": 1})}
        properties = {}
        for task in tasks:
            # Incomplete uploads never displace a complete evidence set.
            rooms = task.get("rooms", [])
            if not rooms or not all(r.get("before") and r.get("after") for r in rooms):
                continue
            stamp = task.get("photos_ready_at") or task.get("submitted_at") or task.get("completed_at")
            if not stamp:
                continue  # Do not guess upload order for ambiguous legacy records.
            properties.setdefault(task["property_id"], []).append((stamp, task))
        candidates = []
        for property_id, ordered in properties.items():
            ordered.sort(key=lambda item: (item[0], str(item[1]["_id"])), reverse=True)
            if not all(set(room.get(phase, [])) & active for _, newest in ordered[:2]
                    for room in newest.get("rooms", []) for phase in ("before", "after")):
                continue  # Missing newer evidence must never cause old evidence to be erased.
            for _, task in ordered[2:]:
                # Never erase an active/reopened task, or evidence placed on hold.
                if task.get("status") != "completed" or task.get("photo_hold"):
                    continue
                for mid in self.evidence_ids(task):
                    if not ObjectId.is_valid(mid):
                        continue
                    media = await self.db.media.find_one({"_id": ObjectId(mid), "is_deleted": False})
                    if not media or media.get("attachment_binding", "").split(":")[0] != str(task["_id"]):
                        continue
                    if not media.get("storage_path", "").startswith(("mongo:", "r2:")):
                        continue
                    # Photo covers, reports, training and other task histories are protected.
                    if await self.db.properties.find_one({"cover_media_id": mid}):
                        continue
                    if await self.db.owner_reports.find_one({"media_ids": mid}):
                        continue
                    if await self.db.training_lessons.find_one({"$or": [{"media_ids": mid}, {"draft.media_ids": mid}, {"published.media_ids": mid}]}):
                        continue
                    if any(str(other["_id"]) != str(task["_id"]) and mid in self.evidence_ids(other) for other in tasks):
                        continue
                    candidates.append({"media_id": mid, "cleaning_id": str(task["_id"]), "property_id": property_id,
                        "size": media.get("size", 0), "storage_path": media["storage_path"], "legacy_storage_path": media.get("legacy_storage_path")})
        return candidates

    async def run(self, actor, note):
        # Cleanup is opt-in; scheduling the job alone cannot activate deletion.
        settings = await self.db.settings.find_one({"_id": "cleaning_photo_retention"}) or {}
        if not settings.get("enabled"):
            return {"enabled": False, "deleted": 0}
        if await self.db.backup_runs.find_one({"database_verified": True, "media_verified": False, "failed": {"$ne": True}}):
            return {"enabled": True, "deleted": 0, "reason": "Backup is still being verified"}
        owner, now = secrets.token_hex(16), datetime.now(timezone.utc)
        try:
            await self.db.maintenance_locks.update_one({"_id": "media-references"},
                {"$setOnInsert": {"until": now - timedelta(seconds=1)}}, upsert=True)
        except DuplicateKeyError:
            pass
        lock = await self.db.maintenance_locks.find_one_and_update({"_id": "media-references", "until": {"$lt": now}},
            {"$set": {"owner": owner, "until": now + timedelta(minutes=5)}}, return_document=ReturnDocument.AFTER)
        if not lock:
            raise HTTPException(409, "Photos are being updated. Retry cleanup shortly.")
        deleted = 0
        pending_backup = 0
        try:
            for candidate in (await self.plan())[:100]:
                if not await self.db.backup_objects.find_one({"media_id": candidate["media_id"], "verified": True}):
                    pending_backup += 1
                    continue  # Never purge the only verified copy.
                if self.verify_backup and not await self.verify_backup(candidate["media_id"]):
                    pending_backup += 1
                    continue
                renewed = await self.db.maintenance_locks.update_one({"_id": "media-references", "owner": owner,
                    "until": {"$gt": datetime.now(timezone.utc)}}, {"$set": {"until": datetime.now(timezone.utc) + timedelta(minutes=5)}})
                if not renewed.matched_count:
                    raise HTTPException(409, "Cleanup lease expired; retry safely.")
                # Persist intent before storage deletion so failures remain retryable.
                mid = ObjectId(candidate["media_id"])
                await self.db.media.update_one({"_id": mid}, {"$set": {"retention_state": "deleting"}})
                await run_in_threadpool(self.delete_object, candidate["storage_path"])
                if candidate.get("legacy_storage_path"):
                    await run_in_threadpool(self.delete_object, candidate["legacy_storage_path"])
                await self.db.media.update_one({"_id": mid}, {"$set": {"is_deleted": True,
                    "retention_state": "expired", "expired_at": self.now_iso(), "expiry_reason": "older_cleaning_set"}})
                await self.db.cleaning.update_one({"_id": ObjectId(candidate["cleaning_id"])},
                    {"$addToSet": {"expired_media_ids": candidate["media_id"]}})
                await self.db.media_retention_audit.insert_one({"media_id": candidate["media_id"],
                    "cleaning_id": candidate["cleaning_id"], "property_id": candidate["property_id"],
                    "actor": str(actor), "note": note, "at": self.now_iso()})
                deleted += 1
            return {"enabled": True, "deleted": deleted, "pending_backup": pending_backup}
        finally:
            await self.db.maintenance_locks.delete_one({"_id": "media-references", "owner": owner})

    def register(self, api, admin_user):
        @api.get("/system/photo-retention")
        async def preview(user=Depends(admin_user)):
            settings = await self.db.settings.find_one({"_id": "cleaning_photo_retention"}) or {}
            plan = await self.plan()
            return {"enabled": bool(settings.get("enabled")), "keep_sets": 2, "eligible_files": len(plan),
                "eligible_bytes": sum(row["size"] for row in plan),
                "candidates": [{k: v for k, v in row.items() if k not in ("storage_path", "legacy_storage_path")} for row in plan[:100]]}

        @api.put("/system/photo-retention")
        async def configure(body: RetentionConfig, user=Depends(admin_user)):
            if not body.note.strip():
                raise HTTPException(422, "Add a reason")
            await self.db.settings.update_one({"_id": "cleaning_photo_retention"}, {"$set": {
                "enabled": body.enabled, "note": body.note.strip(), "actor": str(user["_id"]), "at": self.now_iso()}}, upsert=True)
            return {"enabled": body.enabled}

        @api.post("/system/photo-retention/run")
        async def cleanup(body: RetentionAction, user=Depends(admin_user)):
            if not body.note.strip():
                raise HTTPException(422, "Add a reason")
            return await self.run(user["_id"], body.note.strip())

        @api.put("/cleaning/{cid}/photo-hold")
        async def hold(cid: str, body: PhotoHold, user=Depends(admin_user)):
            if not ObjectId.is_valid(cid) or not body.note.strip():
                raise HTTPException(422, "Choose a cleaning and add a reason")
            result = await self.db.cleaning.update_one({"_id": ObjectId(cid)}, {"$set": {
                "photo_hold": body.hold, "photo_hold_note": body.note.strip()}})
            if not result.matched_count:
                raise HTTPException(404, "Cleaning not found")
            return {"hold": body.hold}
