"""Atomic per-night claims prevent overlapping manual reservations across workers."""
from datetime import date, timedelta
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError


async def claim_nights(db, booking_id, property_id, check_in, check_out):
    first, last = date.fromisoformat(check_in), date.fromisoformat(check_out)
    if (last - first).days > 730:
        raise HTTPException(422, "Bookings can cover at most 730 nights")
    acquired = []
    try:
        for offset in range((last - first).days):
            key = f"{property_id}:{first + timedelta(days=offset)}"
            existing = await db.reserved_nights.find_one({"_id": key})
            if existing and existing["booking_id"] == booking_id:
                continue
            await db.reserved_nights.insert_one({"_id": key, "booking_id": booking_id})
            acquired.append(key)
    except Exception as error:
        await db.reserved_nights.delete_many({"_id": {"$in": acquired}, "booking_id": booking_id})
        if isinstance(error, DuplicateKeyError):
            raise HTTPException(409, "These dates were just booked. Refresh and choose other dates.")
        raise
    return acquired


async def release_unused(db, booking_id, property_id=None, check_in=None, check_out=None):
    keep = []
    if property_id:
        first, last = date.fromisoformat(check_in), date.fromisoformat(check_out)
        keep = [f"{property_id}:{first + timedelta(days=i)}" for i in range((last-first).days)]
    await db.reserved_nights.delete_many({"booking_id": booking_id, "_id": {"$nin": keep}})
