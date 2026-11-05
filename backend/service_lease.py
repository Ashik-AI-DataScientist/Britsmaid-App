"""Shared, reentrant lease for short business writes and maintenance snapshots."""
import secrets
import asyncio
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

held = ContextVar("britsmaid_write_lease", default={})


@asynccontextmanager
async def business_lease(db, seconds=120, name="media-references"):
    if name in held.get():
        yield held.get()[name]
        return
    now, owner = datetime.now(timezone.utc), secrets.token_hex(16)
    try:
        await db.maintenance_locks.update_one({"_id": name},
            {"$setOnInsert": {"until": now - timedelta(seconds=1)}}, upsert=True)
    except DuplicateKeyError:
        pass
    row = await db.maintenance_locks.find_one_and_update({"_id": name, "until": {"$lt": now}},
        {"$set": {"owner": owner, "until": now + timedelta(seconds=seconds)}}, return_document=ReturnDocument.AFTER)
    if not row:
        raise HTTPException(409, "Records are being saved or backed up. Please retry shortly.")
    token = held.set({**held.get(), name: owner})
    parent = asyncio.current_task()
    async def renew():
        try:
            while True:
                await asyncio.sleep(max(5, seconds // 3))
                now = datetime.now(timezone.utc)
                result = await db.maintenance_locks.update_one({"_id": name, "owner": owner,
                    "until": {"$gt": now}}, {"$set": {"until": now + timedelta(seconds=seconds)}})
                if not result.matched_count:
                    parent.cancel()
                    return
        except asyncio.CancelledError:
            raise
        except Exception:
            parent.cancel()
    heartbeat = asyncio.create_task(renew())
    try:
        yield owner
    finally:
        heartbeat.cancel()
        await asyncio.gather(heartbeat, return_exceptions=True)
        held.reset(token)
        await db.maintenance_locks.delete_one({"_id": name, "owner": owner})
