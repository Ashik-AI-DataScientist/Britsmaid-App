"""Opt-in, per-property cleaning-photo expiry, 45 days from upload."""
from datetime import datetime, timedelta, timezone
from bson import ObjectId
from fastapi import Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from service_lease import business_lease

POLICY = "cleaning-photo-45-days-v1"
RETENTION_DAYS = 45

class RetentionAction(BaseModel):
    note: str = Field(min_length=1, max_length=1000)

class PhotoHold(RetentionAction):
    hold: bool

class RetentionConfig(RetentionAction):
    property_id: str
    enabled: bool

def aware_stamp(value):
    """Ambiguous legacy dates never authorize deletion."""
    try:
        stamp = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
        return stamp.astimezone(timezone.utc) if stamp.tzinfo is not None else None
    except (AttributeError, TypeError, ValueError, OverflowError):
        return None

class CleaningRetention:
    def __init__(self, db, delete_object, now_iso):
        self.db, self.delete_object, self.now_iso = db, delete_object, now_iso
        self.verify_backup = None
        self.expire_backup = None

    @staticmethod
    def evidence_ids(task):
        ids = set()
        for room in task.get("rooms", []):
            ids.update(room.get("before", []))
            ids.update(room.get("after", []))
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

    async def enabled(self, pid):
        return bool(await self.db.settings.find_one({"_id": "cleaning_photo_retention:" + pid, "policy": POLICY, "enabled": True}))

    @staticmethod
    def task_protected(task):
        if task.get("status") != "completed" or task.get("photo_hold"):
            return True
        items = [task, *task.get("rooms", [])]
        for event in task.get("admin_history", []):
            old = event.get("before", {})
            items.extend([old, *old.get("rooms", [])])
        for item in items:
            if any(item.get(key) for key in ("damage", "damages", "damage_records", "damage_media_ids", "damage_photos", "damage_notes", "incidents")):
                return True
            if any("damage" in str(item.get(key, "")).lower() for key in ("notes", "review_notes")):
                return True
        return False

    async def shared(self, mid, task_id):
        if await self.db.properties.find_one({"cover_media_id": mid}) or await self.db.owner_reports.find_one({"media_ids": mid}):
            return True
        if await self.db.training_lessons.find_one({"$or": [{"media_ids": mid}, {"draft.media_ids": mid}, {"published.media_ids": mid}]}):
            return True
        fields = ("media_id", "media_ids", "photo_id", "photo_ids", "photos", "attachments.media_id", "attachments.id", "evidence.media_ids", "before_media_id", "after_media_id")
        for name in ("damage_records", "damages", "incidents", "expenses", "invoices"):
            if await self.db[name].find_one({"$or": [{field: {"$in": [mid, ObjectId(mid)]}} for field in fields]}):
                return True
        return bool(await self.db.cleaning.find_one({"_id": {"$ne": task_id}, "$or": [
            {"rooms.before": mid}, {"rooms.after": mid}, {"admin_history.before.rooms.before": mid}, {"admin_history.before.rooms.after": mid}]}))

    async def plan(self, pid=None):
        now = aware_stamp(self.now_iso())
        if now is None:
            raise RuntimeError("Cleanup requires a timezone-aware clock")
        cutoff = now - timedelta(days=RETENTION_DAYS)
        tasks = await self.db.cleaning.find({"property_id": pid} if pid else {}).to_list(None)
        candidates, seen = [], set()
        for task in tasks:
            property_id = task.get("property_id", "")
            if self.task_protected(task) or not ObjectId.is_valid(property_id):
                continue
            if not await self.db.properties.find_one({"_id": ObjectId(property_id), "is_deleted": {"$ne": True}}):
                continue
            for mid in self.evidence_ids(task):
                if not ObjectId.is_valid(mid) or mid in seen:
                    continue
                media = await self.db.media.find_one({"_id": ObjectId(mid), "kind": "image", "is_deleted": False})
                if not media or media.get("attachment_binding", "").split(":")[0] != str(task["_id"]):
                    continue
                uploaded = aware_stamp(media.get("created_at"))
                if uploaded is None or uploaded > cutoff:
                    continue
                # Never delete MongoDB files or migration rollback copies.
                if not media.get("storage_path", "").startswith("r2:") or media.get("legacy_storage_path"):
                    continue
                if media.get("photo_hold") or media.get("protected") or media.get("damage_record_id"):
                    continue
                if media.get("purpose") not in (None, "", "cleaning", "cleaning_before", "cleaning_after", "cleaning_before_after"):
                    continue
                if await self.shared(mid, task["_id"]):
                    continue
                seen.add(mid)
                candidates.append({"media_id": mid, "cleaning_id": str(task["_id"]), "property_id": property_id,
                    "uploaded_at": uploaded.isoformat(), "expires_after": (uploaded + timedelta(days=RETENTION_DAYS)).isoformat(),
                    "size": media.get("size", 0), "storage_path": media["storage_path"]})
        return candidates

    async def purge_recovery(self, mid):
        if self.expire_backup:
            await self.expire_backup(mid)
        await self.db.media.update_one({"_id": ObjectId(mid)}, {"$set": {"recovery_purged_at": self.now_iso()}})

    async def run(self, actor, note):
        policies = await self.db.settings.find({"policy": POLICY, "enabled": True}).to_list(None)
        enabled_ids = {p["property_id"] for p in policies if p.get("property_id")}
        if not enabled_ids:
            return {"enabled": False, "deleted": 0, "pending_backup": 0}
        if not self.verify_backup or not self.expire_backup:
            return {"enabled": True, "deleted": 0, "reason": "Verified cloud backup storage is required before photo deletion"}
        if await self.db.backup_runs.find_one({"database_verified": True, "media_verified": False, "failed": {"$ne": True}}):
            return {"enabled": True, "deleted": 0, "reason": "Backup is still being verified"}
        deleted, pending_backup = 0, 0
        async with business_lease(self.db, seconds=300):
            async for media in self.db.media.find({"is_deleted": True, "expiry_reason": POLICY,
                    "property_id": {"$in": list(enabled_ids)}, "recovery_purged_at": {"$exists": False}}).limit(100):
                cid = media.get("attachment_binding", "").split(":")[0]
                task = await self.db.cleaning.find_one({"_id": ObjectId(cid)}) if ObjectId.is_valid(cid) else None
                if task and not self.task_protected(task) and not media.get("photo_hold") and await self.enabled(media["property_id"]):
                    await self.purge_recovery(str(media["_id"]))
            for candidate in [c for c in await self.plan() if c["property_id"] in enabled_ids][:100]:
                pid, mid = candidate["property_id"], ObjectId(candidate["media_id"])
                if pid not in enabled_ids or not await self.enabled(pid):
                    continue
                if not await self.db.backup_objects.find_one({"media_id": candidate["media_id"], "verified": True}):
                    pending_backup += 1
                    continue
                if not await self.verify_backup(candidate["media_id"]):
                    pending_backup += 1
                    continue
                if not await self.enabled(pid):
                    continue
                audit_id = POLICY + ":" + candidate["media_id"]
                await self.db.media_retention_audit.update_one({"_id": audit_id}, {"$setOnInsert": {
                    "event": "photo_expiry_requested", "media_id": candidate["media_id"], "cleaning_id": candidate["cleaning_id"],
                    "property_id": pid, "uploaded_at": candidate["uploaded_at"], "actor": str(actor), "note": note,
                    "at": self.now_iso(), "policy": POLICY}}, upsert=True)
                await self.db.media.update_one({"_id": mid}, {"$set": {"retention_state": "deleting"}})
                await run_in_threadpool(self.delete_object, candidate["storage_path"])
                await self.db.media.update_one({"_id": mid}, {"$set": {"is_deleted": True, "property_id": pid,
                    "retention_state": "expired", "expired_at": self.now_iso(), "expiry_reason": POLICY}})
                await self.db.cleaning.update_one({"_id": ObjectId(candidate["cleaning_id"])}, {"$addToSet": {"expired_media_ids": candidate["media_id"]}})
                await self.db.media_retention_audit.update_one({"_id": audit_id}, {"$set": {"event": "photo_expired", "completed_at": self.now_iso()}})
                deleted += 1
                await self.purge_recovery(candidate["media_id"])
        return {"enabled": True, "deleted": deleted, "pending_backup": pending_backup}

    def register(self, api, admin_user):
        @api.get("/system/photo-retention")
        async def preview(user=Depends(admin_user)):
            plan = await self.plan()
            properties = []
            async for prop in self.db.properties.find({"is_deleted": {"$ne": True}}).sort("name", 1):
                pid = str(prop["_id"])
                properties.append({"property_id": pid, "name": prop["name"], "enabled": await self.enabled(pid),
                    "eligible_files": sum(c["property_id"] == pid for c in plan)})
            return {"policy": POLICY, "retention_days": RETENTION_DAYS, "enabled": any(p["enabled"] for p in properties),
                "properties": properties, "eligible_files": len(plan), "eligible_bytes": sum(row["size"] for row in plan),
                "candidates": [{k: v for k, v in row.items() if k != "storage_path"} for row in plan[:100]]}

        @api.put("/system/photo-retention")
        async def configure(body: RetentionConfig, user=Depends(admin_user)):
            if not ObjectId.is_valid(body.property_id) or not body.note.strip():
                raise HTTPException(422, "Choose a property and add a reason")
            async with business_lease(self.db):
                if not await self.db.properties.find_one({"_id": ObjectId(body.property_id), "is_deleted": {"$ne": True}}):
                    raise HTTPException(404, "Property not found")
                await self.db.settings.update_one({"_id": "cleaning_photo_retention:" + body.property_id}, {"$set": {
                    "property_id": body.property_id, "policy": POLICY, "enabled": body.enabled,
                    "note": body.note.strip(), "actor": str(user["_id"]), "at": self.now_iso()}}, upsert=True)
                await self.db.media_retention_audit.insert_one({"event": "policy_changed", "property_id": body.property_id,
                    "enabled": body.enabled, "policy": POLICY, "note": body.note.strip(), "actor": str(user["_id"]), "at": self.now_iso()})
            return {"property_id": body.property_id, "enabled": body.enabled, "retention_days": RETENTION_DAYS}

        @api.post("/system/photo-retention/run")
        async def cleanup(body: RetentionAction, user=Depends(admin_user)):
            if not body.note.strip():
                raise HTTPException(422, "Add a reason before cleanup")
            return await self.run(user["_id"], body.note.strip())

        @api.put("/cleaning/{cid}/photo-hold")
        async def hold(cid: str, body: PhotoHold, user=Depends(admin_user)):
            if not ObjectId.is_valid(cid) or not body.note.strip():
                raise HTTPException(422, "Choose a cleaning and add a reason")
            async with business_lease(self.db):
                result = await self.db.cleaning.update_one({"_id": ObjectId(cid)}, {"$set": {"photo_hold": body.hold, "photo_hold_note": body.note.strip()}})
            if not result.matched_count:
                raise HTTPException(404, "Cleaning not found")
            return {"hold": body.hold}
