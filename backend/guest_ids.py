"""Guest check-in intake. ID images never enter the general media collection."""
import hashlib
import io
import os
import secrets
import uuid
from datetime import date, datetime, timezone, timedelta
from typing import Literal

import boto3
from botocore.config import Config
from fastapi import Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response, JSONResponse
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

MAX_BYTES = 8 * 1024 * 1024
INDIA_TZ = timezone(timedelta(hours=5, minutes=30))


class RequestTooLarge(HTTPException):
    def __init__(self):
        super().__init__(413, "ID upload exceeds request size limit")


class BoundedGuestUploads:
    """Enforce the limit while receiving multipart data, including chunked requests."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") != "/api/guest/documents":
            return await self.app(scope, receive, send)
        size = 0

        async def bounded_receive():
            nonlocal size
            message = await receive()
            size += len(message.get("body", b""))
            if size > MAX_BYTES + 64 * 1024:
                raise RequestTooLarge()
            return message

        try:
            await self.app(scope, bounded_receive, send)
        except RequestTooLarge:
            await JSONResponse({"detail": "ID upload exceeds request size limit"}, status_code=413)(scope, receive, send)


def private_store():
    bucket, kms = os.getenv("GUEST_ID_BUCKET"), os.getenv("GUEST_ID_KMS_KEY")
    retention = os.getenv("GUEST_ID_RETENTION_DAYS", "")
    if not bucket or not kms or not retention.isdigit() or not 1 <= int(retention) <= 365:
        raise HTTPException(503, "Guest ID storage and retention policy are not configured")
    s3 = boto3.client("s3", config=Config(signature_version="s3v4", retries={"max_attempts": 3}))
    block = s3.get_public_access_block(Bucket=bucket)["PublicAccessBlockConfiguration"]
    if not all(block.get(k) for k in ("BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets")):
        raise HTTPException(503, "Guest ID bucket must block all public access")
    return s3, bucket, kms, int(retention)


def store_image(key, data):
    s3, bucket, kms, _ = private_store()
    result = s3.put_object(Bucket=bucket, Key=key, Body=data, ContentType="image/jpeg",
                           ServerSideEncryption="aws:kms", SSEKMSKeyId=kms)
    return {"storage_key": key, "storage_bucket": bucket, "storage_version": result.get("VersionId")}


def read_image(doc):
    s3, _, _, _ = private_store()
    args = {"Bucket": doc["storage_bucket"], "Key": doc["storage_key"]}
    if doc.get("storage_version"):
        args["VersionId"] = doc["storage_version"]
    stream = s3.get_object(**args)["Body"]
    try:
        return stream.read()
    finally:
        stream.close()


def delete_image(doc):
    s3, _, _, _ = private_store()
    args = {"Bucket": doc["storage_bucket"], "Key": doc["storage_key"]}
    if doc.get("storage_version"):
        args["VersionId"] = doc["storage_version"]
    s3.delete_object(**args)


def sanitise_image(data):
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in ("JPEG", "PNG") or image.width * image.height > 20_000_000:
                raise HTTPException(422, "Use a JPEG or PNG image up to 20 megapixels")
            image.load()
            output = io.BytesIO()
            image.convert("RGB").save(output, format="JPEG", quality=90)
            return output.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise HTTPException(422, "Invalid ID image")


class IDReview(BaseModel):
    status: Literal["verified", "rejected"]
    reason: str = Field(default="", max_length=1000)


class GuestAdminAction(BaseModel):
    action: Literal["check_in", "undo_check_in", "approve_id", "reset_id", "reject_id"]
    note: str = Field(min_length=1, max_length=2000)
    document_id: str | None = None


def register_guest_routes(api, db, admin_user, oid, now_iso):
    async def audit(action, actor, document_id=None, booking_id=None):
        await db.guest_id_audit.insert_one({"action": action, "actor_id": str(actor),
                                          "document_id": document_id, "booking_id": booking_id, "at": now_iso()})

    async def active_booking(bid):
        booking = await db.bookings.find_one({"_id": oid(bid), "status": "confirmed"})
        if not booking or booking["check_out"] <= datetime.now(INDIA_TZ).date().isoformat():
            raise HTTPException(404, "Booking is not open for check-in")
        if booking.get("guest_checked_in_at"):
            raise HTTPException(409, "Guests are already checked in")
        return booking

    async def guest_link(request: Request):
        auth = request.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else ""
        digest = hashlib.sha256(token.encode()).hexdigest()
        link = await db.guest_links.find_one({"token_hash": digest, "revoked": False, "expires_at": {"$gt": now_iso()}})
        if not token or not link:
            raise HTTPException(401, "Guest check-in link expired or revoked")
        await active_booking(link["booking_id"])
        return link

    @api.get("/guest-bookings")
    async def guest_bookings(user=Depends(admin_user)):
        today = datetime.now(INDIA_TZ).date().isoformat()
        bookings = await db.bookings.find({"status": "confirmed", "check_out": {"$gt": today}}).sort("check_in", 1).to_list(1000)
        result = []
        for b in bookings:
            bid = str(b["_id"])
            documents = await db.guest_ids.find({"booking_id": bid, "status": "verified", "deleted": False,
                "delete_after": {"$gt": now_iso()}, "expires_on": {"$gte": b["check_out"]}}).to_list(300)
            required = set(range(1, b.get("guests", 1) + 1))
            verified = required.intersection(d.get("guest_number") for d in documents)
            reason = ("Guests already checked in" if b.get("guest_checked_in_at") else
                      "Check-in date has not arrived" if b["check_in"] > today else
                      "Every guest needs an approved, valid ID" if verified != required else "Ready for check-in")
            prop = await db.properties.find_one({"_id": oid(b["property_id"])})
            result.append({"id": bid, "property_name": prop.get("name", "Property") if prop else "Property",
                **{k: b.get(k) for k in ("guest_name", "check_in", "check_out", "guests", "guest_checked_in_at")},
                "verified_guests": len(verified), "can_check_in": reason == "Ready for check-in", "check_in_reason": reason,
                "admin_history": b.get("admin_history", [])})
        return result

    @api.post("/bookings/{bid}/guest-link")
    async def invite(bid: str, user=Depends(admin_user)):
        await active_booking(bid)
        token = secrets.token_urlsafe(32)
        expiry = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat()
        await db.guest_links.update_many({"booking_id": bid}, {"$set": {"revoked": True}})
        await db.guest_links.insert_one({"booking_id": bid, "token_hash": hashlib.sha256(token.encode()).hexdigest(),
                                        "expires_at": expiry, "revoked": False, "attempts": 0})
        await audit("invite", user["_id"], booking_id=bid)
        return {"token": token, "expires_at": expiry}

    @api.post("/bookings/{bid}/guest-admin-action")
    async def admin_action(bid: str, body: GuestAdminAction, user=Depends(admin_user)):
        if not body.note.strip():
            raise HTTPException(422, "Add a reason for this admin action")
        b = await db.bookings.find_one({"_id": oid(bid)})
        if not b:
            raise HTTPException(404, "Booking not found")
        event = {"action": body.action, "note": body.note.strip(), "actor_id": str(user["_id"]),
                 "actor_name": user.get("name", "Admin"), "at": now_iso(),
                 "before": {k: b.get(k) for k in ("status", "guest_checked_in_at", "guest_checked_in_by")}}
        if body.action in ("check_in", "undo_check_in"):
            if body.action == "check_in" and b.get("guest_checked_in_at"):
                raise HTTPException(409, "Guests are already checked in")
            if body.action == "undo_check_in" and not b.get("guest_checked_in_at"):
                raise HTTPException(409, "Guests are not checked in")
            update = {"$push": {"admin_history": event}}
            if body.action == "check_in":
                update["$set"] = {"guest_checked_in_at": now_iso(), "guest_checked_in_by": str(user["_id"]), "status": "confirmed"}
            else:
                update["$unset"] = {"guest_checked_in_at": "", "guest_checked_in_by": ""}
                previous = next((e for e in reversed(b.get("admin_history", [])) if e["action"] in ("check_in", "undo_check_in")), None)
                if previous and previous["action"] == "check_in" and previous["before"].get("status"):
                    update["$set"] = {"status": previous["before"]["status"]}
            result = await db.bookings.update_one({"_id": b["_id"], "status": b.get("status"), "guest_checked_in_at": b.get("guest_checked_in_at")}, update)
            if not result.matched_count:
                raise HTTPException(409, "Booking changed; refresh and retry")
            await db.guest_links.update_many({"booking_id": bid}, {"$set": {"revoked": True}})
        else:
            if not body.document_id:
                raise HTTPException(422, "Choose an ID")
            d = await document(body.document_id)
            if d["booking_id"] != bid:
                raise HTTPException(404, "ID does not belong to this booking")
            status = {"approve_id": "verified", "reset_id": "pending", "reject_id": "rejected"}[body.action]
            event["document_id"] = body.document_id
            event["before"] = {k: d.get(k) for k in ("status", "review_reason", "reviewed_at", "reviewed_by")}
            try:
                result = await db.guest_ids.update_one({"_id": d["_id"], "status": d["status"], "deleted": False},
                    {"$set": {"status": status, "active": status != "rejected", "review_reason": body.note.strip(),
                              "reviewed_at": now_iso(), "reviewed_by": str(user["_id"]), "verification_method": "admin_override"},
                     "$push": {"admin_history": event}})
            except DuplicateKeyError:
                raise HTTPException(409, "A newer ID exists for this guest; review that ID instead")
            if not result.matched_count:
                raise HTTPException(409, "ID changed; refresh and retry")
            await db.bookings.update_one({"_id": b["_id"]}, {"$push": {"admin_history": event}})
        await db.guest_id_audit.insert_one({**event, "action": "admin_" + body.action, "booking_id": bid})
        return {"ok": True}

    @api.delete("/bookings/{bid}/guest-link")
    async def revoke(bid: str, user=Depends(admin_user)):
        await db.guest_links.update_many({"booking_id": bid}, {"$set": {"revoked": True}})
        await audit("revoke", user["_id"], booking_id=bid)
        return {"ok": True}

    @api.get("/guest/check-in")
    async def guest_status(link=Depends(guest_link)):
        b = await active_booking(link["booking_id"])
        documents = await db.guest_ids.find({"booking_id": link["booking_id"], "deleted": False, "delete_after": {"$gt": now_iso()}},
                                           {"guest_name": 1, "status": 1, "guest_number": 1, "review_reason": 1}).to_list(300)
        return {"check_in": b["check_in"], "check_out": b["check_out"], "guests": b.get("guests", 1),
                "retention_days": os.getenv("GUEST_ID_RETENTION_DAYS", "not configured"),
                "documents": [{"guest_name": d["guest_name"], "status": d["status"], "guest_number": d.get("guest_number"), "review_reason": d.get("review_reason", "")} for d in documents]}

    @api.post("/guest/documents")
    async def submit(file: UploadFile = File(...), guest_name: str = Form(...),
                     guest_number: int = Form(...),
                     document_type: Literal["passport", "driving_licence", "national_id"] = Form(...),
                     expires_on: str = Form(""), consent: bool = Form(...), link=Depends(guest_link)):
        if not consent or not guest_name.strip() or len(guest_name) > 150:
            raise HTTPException(422, "Guest name and consent are required")
        try:
            expiry = date.max if document_type == "national_id" and not expires_on else date.fromisoformat(expires_on)
        except ValueError:
            raise HTTPException(422, "ID expiry must be YYYY-MM-DD")
        b = await active_booking(link["booking_id"])
        if guest_number < 1 or guest_number > b.get("guests", 1):
            raise HTTPException(422, "Guest number must be within the booked guest count")
        if expiry < date.fromisoformat(b["check_out"]):
            raise HTTPException(422, "ID must be valid through check-out")
        # Bound upload attempts atomically, including failed attempts.
        result = await db.guest_links.update_one({"_id": link["_id"], "revoked": False, "expires_at": {"$gt": now_iso()}, "attempts": {"$lt": min(b.get("guests", 1) * 3, 300)}}, {"$inc": {"attempts": 1}})
        if not result.matched_count:
            raise HTTPException(429, "Upload limit reached; contact the administrator")
        data = await file.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise HTTPException(413, "ID image exceeds 8MB")
        if file.content_type not in ("image/jpeg", "image/png"):
            raise HTTPException(422, "Only JPEG and PNG ID images are accepted")
        data = await run_in_threadpool(sanitise_image, data)
        # A retained-but-expired record must not hold an invisible active slot.
        await db.guest_ids.update_many({"booking_id": link["booking_id"], "guest_number": guest_number,
            "active": True, "delete_after": {"$lte": now_iso()}}, {"$set": {"active": False}})
        _, _, _, retention = await run_in_threadpool(private_store)
        key = f"guest-ids/{uuid.uuid4()}.jpg"
        stored = await run_in_threadpool(store_image, key, data)
        doc = {**stored, "booking_id": link["booking_id"], "property_id": b["property_id"],
               "guest_name": guest_name.strip(), "document_type": document_type, "expires_on": expiry.isoformat(),
               "status": "pending", "guest_number": guest_number, "active": True, "deleted": False, "consented_at": now_iso(), "created_at": now_iso(),
               "delete_after": (datetime.now(timezone.utc) + timedelta(days=retention)).isoformat()}
        try:
            inserted = await db.guest_ids.insert_one(doc)
        except DuplicateKeyError:
            await run_in_threadpool(delete_image, stored)
            raise HTTPException(409, "This guest already has a pending or verified ID")
        except Exception:
            await run_in_threadpool(delete_image, stored)
            raise
        await audit("upload", "guest", str(inserted.inserted_id), link["booking_id"])
        return {"id": str(inserted.inserted_id), "status": "pending"}

    @api.get("/guest-ids")
    async def queue(booking_id: str | None = None, user=Depends(admin_user)):
        q = {"deleted": False, "delete_after": {"$gt": now_iso()}}
        if booking_id:
            q["booking_id"] = booking_id
        docs = await db.guest_ids.find(q, {"storage_key": 0, "storage_bucket": 0, "storage_version": 0}).sort("created_at", -1).to_list(500)
        result = []
        for d in docs:
            d["id"] = str(d.pop("_id"))
            result.append(d)
        return result

    @api.get("/guest-id-audit")
    async def audit_log(booking_id: str | None = None, user=Depends(admin_user)):
        q = {"booking_id": booking_id} if booking_id else {}
        events = await db.guest_id_audit.find(q).sort("at", -1).to_list(500)
        for event in events:
            event["id"] = str(event.pop("_id"))
        return events

    async def document(did):
        d = await db.guest_ids.find_one({"_id": oid(did), "deleted": False, "delete_after": {"$gt": now_iso()}})
        if not d:
            raise HTTPException(404, "Document not found or retention expired")
        return d

    @api.get("/guest-ids/{did}/image")
    async def image(did: str, user=Depends(admin_user)):
        d = await document(did)
        content = await run_in_threadpool(read_image, d)
        await audit("view", user["_id"], did, d["booking_id"])
        return Response(content, media_type="image/jpeg", headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Content-Disposition": "attachment; filename=guest-id.jpg"})

    @api.post("/guest-ids/{did}/review")
    async def review(did: str, body: IDReview, user=Depends(admin_user)):
        d = await document(did)
        await active_booking(d["booking_id"])
        if body.status == "rejected" and not body.reason.strip():
            raise HTTPException(422, "Provide a rejection reason")
        if body.status == "verified" and not await db.guest_id_audit.find_one({"action": "view", "actor_id": str(user["_id"]), "document_id": did}):
            raise HTTPException(409, "Open and review the ID image before approving")
        result = await db.guest_ids.update_one({"_id": d["_id"], "status": "pending", "deleted": False}, {"$set": {
            "status": body.status, "active": body.status == "verified", "review_reason": body.reason, "reviewed_by": str(user["_id"]),
            "reviewed_at": now_iso(), "verification_method": "manual_document_review"}})
        if not result.matched_count:
            raise HTTPException(409, "Document already reviewed; refresh")
        await audit(body.status, user["_id"], did, d["booking_id"])
        return {"ok": True}

    @api.delete("/guest-ids/{did}")
    async def remove(did: str, user=Depends(admin_user)):
        d = await db.guest_ids.find_one({"_id": oid(did), "deleted": False})
        if not d:
            raise HTTPException(404, "Document not found")
        await run_in_threadpool(delete_image, d)
        await db.guest_ids.update_one({"_id": d["_id"]}, {"$set": {"deleted": True, "active": False, "guest_name": "", "deleted_at": now_iso()},
            "$unset": {"storage_key": "", "storage_bucket": "", "storage_version": "", "expires_on": "", "review_reason": ""}})
        await audit("delete", user["_id"], did, d["booking_id"])
        return {"ok": True}

    @api.post("/guest-ids/purge-expired")
    async def purge(user=Depends(admin_user)):
        docs = await db.guest_ids.find({"deleted": False, "delete_after": {"$lte": now_iso()}}).to_list(500)
        for d in docs:
            await remove(str(d["_id"]), user)
        return {"deleted": len(docs)}

    @api.post("/bookings/{bid}/check-in")
    async def check_in(bid: str, user=Depends(admin_user)):
        b = await active_booking(bid)
        if b["check_in"] > datetime.now(INDIA_TZ).date().isoformat():
            raise HTTPException(409, "Check-in date has not arrived")
        documents = await db.guest_ids.find({"booking_id": bid, "status": "verified", "deleted": False,
                                           "delete_after": {"$gt": now_iso()}, "expires_on": {"$gte": b["check_out"]}}).to_list(300)
        slots = {d.get("guest_number") for d in documents}
        if not set(range(1, b.get("guests", 1) + 1)).issubset(slots):
            raise HTTPException(409, "Every guest needs an independently reviewed, valid ID")
        result = await db.bookings.update_one({"_id": b["_id"], "status": "confirmed", "guest_checked_in_at": None,
            **{k: b.get(k) for k in ("guests", "check_in", "check_out", "property_id")}},
            {"$set": {"guest_checked_in_at": now_iso(), "guest_checked_in_by": str(user["_id"])}})
        if not result.matched_count:
            raise HTTPException(409, "Booking changed; refresh before checking in")
        await audit("check_in", user["_id"], booking_id=bid)
        await db.guest_links.update_many({"booking_id": bid}, {"$set": {"revoked": True}})
        return {"ok": True}

    return purge
