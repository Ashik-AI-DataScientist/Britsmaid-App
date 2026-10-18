"""Isolated API regression tests. Never contacts a deployed API, MongoDB or S3."""
import io
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import pytest_asyncio
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.update(MONGO_URL="mongodb://localhost:27017", DB_NAME="isolated_security_tests", JWT_SECRET="test-only-secret-at-least-thirty-two-characters")
with patch("motor.motor_asyncio.AsyncIOMotorClient", AsyncMongoMockClient):
    import server
import guest_ids


@pytest_asyncio.fixture
async def ctx(monkeypatch):
    db = server.db
    for name in await db.list_collection_names():
        await db[name].delete_many({})
    await db.guest_ids.create_index([("booking_id", 1), ("guest_number", 1)], unique=True, partialFilterExpression={"active": True})
    p1, p2, cid, bid = [ObjectId() for _ in range(4)]
    today = datetime.now(guest_ids.INDIA_TZ).date()
    users = {}
    for role in ("admin", "owner", "cleaner", "supervisor", "other_cleaner", "other_owner"):
        actual_role = role.removeprefix("other_")
        users[role] = {"_id": ObjectId(), "name": role, "email": f"{role}@example.com", "role": actual_role, "active": True,
                       "property_ids": [] if role == "admin" else [str(p2 if role.startswith("other_") else p1)]}
        await db.users.insert_one(users[role])
    for pid in (p1, p2):
        await db.properties.insert_one({"_id": pid, "name": str(pid), "location": "Kerala", "rooms": ["Bedroom"], "owner_phone": "private", "owner_share_percent": 70, "ical_feeds": ["secret"], "is_deleted": False})
    await db.cleaning.insert_one({"_id": cid, "property_id": str(p1), "assigned_to": str(users["cleaner"]["_id"]),
        "status": "pending", "date": today.isoformat(), "rooms": [{"name": "Bedroom", "before": [], "after": []}]})
    await db.bookings.insert_one({"_id": bid, "property_id": str(p1), "guest_name": "Guest", "guest_phone": "private", "status": "confirmed", "guests": 2,
        "check_in": today.isoformat(), "check_out": (today + timedelta(days=2)).isoformat(), "amount": 1000})
    monkeypatch.setattr(guest_ids, "private_store", lambda: (None, "private-bucket", "kms-key", 30))
    monkeypatch.setattr(guest_ids, "store_image", lambda key, data: {"storage_key": key, "storage_bucket": "private-bucket", "storage_version": "version-1"})
    monkeypatch.setattr(guest_ids, "read_image", lambda doc: b"private-id")
    monkeypatch.setattr(guest_ids, "delete_image", lambda doc: None)
    monkeypatch.setattr(server, "get_object", lambda path: (b"photo", "image/jpeg"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
        yield {"client": client, "db": db, "users": users, "p1": str(p1), "p2": str(p2), "cid": str(cid), "bid": str(bid)}


def auth(ctx, role="admin"):
    return {"Authorization": "Bearer " + server.issue_token(ctx["users"][role])}


def jpeg():
    buffer = io.BytesIO()
    Image.new("RGB", (20, 20)).save(buffer, format="JPEG")
    return buffer.getvalue()


async def invitation(ctx):
    r = await ctx["client"].post(f'/api/bookings/{ctx["bid"]}/guest-link', headers=auth(ctx))
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


async def upload_id(ctx, headers, number=1, **extra):
    payload = {"guest_name": "Guest", "guest_number": str(number), "document_type": "national_id", "expires_on": "", "consent": "true", **extra}
    return await ctx["client"].post("/api/guest/documents", headers=headers, data=payload, files={"file": ("id.jpg", jpeg(), "image/jpeg")})


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["cleaner", "supervisor"])
@pytest.mark.parametrize("path", ["/bookings", "/calendar?month=2026-10", "/dashboard", "/users", "/guest-ids", "/invoices", "/owner-reports"])
async def test_team_cannot_read_guest_finance_or_admin_data(ctx, role, path):
    r = await ctx["client"].get("/api" + path, headers=auth(ctx, role))
    assert r.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["other_cleaner", "other_owner"])
async def test_cross_property_task_reads_denied(ctx, role):
    r = await ctx["client"].get(f'/api/cleaning/{ctx["cid"]}', headers=auth(ctx, role))
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_same_property_wrong_cleaner_cannot_read_or_edit_task(ctx):
    u = ctx["users"]["other_cleaner"]
    await ctx["db"].users.update_one({"_id": u["_id"]}, {"$set": {"property_ids": [ctx["p1"]]}})
    for method, suffix, body in [("GET", "", None), ("PUT", "", {"notes": "tamper"}), ("PUT", "/rooms/0/checklist", {"checked": []}),
                                  ("POST", "/rooms/0/media", {"phase": "before", "media_id": str(ObjectId())})]:
        r = await ctx["client"].request(method, f'/api/cleaning/{ctx["cid"]}{suffix}', headers=auth(ctx, "other_cleaner"), json=body)
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_staff_property_output_minimises_private_data(ctx):
    r = await ctx["client"].get("/api/properties", headers=auth(ctx, "cleaner"))
    assert len(r.json()) == 1
    assert "owner_phone" not in r.json()[0] and "owner_share_percent" not in r.json()[0] and "ical_feeds" not in r.json()[0]


@pytest.mark.asyncio
async def test_owner_scope_and_no_id_access(ctx):
    r = await ctx["client"].get("/api/bookings", headers=auth(ctx, "owner"))
    assert [b["property_id"] for b in r.json()] == [ctx["p1"]]
    assert (await ctx["client"].get(f'/api/properties/{ctx["p2"]}', headers=auth(ctx, "owner"))).status_code == 404
    assert (await ctx["client"].get("/api/guest-ids", headers=auth(ctx, "owner"))).status_code == 403


@pytest.mark.asyncio
async def test_media_cross_property_and_general_id_route_denied(ctx):
    mid = ObjectId()
    await ctx["db"].media.insert_one({"_id": mid, "is_deleted": False, "kind": "image", "owner_id": str(ctx["users"]["admin"]["_id"]), "storage_path": "photo"})
    assert (await ctx["client"].get(f"/api/files/{mid}", headers=auth(ctx, "owner"))).status_code == 404
    await ctx["db"].cleaning.update_one({"_id": ObjectId(ctx["cid"])}, {"$set": {"rooms.0.before": [str(mid)]}})
    assert (await ctx["client"].get(f"/api/files/{mid}", headers=auth(ctx, "owner"))).status_code == 200
    assert (await ctx["client"].get(f"/api/files/{mid}", headers=auth(ctx, "other_owner"))).status_code == 404
    assert (await ctx["client"].get(f"/api/files/{ObjectId()}", headers=auth(ctx))).status_code == 404


@pytest.mark.asyncio
async def test_cleaning_submission_checklist_review_and_lock(ctx):
    url = f'/api/cleaning/{ctx["cid"]}'
    assert (await ctx["client"].put(url, headers=auth(ctx, "cleaner"), json={"status": "completed"})).status_code == 400
    await ctx["db"].cleaning.update_one({"_id": ObjectId(ctx["cid"])}, {"$set": {"rooms.0.before": ["photo"], "rooms.0.after": ["photo"]}})
    assert (await ctx["client"].put(url, headers=auth(ctx, "cleaner"), json={"status": "completed"})).status_code == 400
    r = await ctx["client"].put(url + "/rooms/0/checklist", headers=auth(ctx, "cleaner"), json={"checked": server.CHECKLIST})
    assert r.status_code == 200
    r = await ctx["client"].put(url, headers=auth(ctx, "cleaner"), json={"status": "completed"})
    assert r.json()["status"] == "awaiting_review"
    assert (await ctx["client"].put(url, headers=auth(ctx, "cleaner"), json={"notes": "tamper"})).status_code == 409
    assert (await ctx["client"].post(url + "/review", headers=auth(ctx, "cleaner"), json={"approved": True})).status_code == 403
    assert (await ctx["client"].post(url + "/review", headers=auth(ctx, "supervisor"), json={"approved": False})).status_code == 422
    r = await ctx["client"].post(url + "/review", headers=auth(ctx, "supervisor"), json={"approved": True})
    assert r.json()["status"] == "completed"
    assert (await ctx["client"].post(url + "/review", headers=auth(ctx), json={"approved": True})).status_code == 409


@pytest.mark.asyncio
async def test_rework_and_assignment_validation(ctx):
    url = f'/api/cleaning/{ctx["cid"]}'
    assert (await ctx["client"].put(url, headers=auth(ctx), json={"assigned_to": str(ctx["users"]["owner"]["_id"])})).status_code == 422
    assert (await ctx["client"].put(url, headers=auth(ctx, "supervisor"), json={"assigned_to": str(ctx["users"]["other_cleaner"]["_id"])})).status_code == 422
    assert (await ctx["client"].put(url, headers=auth(ctx, "cleaner"), json={"assigned_to": None})).status_code == 403
    await ctx["db"].cleaning.update_one({"_id": ObjectId(ctx["cid"])}, {"$set": {"status": "awaiting_review"}})
    r = await ctx["client"].post(url + "/review", headers=auth(ctx, "supervisor"), json={"approved": False, "notes": "Replace linen"})
    assert r.json()["status"] == "in_progress" and r.json()["review_notes"] == "Replace linen"


@pytest.mark.asyncio
@pytest.mark.parametrize("idx,checked", [(-1, []), (8, []), (0, ["not a task"])])
async def test_invalid_room_and_checklist(ctx, idx, checked):
    assert (await ctx["client"].put(f'/api/cleaning/{ctx["cid"]}/rooms/{idx}/checklist', headers=auth(ctx, "cleaner"), json={"checked": checked})).status_code == 422


@pytest.mark.asyncio
async def test_empty_rooms_cannot_complete(ctx):
    await ctx["db"].cleaning.update_one({"_id": ObjectId(ctx["cid"])}, {"$set": {"rooms": []}})
    assert (await ctx["client"].put(f'/api/cleaning/{ctx["cid"]}', headers=auth(ctx), json={"status": "completed"})).status_code == 400


@pytest.mark.asyncio
async def test_upload_media_validates_ownership_and_is_idempotent(ctx):
    mid = ObjectId()
    await ctx["db"].media.insert_one({"_id": mid, "is_deleted": False, "kind": "image", "owner_id": str(ctx["users"]["other_cleaner"]["_id"])})
    url = f'/api/cleaning/{ctx["cid"]}/rooms/0/media'
    body = {"phase": "before", "media_id": str(mid)}
    assert (await ctx["client"].post(url, headers=auth(ctx, "cleaner"), json=body)).status_code == 422
    await ctx["db"].media.update_one({"_id": mid}, {"$set": {"owner_id": str(ctx["users"]["cleaner"]["_id"])}})
    for _ in range(2):
        r = await ctx["client"].post(url, headers=auth(ctx, "cleaner"), json=body)
        assert r.status_code == 200
    assert r.json()["rooms"][0]["before"] == [str(mid)]


@pytest.mark.asyncio
async def test_guest_invites_expire_revoke_replace_and_hide_tokens(ctx):
    headers = await invitation(ctx)
    record = await ctx["db"].guest_links.find_one({})
    assert headers["Authorization"][7:] not in str(record)
    assert (await ctx["client"].get("/api/guest/check-in", headers=headers)).status_code == 200
    second = await invitation(ctx)
    assert (await ctx["client"].get("/api/guest/check-in", headers=headers)).status_code == 401
    await ctx["client"].delete(f'/api/bookings/{ctx["bid"]}/guest-link', headers=auth(ctx))
    assert (await ctx["client"].get("/api/guest/check-in", headers=second)).status_code == 401
    third = await invitation(ctx)
    await ctx["db"].guest_links.update_many({}, {"$set": {"expires_at": "2000-01-01"}})
    assert (await ctx["client"].get("/api/guest/check-in", headers=third)).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{"consent": "false"}, {"guest_name": " "}, {"guest_number": "0"}, {"guest_number": "3"}, {"expires_on": "invalid"}, {"expires_on": "2000-01-01"}, {"document_type": "passport"}])
async def test_invalid_guest_document_fields(ctx, payload):
    r = await upload_id(ctx, await invitation(ctx), **payload)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_guest_review_checkin_same_name_guests_and_document_privacy(ctx):
    headers = await invitation(ctx)
    for slot in (1, 2):
        r = await upload_id(ctx, headers, slot)
        assert r.status_code == 200, r.text
        did = r.json()["id"]
        assert (await ctx["client"].get(f"/api/files/{did}", headers=auth(ctx))).status_code == 404
        assert (await ctx["client"].get(f"/api/guest-ids/{did}/image", headers=auth(ctx, "owner"))).status_code == 403
        image = await ctx["client"].get(f"/api/guest-ids/{did}/image", headers=auth(ctx))
        assert image.status_code == 200 and image.headers["cache-control"] == "no-store"
        assert (await ctx["client"].post(f'/api/bookings/{ctx["bid"]}/check-in', headers=auth(ctx))).status_code == 409
        assert (await ctx["client"].post(f"/api/guest-ids/{did}/review", headers=auth(ctx), json={"status": "verified"})).status_code == 200
    r = await ctx["client"].get("/api/guest-ids", headers=auth(ctx))
    assert len(r.json()) == 2 and "storage_key" not in r.text
    assert (await ctx["client"].post(f'/api/bookings/{ctx["bid"]}/check-in', headers=auth(ctx))).status_code == 200
    assert (await ctx["client"].get("/api/guest/check-in", headers=headers)).status_code == 401
    assert await ctx["db"].guest_id_audit.count_documents({"action": "view"}) == 2


@pytest.mark.asyncio
async def test_duplicate_slot_rejection_retry_limits_delete_and_expiry(ctx, monkeypatch):
    headers = await invitation(ctx)
    r = await upload_id(ctx, headers)
    did = r.json()["id"]
    deleted = []
    monkeypatch.setattr(guest_ids, "delete_image", lambda doc: deleted.append(doc["storage_key"]))
    assert (await upload_id(ctx, headers)).status_code == 409
    assert len(deleted) == 1  # Duplicate upload is cleaned up from storage.
    url = f"/api/guest-ids/{did}/review"
    assert (await ctx["client"].post(url, headers=auth(ctx), json={"status": "rejected"})).status_code == 422
    assert (await ctx["client"].post(url, headers=auth(ctx), json={"status": "rejected", "reason": "Unreadable"})).status_code == 200
    await ctx["client"].get(f"/api/guest-ids/{did}/image", headers=auth(ctx))
    assert (await ctx["client"].post(url, headers=auth(ctx), json={"status": "verified"})).status_code == 409
    r = await upload_id(ctx, headers)
    assert r.status_code == 200
    did2 = r.json()["id"]
    await ctx["db"].guest_ids.update_one({"_id": ObjectId(did2)}, {"$set": {"delete_after": "2000-01-01"}})
    assert (await ctx["client"].get(f"/api/guest-ids/{did2}/image", headers=auth(ctx))).status_code == 404
    purge = await ctx["client"].post("/api/guest-ids/purge-expired", headers=auth(ctx))
    assert purge.json()["deleted"] == 1
    assert (await ctx["client"].delete(f"/api/guest-ids/{did}", headers=auth(ctx))).status_code == 200
    document = await ctx["db"].guest_ids.find_one({"_id": ObjectId(did)})
    assert document["deleted"] and document["guest_name"] == "" and "storage_key" not in document
    await ctx["db"].guest_links.update_many({}, {"$set": {"attempts": 6}})
    assert (await upload_id(ctx, headers)).status_code == 429


@pytest.mark.asyncio
@pytest.mark.parametrize("content,ctype,status", [(b"fake", "image/jpeg", 422), (b"<script>", "text/html", 422), (b"x" * (guest_ids.MAX_BYTES + 1), "image/jpeg", 413)], ids=["invalid-image", "html", "oversize"])
async def test_guest_file_validation(ctx, content, ctype, status):
    headers = await invitation(ctx)
    r = await ctx["client"].post("/api/guest/documents", headers=headers, data={"guest_name": "Guest", "guest_number": "1", "document_type": "national_id", "consent": "true"}, files={"file": ("id.jpg", content, ctype)})
    assert r.status_code == status


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [("guests", 0), ("amount", -1), ("ota_commission", -1), ("property_id", "bad-id")])
async def test_invalid_booking_inputs(ctx, field, value):
    payload = {"property_id": ctx["p1"], "guest_name": "Guest", "check_in": "2027-01-01", "check_out": "2027-01-02", field: value}
    assert (await ctx["client"].post("/api/bookings", headers=auth(ctx), json=payload)).status_code == 422


@pytest.mark.asyncio
async def test_deleted_property_and_deactivated_user_denied(ctx):
    await ctx["db"].properties.update_one({"_id": ObjectId(ctx["p2"])}, {"$set": {"is_deleted": True}})
    r = await ctx["client"].post("/api/bookings", headers=auth(ctx), json={"property_id": ctx["p2"], "guest_name": "Guest", "check_in": "2027-01-01", "check_out": "2027-01-02"})
    assert r.status_code == 400
    await ctx["db"].users.update_one({"_id": ctx["users"]["cleaner"]["_id"]}, {"$set": {"active": False}})
    assert (await ctx["client"].get("/api/cleaning", headers=auth(ctx, "cleaner"))).status_code == 401


def test_private_store_fails_closed(monkeypatch):
    monkeypatch.delenv("GUEST_ID_BUCKET", raising=False)
    with pytest.raises(server.HTTPException) as exc:
        guest_ids.private_store()
    assert exc.value.status_code == 503


def test_sanitise_strips_metadata():
    output = guest_ids.sanitise_image(jpeg())
    with Image.open(io.BytesIO(output)) as image:
        assert image.format == "JPEG" and not image.getexif()


def test_s3_public_access_and_kms_version_deletion(monkeypatch):
    from unittest.mock import MagicMock
    s3 = MagicMock()
    monkeypatch.setenv("GUEST_ID_BUCKET", "private-bucket")
    monkeypatch.setenv("GUEST_ID_KMS_KEY", "kms-key")
    monkeypatch.setenv("GUEST_ID_RETENTION_DAYS", "30")
    monkeypatch.setattr(guest_ids.boto3, "client", lambda *args, **kwargs: s3)
    flags = dict.fromkeys(["BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets"], True)
    s3.get_public_access_block.return_value = {"PublicAccessBlockConfiguration": flags}
    s3.put_object.return_value = {"VersionId": "v1"}
    document = guest_ids.store_image("guest-ids/opaque.jpg", jpeg())
    assert s3.put_object.call_args.kwargs["ServerSideEncryption"] == "aws:kms"
    assert s3.put_object.call_args.kwargs["SSEKMSKeyId"] == "kms-key"
    guest_ids.delete_image(document)
    assert s3.delete_object.call_args.kwargs["VersionId"] == "v1"
    flags["BlockPublicPolicy"] = False
    with pytest.raises(server.HTTPException) as exc:
        guest_ids.private_store()
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_admin_must_open_document_before_approval(ctx):
    document = await upload_id(ctx, await invitation(ctx))
    did = document.json()["id"]
    r = await ctx["client"].post(f"/api/guest-ids/{did}/review", headers=auth(ctx), json={"status": "verified"})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_cleaning_concurrent_mutation_returns_conflict(ctx, monkeypatch):
    original = server.checked_cleaning
    async def racing_read(cid, user, writable=False):
        c = await original(cid, user, writable)
        await ctx["db"].cleaning.update_one({"_id": c["_id"]}, {"$inc": {"revision": 1}})
        return c
    monkeypatch.setattr(server, "checked_cleaning", racing_read)
    r = await ctx["client"].put(f'/api/cleaning/{ctx["cid"]}/rooms/0/checklist', headers=auth(ctx, "cleaner"), json={"checked": server.CHECKLIST})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_expired_booking_and_future_checkin_denied(ctx):
    today = datetime.now(guest_ids.INDIA_TZ).date()
    await ctx["db"].bookings.update_one({"_id": ObjectId(ctx["bid"])}, {"$set": {"check_in": (today + timedelta(days=1)).isoformat()}})
    assert (await ctx["client"].post(f'/api/bookings/{ctx["bid"]}/check-in', headers=auth(ctx))).status_code == 409
    await ctx["db"].bookings.update_one({"_id": ObjectId(ctx["bid"])}, {"$set": {"status": "cancelled"}})
    assert (await ctx["client"].post(f'/api/bookings/{ctx["bid"]}/guest-link', headers=auth(ctx))).status_code == 404


@pytest.mark.asyncio
async def test_deletion_failure_keeps_record_for_retry(ctx, monkeypatch):
    r = await upload_id(ctx, await invitation(ctx))
    did = r.json()["id"]
    def failed_delete(doc):
        raise RuntimeError("Storage unavailable")
    monkeypatch.setattr(guest_ids, "delete_image", failed_delete)
    response = await ctx["client"].delete(f"/api/guest-ids/{did}", headers=auth(ctx))
    assert response.status_code == 503 and response.json()["reference"]
    d = await ctx["db"].guest_ids.find_one({"_id": ObjectId(did)})
    assert not d["deleted"] and "storage_key" in d


@pytest.mark.asyncio
async def test_oversized_multipart_request_is_bounded(ctx):
    r = await ctx["client"].post("/api/guest/documents", headers=await invitation(ctx), data={"guest_name": "Guest", "guest_number": "1", "document_type": "national_id", "consent": "true"}, files={"file": ("id.jpg", b"x" * (guest_ids.MAX_BYTES + 128 * 1024), "image/jpeg")})
    assert r.status_code == 413


@pytest.mark.asyncio
async def test_uploaded_cleaning_photo_loses_access_after_reassignment(ctx):
    mid = ObjectId()
    await ctx["db"].media.insert_one({"_id": mid, "owner_id": str(ctx["users"]["cleaner"]["_id"]), "is_deleted": False, "storage_path": "photo", "kind": "image"})
    await ctx["db"].cleaning.update_one({"_id": ObjectId(ctx["cid"])}, {"$set": {"assigned_to": str(ctx["users"]["other_cleaner"]["_id"]), "rooms.0.before": [str(mid)]}})
    assert (await ctx["client"].get(f"/api/files/{mid}", headers=auth(ctx, "cleaner"))).status_code == 404


@pytest.mark.asyncio
async def test_guest_booking_progress_and_repeat_checkin(ctx):
    headers = await invitation(ctx)
    for slot in (1, 2):
        before = (await ctx["client"].get("/api/guest-bookings", headers=auth(ctx))).json()[0]
        assert before["verified_guests"] == slot - 1 and not before["can_check_in"]
        did = (await upload_id(ctx, headers, slot)).json()["id"]
        await ctx["client"].get(f"/api/guest-ids/{did}/image", headers=auth(ctx))
        await ctx["client"].post(f"/api/guest-ids/{did}/review", headers=auth(ctx), json={"status": "verified"})
    ready = (await ctx["client"].get("/api/guest-bookings", headers=auth(ctx))).json()[0]
    assert ready["can_check_in"] and ready["verified_guests"] == 2
    url = f'/api/bookings/{ctx["bid"]}/check-in'
    assert (await ctx["client"].post(url, headers=auth(ctx))).status_code == 200
    assert (await ctx["client"].post(url, headers=auth(ctx))).status_code == 409
    checked = (await ctx["client"].get("/api/guest-bookings", headers=auth(ctx))).json()[0]
    assert checked["guest_checked_in_at"] and not checked["can_check_in"]
    assert await ctx["db"].guest_id_audit.count_documents({"action": "check_in"}) == 1


@pytest.mark.asyncio
async def test_guest_booking_queue_dates_and_access(ctx):
    for role in ("owner", "cleaner", "supervisor"):
        assert (await ctx["client"].get("/api/guest-bookings", headers=auth(ctx, role))).status_code == 403
    today = datetime.now(guest_ids.INDIA_TZ).date()
    await ctx["db"].bookings.update_one({"_id": ObjectId(ctx["bid"])}, {"$set": {"check_in": (today + timedelta(days=1)).isoformat()}})
    upcoming = (await ctx["client"].get("/api/guest-bookings", headers=auth(ctx))).json()[0]
    assert not upcoming["can_check_in"] and upcoming["check_in_reason"] == "Check-in date has not arrived"
    await ctx["db"].bookings.update_one({"_id": ObjectId(ctx["bid"])}, {"$set": {"check_out": today.isoformat()}})
    assert (await ctx["client"].get("/api/guest-bookings", headers=auth(ctx))).json() == []

@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["owner", "cleaner", "supervisor"])
async def test_admin_overrides_are_admin_only(ctx, role):
    for url, body in [(f'/api/cleaning/{ctx["cid"]}/admin-action', {"action": "complete", "note": "Test"}),
                      (f'/api/bookings/{ctx["bid"]}/guest-admin-action', {"action": "check_in", "note": "Test"})]:
        assert (await ctx["client"].post(url, headers=auth(ctx, role), json=body)).status_code == 403


@pytest.mark.asyncio
async def test_admin_cleaning_override_reopen_preserves_evidence(ctx):
    url = f'/api/cleaning/{ctx["cid"]}/admin-action'
    for note in ("", "   "):
        assert (await ctx["client"].post(url, headers=auth(ctx), json={"action": "complete", "note": note})).status_code == 422
    complete = await ctx["client"].post(url, headers=auth(ctx), json={"action": "complete", "note": "Inspected in person; camera unavailable"})
    assert complete.status_code == 200 and complete.json()["status"] == "completed"
    await ctx["db"].cleaning.update_one({"_id": ObjectId(ctx["cid"])}, {"$set": {"rooms.0.before": ["old-photo"], "rooms.0.checked": server.CHECKLIST}})
    uid = str(ctx["users"]["other_cleaner"]["_id"])
    assert (await ctx["client"].post(url, headers=auth(ctx), json={"action": "reassign", "assigned_to": uid, "note": "Needs rework"})).status_code == 422
    await ctx["db"].users.update_one({"_id": ObjectId(uid)}, {"$set": {"property_ids": [ctx["p1"]]}})
    reopened = await ctx["client"].post(url, headers=auth(ctx), json={"action": "reassign", "assigned_to": uid, "note": "Bathroom not cleaned"})
    data = reopened.json()
    assert reopened.status_code == 200 and data["status"] == "pending" and data["assigned_to"] == uid
    assert "completed_at" not in data and data["rooms"][0]["before"] == [] and data["rooms"][0]["checked"] == []
    assert data["admin_history"][-1]["before"]["rooms"][0]["before"] == ["old-photo"]
    assert data["admin_history"][-1]["note"] == "Bathroom not cleaned"
    assert (await ctx["client"].get(f'/api/cleaning/{ctx["cid"]}', headers=auth(ctx, "cleaner"))).status_code == 404
    assert (await ctx["client"].put(f'/api/cleaning/{ctx["cid"]}', headers=auth(ctx, "other_cleaner"), json={"notes": "Starting rework"})).status_code == 200


@pytest.mark.asyncio
async def test_guest_admin_override_undo_and_privacy(ctx):
    invite = await invitation(ctx)
    url = f'/api/bookings/{ctx["bid"]}/guest-admin-action'
    for note in ("", "   "):
        assert (await ctx["client"].post(url, headers=auth(ctx), json={"action": "check_in", "note": note})).status_code == 422
    today = datetime.now(guest_ids.INDIA_TZ).date()
    await ctx["db"].bookings.update_one({"_id": ObjectId(ctx["bid"])}, {"$set": {"check_in": (today + timedelta(days=1)).isoformat()}})
    assert (await ctx["client"].post(url, headers=auth(ctx), json={"action": "check_in", "note": "Early arrival; IDs inspected in person"})).status_code == 200
    assert (await ctx["client"].get("/api/guest/check-in", headers=invite)).status_code == 401
    assert await ctx["db"].guest_ids.count_documents({"status": "verified"}) == 0
    for path in ("/api/bookings", f'/api/bookings/{ctx["bid"]}'):
        assert "admin_history" not in (await ctx["client"].get(path, headers=auth(ctx, "owner"))).text
    assert (await ctx["client"].post(url, headers=auth(ctx), json={"action": "undo_check_in", "note": "Wrong guest checked in"})).status_code == 200
    booking = await ctx["db"].bookings.find_one({"_id": ObjectId(ctx["bid"])})
    assert "guest_checked_in_at" not in booking and len(booking["admin_history"]) == 2
    assert (await ctx["client"].get("/api/guest/check-in", headers=invite)).status_code == 401


@pytest.mark.asyncio
async def test_guest_admin_review_can_be_reversed_without_exposing_other_booking(ctx):
    did = (await upload_id(ctx, await invitation(ctx))).json()["id"]
    url = f'/api/bookings/{ctx["bid"]}/guest-admin-action'
    for action, status in (("approve_id", "verified"), ("reset_id", "pending"), ("reject_id", "rejected")):
        r = await ctx["client"].post(url, headers=auth(ctx), json={"action": action, "document_id": did, "note": "Admin correction"})
        assert r.status_code == 200
        document = await ctx["db"].guest_ids.find_one({"_id": ObjectId(did)})
        assert document["status"] == status
    assert len(document["admin_history"]) == 3
    other = ObjectId()
    await ctx["db"].bookings.insert_one({"_id": other, "status": "confirmed"})
    assert (await ctx["client"].post(f'/api/bookings/{other}/guest-admin-action', headers=auth(ctx), json={"action": "reset_id", "document_id": did, "note": "Wrong booking"})).status_code == 404
