"""Revocable availability-only feeds; no guest or financial fields leave this module."""
import re
import secrets
from datetime import date, datetime, timedelta, timezone
from fastapi import Depends, HTTPException
from fastapi.responses import Response
from icalendar import Calendar, Event
from pymongo import ReturnDocument


def availability_calendar(bookings):
    cal = Calendar()
    cal.add("prodid", "-//Britsmaid//Property Availability//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    for booking in bookings:
        first, last = date.fromisoformat(booking["check_in"]), date.fromisoformat(booking["check_out"])
        if last <= first:
            continue
        event = Event()
        event.add("uid", f"{booking['_id']}@calendar.britsmaid")
        event.add("dtstamp", datetime.now(timezone.utc))
        event.add("sequence", booking.get("revision", 0))
        event.add("dtstart", first)
        event.add("dtend", last)  # iCalendar checkout day is exclusive.
        event.add("summary", "Britsmaid - Unavailable")
        event.add("status", "CONFIRMED")
        event.add("transp", "OPAQUE")
        cal.add_component(event)
    return cal.to_ical()


def register_calendar_exports(api, db, admin_user, oid, now_iso, otas):
    async def property_exists(pid):
        if not await db.properties.find_one({"_id": oid(pid), "is_deleted": {"$ne": True}}):
            raise HTTPException(404, "Property not found")

    @api.get("/properties/{pid}/ical-export")
    async def export_details(pid: str, _=Depends(admin_user)):
        await property_exists(pid)
        row = await db.calendar_exports.find_one({"_id": pid})
        return {"token": row.get("token") if row else None}

    @api.post("/properties/{pid}/ical-export")
    async def enable_export(pid: str, user=Depends(admin_user)):
        await property_exists(pid)
        row = await db.calendar_exports.find_one_and_update({"_id": pid}, {"$setOnInsert": {
            "token": secrets.token_urlsafe(32), "created_at": now_iso(), "created_by": str(user["_id"])
        }}, upsert=True, return_document=ReturnDocument.AFTER)
        return {"token": row["token"]}

    @api.delete("/properties/{pid}/ical-export")
    async def disable_export(pid: str, _=Depends(admin_user)):
        await property_exists(pid)
        await db.calendar_exports.delete_one({"_id": pid})
        return {"ok": True}

    @api.get("/ical/{token}.ics", include_in_schema=False)
    async def export_calendar(token: str, exclude_ota: str | None = None):
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
            raise HTTPException(404, "Calendar not found")
        if exclude_ota is not None and exclude_ota not in otas:
            raise HTTPException(422, "Choose a supported destination")
        row = await db.calendar_exports.find_one({"token": token})
        if not row:
            raise HTTPException(404, "Calendar not found")
        await property_exists(row["_id"])
        # Bound the payload, while including stays spanning either boundary.
        today = datetime.now(timezone.utc).date()
        query = {"property_id": row["_id"], "status": {"$in": ["confirmed", "blocked"]},
                 "check_out": {"$gt": (today - timedelta(days=365)).isoformat()},
                 "check_in": {"$lt": (today + timedelta(days=3 * 366)).isoformat()}}
        if exclude_ota:
            query["ota"] = {"$ne": exclude_ota}
        bookings = await db.bookings.find(query).sort("check_in", 1).to_list(10001)
        if len(bookings) > 10000:
            raise HTTPException(503, "Calendar is temporarily unavailable")
        return Response(availability_calendar(bookings), media_type="text/calendar; charset=utf-8", headers={
            "Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff", "Content-Disposition": 'inline; filename="availability.ics"'})
