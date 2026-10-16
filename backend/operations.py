"""Sanitized in-app incident reporting. Never stores request bodies or tokens."""
import hashlib
from datetime import datetime, timezone
from fastapi import Depends


class IssueTracker:
    def __init__(self, db):
        self.db = db
        self.fallback = {}

    async def record(self, route, failed):
        key = hashlib.sha256(route.encode()).hexdigest()[:12]
        now = datetime.now(timezone.utc).isoformat()
        try:
            old = await self.db.system_issues.find_one({"_id": key})
            if failed:
                title = ("Guest ID storage needs attention" if "guest" in route.lower() else
                         "Photo or video request failed" if any(x in route for x in ("upload", "files")) else
                         "Calendar sync needs attention" if "Calendar sync" in route else "A service request failed")
                await self.db.system_issues.update_one({"_id": key}, {"$set": {
                    "title": title, "route": route, "status": "open", "last_seen": now,
                    "help": "Retry the action. If it keeps failing, ask the admin to check the server and storage."},
                    "$setOnInsert": {"first_seen": now}, "$inc": {"count": 1}}, upsert=True)
            elif old and old["status"] == "open":
                await self.db.system_issues.update_one({"_id": key}, {"$set": {"status": "recovered", "recovered_at": now}})
            self.fallback.pop(key, None)
        except Exception:
            if failed:
                self.fallback[key] = {"_id": key, "title": "Service or database unavailable", "status": "open", "route": route, "last_seen": now,
                    "help": "Check the server/database, then retry. This notice is temporarily held in server memory."}
        return key

    def register(self, api, admin_user):
        @api.get("/system/issues")
        async def issues(user=Depends(admin_user)):
            try:
                rows = await self.db.system_issues.find({}).sort("last_seen", -1).to_list(100)
            except Exception:
                rows = []
            combined = {row["_id"]: row for row in rows}
            combined.update(self.fallback)
            return [{"id": row["_id"], **{k: v for k, v in row.items() if k != "_id"}} for row in combined.values()]
