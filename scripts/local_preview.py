"""Local-only demo of the real app routes. No production database or cloud storage.

Run with .venv/Scripts/python.exe scripts/local_preview.py, then open localhost:8765.
Database records reset on restart; uploaded test files remain in .local-preview/media.
Never use this launcher for deployment or real guest documents.
"""
import io
import os
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from mongomock_motor import AsyncMongoMockClient
from PIL import Image, ImageDraw
from fastapi import HTTPException
from fastapi.responses import FileResponse, HTMLResponse

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / ".local-preview" / "web"
MEDIA = ROOT / ".local-preview" / "media"
MEDIA.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "backend"))
os.environ.update(MONGO_URL="mongodb://127.0.0.1:27017", DB_NAME="britsmaid_local_demo",
                  JWT_SECRET=secrets.token_urlsafe(48), GUEST_ID_RETENTION_DAYS="7")
with patch("motor.motor_asyncio.AsyncIOMotorClient", AsyncMongoMockClient):
    import server
import guest_ids

PASSWORD = secrets.token_urlsafe(18) if os.environ.get("BRITSMAID_PREVIEW_PRIVATE") == "1" else "Preview@2026"
if os.environ.get("BRITSMAID_PREVIEW_PRIVATE") == "1":
    account_file = ROOT / ".local-preview" / "private-test-accounts.txt"
    account_file.write_text("Local synthetic test accounts only. Resets on restart.\n" + "\n".join(f"{r}@example.com : {PASSWORD}" for r in ("admin", "owner", "cleaner", "supervisor", "relief")), encoding="utf-8")


def media_path(key):
    target = (MEDIA / key).resolve()
    if not target.is_relative_to(MEDIA.resolve()):
        raise HTTPException(400, "Invalid demo file path")
    return target


def put_local(key, data, content_type="image/jpeg"):
    target = media_path(key)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {"path": key, "size": len(data)}


def get_local(key):
    target = media_path(key)
    if not target.is_file():
        raise HTTPException(404, "Demo file missing")
    return target.read_bytes(), "image/jpeg"


def store_demo_id(key, data):
    put_local(key, data)
    return {"storage_key": key, "storage_bucket": "LOCAL-DEMO-NOT-ENCRYPTED", "storage_version": None}


def offline(*args, **kwargs):
    raise HTTPException(503, "Google login and external integrations are disabled in this local demo; use a test account")


server.put_object = put_local
server.get_object = get_local
server.requests.get = offline
server.requests.post = offline
guest_ids.private_store = lambda: (None, "LOCAL-DEMO-NOT-ENCRYPTED", "no-production-key", 7)
guest_ids.store_image = store_demo_id
guest_ids.read_image = lambda doc: get_local(doc["storage_key"])[0]
guest_ids.delete_image = lambda doc: media_path(doc["storage_key"]).unlink(missing_ok=True)

# Replace provisioning/background jobs in this separate launcher only.
server.app.router.on_startup.clear()
server.app.router.on_shutdown.clear()


def sample_photo(label, colour):
    image = Image.new("RGB", (1000, 650), colour)
    draw = ImageDraw.Draw(image)
    draw.text((70, 120), "BRITSMAID LOCAL PREVIEW", fill="white", font_size=44)
    draw.text((70, 230), label, fill="white", font_size=36)
    draw.text((70, 380), "SAMPLE ONLY - NOT A REAL GUEST DOCUMENT", fill="white", font_size=26)
    buffer = io.BytesIO()
    image.save(buffer, "JPEG")
    return buffer.getvalue()


@server.app.on_event("startup")
async def seed_local_preview():
    db = server.db
    await server.training.indexes()
    await db.users.create_index("email", unique=True)
    await db.guest_links.create_index("token_hash", unique=True)
    await db.guest_ids.create_index([("booking_id", 1), ("guest_number", 1)], unique=True, partialFilterExpression={"active": True})
    await server.seed_demo()
    from training import LessonIn
    sample = LessonIn(title="SAMPLE — Room photo basics", instructions="SAMPLE ONLY: not approved business training.\n1. Open your assigned task and choose the room.\n2. Save a before photo before cleaning.\n3. Follow your supervisor's approved cleaning instructions.\n4. Save an after photo, finish the checklist and submit for review.", onboarding=True, refresher_days=30)
    await db.training_lessons.insert_one({"draft": sample.model_dump(), "revision": 0, "archived": False, "created_at": server.now_iso(), "updated_at": server.now_iso()})
    properties = await db.properties.find({}).sort("name", 1).to_list(10)
    pids = [str(p["_id"]) for p in properties]
    users = {}
    for role, name in [("admin", "Demo Admin"), ("owner", "Demo Property Owner"), ("cleaner", "Demo Cleaner"), ("supervisor", "Demo Supervisor")]:
        user = {"name": name, "email": f"{role}@example.com", "password_hash": server.hash_pw(PASSWORD),
                "role": role, "property_ids": pids[:1] if role == "owner" else pids if role != "admin" else [],
                "active": True, "phone": "", "created_at": server.now_iso()}
        user["_id"] = (await db.users.insert_one(user)).inserted_id
        users[role] = user
    await db.users.insert_one({"name": "Demo Relief Cleaner", "email": "relief@example.com", "password_hash": server.hash_pw(PASSWORD),
        "role": "cleaner", "property_ids": pids, "active": True, "phone": "", "created_at": server.now_iso()})
    await db.cleaning.update_many({}, {"$set": {"assigned_to": str(users["cleaner"]["_id"])}})
    mids = []
    for phase, colour in [("Before cleaning (sample)", "#8a6045"), ("After cleaning (sample)", "#185f65")]:
        key = f"demo/{len(mids)}.jpg"
        content = sample_photo(phase, colour)
        put_local(key, content)
        result = await db.media.insert_one({"storage_path": key, "content_type": "image/jpeg", "kind": "image", "original_name": "sample.jpg",
                                            "size": len(content), "owner_id": str(users["cleaner"]["_id"]), "created_at": server.now_iso(), "is_deleted": False})
        mids.append(str(result.inserted_id))
    today = datetime.now(guest_ids.INDIA_TZ).date()
    for i, status in enumerate(["pending", "in_progress", "awaiting_review", "completed"]):
        p = properties[i % len(properties)]
        await db.cleaning.insert_one({"property_id": str(p["_id"]), "booking_id": None, "date": (today - timedelta(days=i)).isoformat(),
            "assigned_to": str(users["cleaner"]["_id"]), "status": status, "notes": "Sample turnover for exploring the updated workflow.",
            "rooms": [{"name": name, "before": [mids[0]] if status != "pending" else [], "after": [mids[1]] if status in ("awaiting_review", "completed") else [],
                       "checked": server.CHECKLIST if status in ("awaiting_review", "completed") else []} for name in p["rooms"]], "created_at": server.now_iso(),
            **({"completed_at": server.now_iso()} if status == "completed" else {})})
    p = properties[0]
    b = {"property_id": str(p["_id"]), "guest_name": "Sample Guest (demo)", "guest_phone": "", "guest_email": "sample@example.com", "guests": 1,
         "ota": "Direct", "check_in": today.isoformat(), "check_out": (today + timedelta(days=2)).isoformat(), "status": "confirmed",
         "amount": 12000, "ota_commission": 0, "source": "manual", "notes": "Demo only", "created_at": server.now_iso()}
    bid = str((await db.bookings.insert_one(b)).inserted_id)
    doc = store_demo_id("guest-ids/sample.jpg", sample_photo("Fictional guest ID for testing", "#364868"))
    await db.guest_ids.insert_one({**doc, "booking_id": bid, "property_id": str(p["_id"]), "guest_name": "Sample Guest (demo)", "guest_number": 1,
        "document_type": "national_id", "expires_on": "9999-12-31", "status": "pending", "active": True, "deleted": False,
        "consented_at": server.now_iso(), "created_at": server.now_iso(), "delete_after": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()})
    await server.create_invoice(server.InvoiceIn(type="guest", property_id=str(p["_id"]), bill_to_name="Sample Guest (demo)",
        items=[server.InvoiceItem(description="Sample villa stay", qty=2, rate=6000)], issue_date=today.isoformat()), users["admin"])
    for p in properties:
        await server.create_owner_report(server.OwnerReportIn(property_id=str(p["_id"]), month=today.isoformat()[:7],
            title=f"{p['name']} - sample owner report", condition_notes="Sample report. All amounts and guests are fictional.", media_ids=mids), users["admin"])
    print("LOCAL DEMO READY - four roles @example.com - database resets on restart; use the printed listener addresses", flush=True)


@server.app.get("/preview-health")
async def preview_health():
    return {"mode": "local-demo", "database": "in-memory", "storage": "local-demo-unencrypted", "production_connected": False}


@server.app.get("/{preview_path:path}", include_in_schema=False)
async def preview_frontend(preview_path: str):
    if preview_path.startswith("api/"):
        raise HTTPException(404, "Not found")
    target = (WEB / preview_path).resolve()
    if not target.is_relative_to(WEB.resolve()):
        raise HTTPException(404, "Not found")
    # Exported pnpm asset paths can exceed Windows' 260-character path limit.
    # Returning index.html for a missed font makes every icon an empty box.
    disk_target = Path("\\\\?\\" + str(target)) if os.name == "nt" else target
    if disk_target.is_file() and target.name != "index.html":
        font_type = {".ttf": "font/ttf", ".otf": "font/otf", ".woff": "font/woff", ".woff2": "font/woff2"}.get(target.suffix.lower())
        return FileResponse(disk_target, media_type=font_type)
    if preview_path.startswith(("assets/", "_expo/")):
        raise HTTPException(404, "Preview asset not found")
    index = WEB / "index.html"
    if not index.is_file():
        return HTMLResponse("Preview build is not ready yet.", status_code=503)
    banner = '<div style="position:fixed;bottom:0;left:0;right:0;z-index:99999;background:#fff0bc;color:#392c00;padding:5px 10px;text-align:center;font:12px sans-serif;pointer-events:none">LOCAL DEMO - Sample data resets on restart. Use dummy photos/IDs only. Google login disabled.</div>'
    frame_style = '<style id="local-preview-frame">#root{height:calc(100% - 40px)!important}</style>'
    page = index.read_text(encoding="utf-8").replace("</head>", frame_style + "</head>")
    return HTMLResponse(page.replace("</body>", banner + "</body>"), headers={"Cache-Control": "no-store"})


if __name__ == "__main__":
    import argparse
    import ipaddress
    import socket
    import uvicorn
    parser = argparse.ArgumentParser(description="Local demo; optionally share on a private Wi-Fi IPv4 address")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--lan-ip", help="Computer's private Wi-Fi IPv4 address")
    options = parser.parse_args()
    addresses = ["127.0.0.1"]
    if options.lan_ip:
        address = ipaddress.IPv4Address(options.lan_ip)
        if not address.is_private or address.is_loopback or address.is_unspecified or address.is_link_local or address.is_multicast:
            parser.error("Use the computer's private Wi-Fi IPv4 address")
        addresses.append(str(address))
    sockets = []
    try:
        for address in addresses:
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.bind((address, options.port))
            listener.listen(128)
            listener.setblocking(False)
            sockets.append(listener)
        for address in addresses:
            print(f"Demo preview: http://{address}:{options.port}", flush=True)
        config = uvicorn.Config(server.app, host="127.0.0.1", port=options.port, access_log=False)
        uvicorn.Server(config).run(sockets=sockets)
    finally:
        for listener in sockets:
            listener.close()
