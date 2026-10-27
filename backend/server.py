from fastapi import FastAPI, APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, Request
from fastapi.responses import Response, HTMLResponse
from fastapi.concurrency import run_in_threadpool
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, BeforeValidator, ConfigDict, EmailStr, field_validator
from validation import valid_date, valid_month, month_bounds
from reservations import claim_nights, release_unused
from safe_calendar_fetch import fetch_calendar, CalendarFetchError, validate_url
from typing import Annotated, List, Optional, Literal, Any
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
from bson import ObjectId
import os, logging, uuid, secrets, html, json, asyncio, string, hashlib, re
from zoneinfo import ZoneInfo
from pymongo.errors import DuplicateKeyError
import bcrypt, jwt, requests

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]
JWT_SECRET = os.environ['JWT_SECRET']
JWT_ALG = "HS256"
TOKEN_DAYS = 7

app = FastAPI(title="Britsmaid API")
api = APIRouter(prefix="/api")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("britsmaid")

# ---------------------------------------------------------------- Mongo helpers
PyObjectId = Annotated[str, BeforeValidator(lambda v: str(v) if isinstance(v, ObjectId) else v)]


class BaseDocument(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    id: Optional[PyObjectId] = Field(default=None, alias="_id")

    @classmethod
    def from_mongo(cls, doc: Optional[dict]):
        if doc is None:
            return None
        d = dict(doc)
        for k, v in list(d.items()):
            if isinstance(v, ObjectId) and k != "_id":
                d[k] = str(v)
        return cls(**d)

    def to_mongo(self) -> dict:
        d = self.model_dump(by_alias=True, exclude_none=False)
        d.pop("_id", None)
        d.pop("id", None)
        return d

    def out(self) -> dict:
        d = self.model_dump()
        d.pop("password_hash", None)
        for key in list(d):
            if key.startswith("mfa_"):
                d.pop(key)
        return d


def out(doc):
    return BaseDocument.from_mongo(doc).out() if doc else None


def oid(v: str) -> ObjectId:
    if not ObjectId.is_valid(v):
        raise HTTPException(404, "Not found")
    return ObjectId(v)


def now_iso():
    return datetime.now(timezone.utc).isoformat()

# ---------------------------------------------------------------- Storage
STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
APP_NAME = "britsmaid"
storage_key = None


def delete_object(path):
    raise HTTPException(503, "Photo deletion storage is not configured")


def init_storage():
    global storage_key
    if storage_key:
        return storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
    resp.raise_for_status()
    storage_key = resp.json()["storage_key"]
    return storage_key


def put_object(path: str, data: bytes, content_type: str) -> dict:
    global storage_key
    key = init_storage()
    resp = requests.put(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key, "Content-Type": content_type}, data=data, timeout=180)
    if resp.status_code == 503:
        storage_key = None
        key = init_storage()
        resp = requests.put(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key, "Content-Type": content_type}, data=data, timeout=180)
    if resp.status_code == 402:
        raise HTTPException(402, "Storage credits exhausted")
    resp.raise_for_status()
    return resp.json()


def get_object(path: str):
    key = init_storage()
    resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=120)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")

# ---------------------------------------------------------------- Auth
def hash_pw(p: str) -> str:
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()


def verify_pw(p: str, h: str) -> bool:
    if len(p.encode()) > 72:
        return False
    try:
        return bcrypt.checkpw(p.encode(), h.encode())
    except Exception:
        return False


DUMMY_HASH = hash_pw("dummy-password-xyz")


def issue_token(user: dict) -> str:
    n = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(user["_id"]), "role": user["role"], "sv": user.get("session_version", 0), "jti": uuid.uuid4().hex, "iat": n, "exp": n + timedelta(days=TOKEN_DAYS)}, JWT_SECRET, algorithm=JWT_ALG)


async def user_from_token(token: Optional[str]):
    if not token:
        raise HTTPException(401, "Not authenticated")
    if await db.revoked_sessions.find_one({"_id": hashlib.sha256(token.encode()).hexdigest()}):
        raise HTTPException(401, "Session ended. Please sign in again.")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.InvalidTokenError:
        # Google sign-in sessions (Emergent-managed) are validated by lookup
        sess = await db.user_sessions.find_one({"session_token": token})
        if not sess:
            raise HTTPException(401, "Invalid token")
        exp = sess["expires_at"]
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            raise HTTPException(401, "Session expired")
        payload = {"sub": sess["user_id"], "sv": sess.get("session_version", 0)}
    if payload.get("purpose", "access") != "access":
        raise HTTPException(401, "Invalid token")
    return await active_token_user(payload)


async def active_token_user(payload):
    uid = payload.get("sub")
    if not uid or not ObjectId.is_valid(uid):
        raise HTTPException(401, "Invalid token")
    user = await db.users.find_one({"_id": ObjectId(uid), "active": True})
    if not user:
        raise HTTPException(401, "Invalid token")
    if payload.get("sv", 0) != user.get("session_version", 0):
        raise HTTPException(401, "Your password changed. Please sign in again.")
    return user


async def current_user(request: Request):
    token = request_token(request)
    if token and not request.headers.get("Authorization") and request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin", "")
        expected = os.getenv("PUBLIC_APP_URL", str(request.base_url).rstrip("/"))
        if origin != expected or request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "Open this action inside Britsmaid and try again.")
    return await user_from_token(token)


def request_token(request):
    auth = request.headers.get("Authorization", "")
    return auth[7:] if auth.lower().startswith("bearer ") else request.cookies.get("bm_session")


@api.post("/auth/logout")
async def end_session(request: Request, user=Depends(current_user)):
    token = request_token(request)
    # Keep revocation beyond the longest supported access-token lifetime.
    await db.revoked_sessions.update_one(
        {"_id": hashlib.sha256(token.encode()).hexdigest()},
        {"$set": {"expires_at": datetime.now(timezone.utc) + timedelta(days=TOKEN_DAYS + 1)}}, upsert=True)
    await db.user_sessions.delete_many({"session_token": token})
    response = Response(content='{"ok":true}', media_type="application/json")
    response.delete_cookie("bm_session", path="/api", secure=True, httponly=True, samesite="strict")
    return response


async def admin_user(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    return user


async def staff_user(user=Depends(current_user)):
    """Admin or cleaner (internal team)."""
    if user["role"] not in ("admin", "cleaner", "supervisor"):
        raise HTTPException(403, "Team members only")
    return user


async def finance_user(user=Depends(current_user)):
    """Admin or owner (owners are scoped to their villas)."""
    if user["role"] not in ("admin", "owner"):
        raise HTTPException(403, "Not allowed")
    return user


def owner_pids(user) -> Optional[List[str]]:
    """None = unrestricted; list = villas this owner may see."""
    return list(user.get("property_ids") or []) if user["role"] != "admin" else None


def check_pid(user, pid: str):
    allowed = owner_pids(user)
    if allowed is not None and pid not in allowed:
        raise HTTPException(404, "Not found")


def scope(user, q: dict, field: str = "property_id"):
    allowed = owner_pids(user)
    if allowed is not None:
        if q.get(field):
            check_pid(user, q[field])
        else:
            q[field] = {"$in": allowed}
    return q


class LoginIn(BaseModel):
    email: EmailStr
    password: str
    mfa_code: str = Field(default="", max_length=40)
    browser_session: bool = False


class StaffIn(BaseModel):
    name: str
    email: EmailStr
    password: str = Field(min_length=12, max_length=72)
    role: Literal["admin", "cleaner", "supervisor", "owner"] = "cleaner"
    property_ids: List[str] = []
    phone: str = ""

    @field_validator("password")
    @classmethod
    def bounded_password(cls, value):
        if value is not None and len(value.encode()) > 72:
            raise ValueError("Password must fit within 72 UTF-8 bytes")
        return value


class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[Literal["admin", "cleaner", "supervisor", "owner"]] = None
    phone: Optional[str] = None
    property_ids: Optional[List[str]] = None
    password: Optional[str] = Field(default=None, min_length=12, max_length=72)

    @field_validator("password")
    @classmethod
    def bounded_password(cls, value):
        if value is not None and len(value.encode()) > 72:
            raise ValueError("Password must fit within 72 UTF-8 bytes")
        return value


async def validate_pids(pids: List[str]) -> List[str]:
    pids = list(dict.fromkeys(pids))
    if any(not ObjectId.is_valid(x) for x in pids):
        raise HTTPException(422, "Invalid property id")
    if await db.properties.count_documents({"_id": {"$in": [ObjectId(x) for x in pids]}, "is_deleted": {"$ne": True}}) != len(pids):
        raise HTTPException(400, "One or more properties do not exist")
    return pids


@api.post("/auth/login")
async def login(body: LoginIn):
    email = body.email.strip().lower()
    user = await db.users.find_one({"email": email})
    ok = verify_pw(body.password, user["password_hash"] if user else DUMMY_HASH)
    if not user or not user.get("active") or not ok:
        raise HTTPException(401, "Incorrect email or password")
    if user.get("mfa_secret"):
        if not body.mfa_code:
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "Enter your authenticator or recovery code", "code": "MFA_REQUIRED"}, status_code=401)
        if not await admin_mfa.verify(user, body.mfa_code):
            raise HTTPException(401, "Authenticator/recovery code incorrect or already used")
    if body.browser_session:
        from fastapi.responses import JSONResponse
        token = issue_token(user)
        response = JSONResponse({"cookie_session": True, "user": out(user)})
        response.set_cookie("bm_session", token, max_age=TOKEN_DAYS * 86400, path="/api", secure=True, httponly=True, samesite="strict")
        return response
    return {"access_token": issue_token(user), "token_type": "bearer", "user": out(user)}


class SessionIn(BaseModel):
    session_id: str


@api.post("/auth/session")
async def google_session(body: SessionIn):
    import httpx
    async with httpx.AsyncClient(timeout=20) as hc:
        r = await hc.get("https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data", headers={"X-Session-ID": body.session_id})
    if r.status_code != 200:
        raise HTTPException(401, "Google sign-in failed, please try again")
    data = r.json()
    email = (data.get("email") or "").strip().lower()
    user = await db.users.find_one({"email": email, "active": True})
    if not user:
        raise HTTPException(403, f"No Britsmaid account for {email}. Ask your admin to add this email in Team & logins.")
    token = data["session_token"]
    await db.users.update_one({"_id": user["_id"]}, {"$set": {"picture": data.get("picture"), "google_linked": True}})
    await db.user_sessions.update_one({"session_token": token}, {"$set": {"session_token": token, "user_id": str(user["_id"]),
                                      "session_version": user.get("session_version", 0), "expires_at": datetime.now(timezone.utc) + timedelta(days=7), "created_at": datetime.now(timezone.utc)}}, upsert=True)
    return {"session_token": token, "user": out(await db.users.find_one({"_id": user["_id"]}))}


@api.get("/auth/me")
async def me(user=Depends(current_user)):
    return out(user)


@api.get("/users")
async def list_users(_=Depends(admin_user)):
    return [out(u) for u in await db.users.find({"active": True}).sort("created_at", 1).to_list(500)]


@api.post("/users")
async def create_user(body: StaffIn, _=Depends(admin_user)):
    email = body.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(409, "Email already registered")
    if body.role == "owner" and not body.property_ids:
        raise HTTPException(400, "Assign at least one villa to the owner")
    pids = await validate_pids(body.property_ids) if body.role != "admin" else []
    doc = {"name": body.name, "email": email, "password_hash": hash_pw(body.password), "role": body.role, "property_ids": pids, "phone": body.phone.strip(), "active": True, "created_at": now_iso()}
    r = await db.users.insert_one(doc)
    if doc.get("role") == "cleaner":
        await training.onboarding({**doc, "_id": r.inserted_id})
    return out(await db.users.find_one({"_id": r.inserted_id}))


@api.put("/users/{uid}")
async def update_user(uid: str, body: UserUpdate, admin=Depends(admin_user)):
    u = await db.users.find_one({"_id": oid(uid), "active": True})
    if not u:
        raise HTTPException(404, "User not found")
    changes: dict[str, Any] = {}
    if body.role and body.role != u["role"]:
        if str(admin["_id"]) == uid:
            raise HTTPException(400, "You cannot change your own role")
        if body.role == "owner" and not body.property_ids:
            raise HTTPException(400, "Assign at least one villa to the owner")
        changes["role"] = body.role
        changes["property_ids"] = []
        if body.role == "admin":
            changes["property_ids"] = []
        u["role"] = body.role
    if body.name:
        changes["name"] = body.name
    if body.phone is not None:
        changes["phone"] = body.phone.strip()
    if body.password:
        changes["password_hash"] = hash_pw(body.password)
    if body.property_ids is not None and u["role"] == "admin" and "role" in changes:
        pass
    elif body.property_ids is not None:
        if u["role"] == "admin":
            raise HTTPException(400, "Admins do not need villa assignments")
        if not body.property_ids and u["role"] == "owner":
            raise HTTPException(400, "Assign at least one villa")
        changes["property_ids"] = await validate_pids(body.property_ids)
    if changes:
        update = {"$set": changes}
        if body.password:
            update["$inc"] = {"session_version": 1}
            await db.user_sessions.delete_many({"user_id": str(u["_id"])})
        await db.users.update_one({"_id": u["_id"]}, update)
    updated = await db.users.find_one({"_id": u["_id"]})
    if changes.get("role") == "cleaner":
        await training.onboarding(updated)
    return out(updated)


@api.post("/users/{uid}/reset-password")
async def reset_password(uid: str, _=Depends(admin_user)):
    u = await db.users.find_one({"_id": oid(uid), "active": True})
    if not u:
        raise HTTPException(404, "User not found")
    alphabet = string.ascii_letters + string.digits
    temp = "BM-" + "".join(secrets.choice(alphabet) for _ in range(16))
    await db.users.update_one({"_id": u["_id"]}, {"$set": {"password_hash": hash_pw(temp)}, "$inc": {"session_version": 1}})
    await db.user_sessions.delete_many({"user_id": str(u["_id"])})
    return {"user": out(u), "temp_password": temp}


@api.delete("/users/{uid}")
async def deactivate_user(uid: str, admin=Depends(admin_user)):
    if str(admin["_id"]) == uid:
        raise HTTPException(400, "You cannot remove yourself")
    await db.users.update_one({"_id": oid(uid)}, {"$set": {"active": False}, "$inc": {"session_version": 1}})
    await db.user_sessions.delete_many({"user_id": uid})
    return {"ok": True}

# ---------------------------------------------------------------- Media
photo_processing_lock = asyncio.Semaphore(1)
@api.post("/upload")
async def upload(file: UploadFile = File(...), request_key: Optional[str] = Form(None), user=Depends(staff_user)):
    data = await file.read(100 * 1024 * 1024 + 1)
    if len(data) > 100 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 100MB)")
    ctype = file.content_type or "application/octet-stream"
    if ctype.startswith("image/") or ctype == "application/octet-stream":
        from media_images import normalise_photo
        async with photo_processing_lock:
            data = await run_in_threadpool(normalise_photo, data)
        ctype, ext = "image/jpeg", "jpg"
    elif ctype == "video/mp4" and len(data) > 12 and data[4:8] == b"ftyp":
        ext = "mp4"
    elif ctype == "video/quicktime" and len(data) > 12 and data[4:8] == b"ftyp":
        ext = "mov"
    else:
        raise HTTPException(422, "Choose a supported photo or MP4/MOV video")
    if request_key and not re.fullmatch(r"[A-Za-z0-9_-]{8,120}", request_key):
        raise HTTPException(422, "Invalid upload retry reference")
    digest = hashlib.sha256(data).hexdigest()
    media_oid = ObjectId(hashlib.sha256(f"{user['_id']}:{request_key}".encode()).hexdigest()[:24]) if request_key else ObjectId()
    existing = await db.media.find_one({"_id": media_oid})
    if existing:
        if existing.get("upload_digest") != digest or existing.get("is_deleted"):
            raise HTTPException(409, "Upload reference changed; select the original photo or start a new capture")
        return out(existing)
    path = f"{APP_NAME}/uploads/{user['_id']}/{media_oid}-{digest[:32]}.{ext}"
    res = await run_in_threadpool(put_object, path, data, ctype)
    doc = {"storage_path": res["path"], "content_type": ctype, "kind": "video" if ctype.startswith("video") else "image",
           "original_name": file.filename, "size": res.get("size"), "owner_id": str(user["_id"]), "created_at": now_iso(), "is_deleted": False}
    doc.update(_id=media_oid, upload_digest=digest)
    try:
        await db.media.insert_one(doc)
    except DuplicateKeyError:
        existing = await db.media.find_one({"_id": media_oid})
        if existing.get("upload_digest") != digest:
            raise HTTPException(409, "Upload reference already used for a different photo")
    return out(await db.media.find_one({"_id": media_oid}))


async def stream_media(media_id: str):
    m = await db.media.find_one({"_id": oid(media_id), "is_deleted": False})
    if not m:
        raise HTTPException(404, "File not found")
    data, ctype = await run_in_threadpool(get_object, m["storage_path"])
    safe_type = m.get("content_type") or ctype
    if safe_type not in ("image/jpeg", "image/png", "video/mp4", "video/quicktime"):
        raise HTTPException(422, "This file cannot be displayed safely. Upload a new photo or video.")
    return Response(content=data, media_type=safe_type, headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox"})


async def authorize_media(media_id, user):
    media = await db.media.find_one({"_id": oid(media_id), "is_deleted": False})
    if not media:
        raise HTTPException(404, "File not found")
    if user["role"] != "admin":
        cover = await db.properties.find_one({"cover_media_id": media_id, "is_deleted": {"$ne": True},
            "_id": {"$in": [oid(pid) for pid in owner_pids(user)]}})
        if cover:
            return
        cq = scope(user, {"$or": [{"rooms.before": media_id}, {"rooms.after": media_id}]})
        if user["role"] == "cleaner":
            cq["assigned_to"] = str(user["_id"])
        linked = await db.cleaning.find_one(cq)
        if not linked and user["role"] == "owner":
            linked = await db.owner_reports.find_one(scope(user, {"media_ids": media_id}))
        if not linked:
            linked_elsewhere = await db.cleaning.find_one({"$or": [{"rooms.before": media_id}, {"rooms.after": media_id}]})
            linked_elsewhere = linked_elsewhere or await db.owner_reports.find_one({"media_ids": media_id})
            if linked_elsewhere or media.get("owner_id") != str(user["_id"]) or not owner_pids(user):
                raise HTTPException(404, "File not found")


@api.post("/files/{media_id}/ticket")
async def media_ticket(media_id: str, request: Request, user=Depends(current_user)):
    await authorize_media(media_id, user)
    now = datetime.now(timezone.utc)
    ticket = jwt.encode({"sub": str(user["_id"]), "sv": user.get("session_version", 0),
        "purpose": "file", "aud": "britsmaid-media", "media_id": media_id,
        "session_key": hashlib.sha256(request_token(request).encode()).hexdigest(),
        "iat": now, "exp": now + timedelta(minutes=5)}, JWT_SECRET, algorithm=JWT_ALG)
    return {"ticket": ticket}


@api.get("/files/{media_id}")
async def get_file(media_id: str, request: Request, ticket: Optional[str] = None):
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        user = await user_from_token(auth[7:])
    else:
        try:
            payload = jwt.decode(ticket or "", JWT_SECRET, algorithms=[JWT_ALG], audience="britsmaid-media")
            if payload.get("purpose") != "file" or payload.get("media_id") != media_id or not payload.get("session_key"):
                raise jwt.InvalidTokenError()
        except jwt.InvalidTokenError:
            raise HTTPException(401, "Photo link expired. Reopen the photo.") from None
        if await db.revoked_sessions.find_one({"_id": payload["session_key"]}):
            raise HTTPException(401, "Session ended. Please sign in again.")
        user = await active_token_user(payload)
    await authorize_media(media_id, user)
    return await stream_media(media_id)

# ---------------------------------------------------------------- Properties
OTAS = ["Airbnb", "Booking.com", "Agoda", "MakeMyTrip", "Expedia", "Vrbo", "Direct", "Other"]


class IcalFeed(BaseModel):
    ota: str
    url: str = Field(max_length=8192)

    @field_validator("url")
    @classmethod
    def public_https_link(cls, value):
        validate_url(value)
        return value

    last_synced: Optional[str] = None


class ContactIn(BaseModel):
    name: str
    role: str = "Emergency contact"  # Owner, Co-owner, Family, Caretaker, Emergency contact, Property manager, Local contact, Other
    phone: str = ""
    alt_phone: str = ""
    email: str = ""
    notes: str = ""
    emergency: bool = False


class PropertyIn(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    location: str = ""
    owner_name: str = ""
    owner_email: str = ""
    owner_phone: str = ""
    owner_alt_phone: str = ""
    owner_address: str = ""
    contacts: List[ContactIn] = []
    owner_share_percent: float = Field(70, ge=0, le=100)
    electricity_mode: Literal["split_half", "owner"] = "owner"
    base_rate: float = Field(default=0, ge=0, allow_inf_nan=False)
    rooms: List[str] = ["Living Room", "Kitchen", "Bedroom 1", "Bathroom 1"]
    ical_feeds: List[IcalFeed] = Field(default_factory=list, max_length=32)
    cover_url: str = ""
    cover_media_id: str = ""
    notes: str = ""

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value):
        if not value.strip():
            raise ValueError("Enter a property name")
        return value.strip()

    @field_validator("rooms")
    @classmethod
    def valid_rooms(cls, values):
        rooms = [v.strip() for v in values]
        if len(rooms) > 100 or any(not r or len(r) > 180 for r in rooms) or len({r.casefold() for r in rooms}) != len(rooms):
            raise ValueError("Use distinct nonempty room names (maximum 100)")
        return rooms


@api.get("/properties")
async def list_properties(user=Depends(current_user)):
    q: dict[str, Any] = {"is_deleted": {"$ne": True}}
    if owner_pids(user) is not None:
        q["_id"] = {"$in": [ObjectId(x) for x in owner_pids(user)]}
    props = await db.properties.find(q).sort("name", 1).to_list(500)
    today = date.today().isoformat()
    result = []
    for p in props:
        o = out(p)
        o.update(await property_status(o["id"], today))
        o = property_view(o, user)
        result.append(o)
    return result


def property_view(p, user):
    if user["role"] in ("cleaner", "supervisor"):
        return {k: v for k, v in p.items() if k in ("id", "name", "location", "rooms", "occupied", "needs_cleaning", "pending_cleaning_id")}
    return p


async def property_status(pid: str, day: str):
    occ = await db.bookings.find_one({"property_id": pid, "status": {"$ne": "cancelled"}, "check_in": {"$lte": day}, "check_out": {"$gt": day}})
    pending = await db.cleaning.find_one({"property_id": pid, "status": {"$nin": ["completed", "cancelled"]}, "date": {"$lte": day}})
    return {"occupied": bool(occ), "current_guest": occ.get("guest_name") if occ else None,
            "needs_cleaning": bool(pending), "pending_cleaning_id": str(pending["_id"]) if pending else None}


async def validate_property_cover(media_id, user, previous_id=""):
    if not media_id:
        return
    media = await db.media.find_one({"_id": oid(media_id), "is_deleted": False})
    if not media or media.get("kind") != "image":
        raise HTTPException(422, "Choose an uploaded photo for the villa cover")
    if media_id == previous_id:
        return
    if media.get("owner_id") != str(user["_id"]) or media.get("attachment_binding"):
        raise HTTPException(422, "Upload a new villa cover photo from your account")
    if await db.cleaning.find_one({"$or": [{"rooms.before": media_id}, {"rooms.after": media_id}]}) or await db.owner_reports.find_one({"media_ids": media_id}):
        raise HTTPException(422, "Upload a separate cover photo instead of a cleaning or report attachment")


@api.post("/properties")
async def create_property(body: PropertyIn, _=Depends(admin_user)):
    await validate_property_cover(body.cover_media_id, _)
    doc = body.model_dump()
    doc.update({"created_at": now_iso(), "is_deleted": False})
    r = await db.properties.insert_one(doc)
    return out(await db.properties.find_one({"_id": r.inserted_id}))


@api.get("/properties/{pid}")
async def get_property(pid: str, user=Depends(current_user)):
    check_pid(user, pid)
    p = await db.properties.find_one({"_id": oid(pid)})
    if not p:
        raise HTTPException(404, "Property not found")
    o = out(p)
    o.update(await property_status(pid, date.today().isoformat()))
    return property_view(o, user)


@api.put("/properties/{pid}")
async def update_property(pid: str, body: PropertyIn, _=Depends(admin_user)):
    previous = await db.properties.find_one({"_id": oid(pid), "is_deleted": {"$ne": True}})
    if not previous:
        raise HTTPException(404, "Property not found")
    await validate_property_cover(body.cover_media_id, _, previous.get("cover_media_id", ""))
    await db.properties.update_one({"_id": oid(pid)}, {"$set": body.model_dump()})
    return await get_property(pid, _)


@api.delete("/properties/{pid}")
async def delete_property(pid: str, _=Depends(admin_user)):
    await db.properties.update_one({"_id": oid(pid)}, {"$set": {"is_deleted": True}})
    await db.users.update_many({"property_ids": pid}, {"$pull": {"property_ids": pid}})
    return {"ok": True}

# ---------------------------------------------------------------- Bookings
class BookingIn(BaseModel):
    property_id: str
    guest_name: str
    guest_phone: str = ""
    guest_email: str = ""
    guests: int = Field(default=1, ge=1, le=100)
    ota: str = "Direct"
    check_in: str
    check_out: str
    amount: float = Field(default=0, ge=0, allow_inf_nan=False)
    ota_commission: float = Field(default=0, ge=0, allow_inf_nan=False)
    status: Literal["confirmed", "cancelled", "blocked"] = "confirmed"
    notes: str = ""


async def ensure_cleaning(pid: str, booking_id: str, day: str):
    if await db.cleaning.find_one({"booking_id": booking_id}):
        return
    p = await db.properties.find_one({"_id": ObjectId(pid)})
    rooms = (p or {}).get("rooms") or ["Living Room"]
    await db.cleaning.insert_one({"property_id": pid, "booking_id": booking_id, "date": day, "status": "pending", "assigned_to": None,
                                  "rooms": [{"name": r, "before": [], "after": []} for r in rooms], "notes": "", "created_at": now_iso()})


def validate_dates(ci: str, co: str):
    try:
        if date.fromisoformat(co) <= date.fromisoformat(ci):
            raise HTTPException(400, "Check-out must be after check-in")
    except ValueError:
        raise HTTPException(400, "Dates must be YYYY-MM-DD")


async def check_overlap(b: BookingIn, exclude: Optional[str] = None):
    q = {"property_id": b.property_id, "status": {"$ne": "cancelled"}, "check_in": {"$lt": b.check_out}, "check_out": {"$gt": b.check_in}}
    if exclude:
        q["_id"] = {"$ne": ObjectId(exclude)}
    clash = await db.bookings.find_one(q)
    if clash:
        raise HTTPException(409, f"Dates overlap with {clash.get('guest_name')} ({clash['check_in']} → {clash['check_out']})")


@api.get("/bookings")
async def list_bookings(property_id: Optional[str] = None, start: Optional[str] = None, end: Optional[str] = None, user=Depends(finance_user)):
    q: dict[str, Any] = {}
    if property_id:
        q["property_id"] = property_id
    scope(user, q)
    if start and end:
        q["check_in"] = {"$lt": end}
        q["check_out"] = {"$gt": start}
    projection = {"admin_history": 0} if user["role"] != "admin" else None
    return [out(b) for b in await db.bookings.find(q, projection).sort("check_in", 1).to_list(2000)]


@api.post("/bookings")
async def create_booking(body: BookingIn, _=Depends(admin_user)):
    await validate_pids([body.property_id])
    validate_dates(body.check_in, body.check_out)
    if body.status != "cancelled":
        await check_overlap(body)
    doc = body.model_dump()
    doc.update({"source": "manual", "created_at": now_iso()})
    doc["_id"] = ObjectId()
    if body.status != "cancelled":
        await claim_nights(db, str(doc["_id"]), body.property_id, body.check_in, body.check_out)
    try:
        r = await db.bookings.insert_one(doc)
    except Exception:
        await release_unused(db, str(doc["_id"]))
        raise
    if body.status == "confirmed":
        await ensure_cleaning(body.property_id, str(r.inserted_id), body.check_out)
    return out(await db.bookings.find_one({"_id": r.inserted_id}))


@api.get("/bookings/{bid}")
async def get_booking(bid: str, user=Depends(finance_user)):
    b = await db.bookings.find_one({"_id": oid(bid)})
    if not b:
        raise HTTPException(404, "Booking not found")
    check_pid(user, b["property_id"])
    if user["role"] != "admin":
        b.pop("admin_history", None)
    return out(b)


@api.put("/bookings/{bid}")
async def update_booking(bid: str, body: BookingIn, _=Depends(admin_user)):
    await validate_pids([body.property_id])
    previous = await db.bookings.find_one({"_id": oid(bid)})
    if not previous:
        raise HTTPException(404, "Booking not found")
    validate_dates(body.check_in, body.check_out)
    active_task = await db.cleaning.find_one({"booking_id": bid, "status": {"$in": ["in_progress", "awaiting_review", "completed"]}})
    if active_task and body.status == "confirmed" and (previous["property_id"] != body.property_id or previous["check_out"] != body.check_out):
        raise HTTPException(409, "Cleaning work already exists. Reopen it with an admin reason before changing the property or checkout date.")
    if body.status != "cancelled":
        await check_overlap(body, bid)
    claimed = []
    if body.status != "cancelled":
        claimed = await claim_nights(db, bid, body.property_id, body.check_in, body.check_out)
    result = await db.bookings.update_one({"_id": oid(bid), "revision": previous.get("revision")}, {"$set": body.model_dump(), "$inc": {"revision": 1}})
    if not result.matched_count:
        await db.reserved_nights.delete_many({"_id": {"$in": claimed}, "booking_id": bid})
        raise HTTPException(409, "Booking changed. Refresh before saving again.")
    await release_unused(db, bid, body.property_id if body.status != "cancelled" else None, body.check_in, body.check_out)
    if body.status == "confirmed":
        await ensure_cleaning(body.property_id, bid, body.check_out)
        prop = await db.properties.find_one({"_id": oid(body.property_id)})
        task = await db.cleaning.find_one({"booking_id": bid})
        changes = {"date": body.check_out, "property_id": body.property_id}
        if task and task.get("property_id") != body.property_id:
            changes.update(assigned_to=None, rooms=[{"name": r, "before": [], "after": [], "checked": []} for r in prop.get("rooms", [])])
        if task and task["status"] == "cancelled":
            changes["status"] = "pending"
        await db.cleaning.update_one({"booking_id": bid, "status": {"$in": ["pending", "cancelled"]}}, {"$set": changes})
    else:
        await db.cleaning.update_many({"booking_id": bid, "status": {"$ne": "completed"}}, {"$set": {"status": "cancelled", "review_notes": "Booking cancelled or blocked"}})
    return await get_booking(bid, _)


@api.delete("/bookings/{bid}")
async def delete_booking(bid: str, _=Depends(admin_user)):
    await release_unused(db, bid)
    await db.bookings.delete_one({"_id": oid(bid)})
    await db.cleaning.update_many({"booking_id": bid, "status": {"$ne": "completed"}}, {"$set": {"status": "cancelled", "review_notes": "Booking removed"}, "$inc": {"revision": 1}})
    return {"ok": True}


def _to_date_str(v) -> str:
    if isinstance(v, datetime):
        return (v.astimezone(ZoneInfo("Asia/Kolkata")) if v.tzinfo else v).date().isoformat()
    return v.isoformat()


def parse_ical(text: str):
    from icalendar import Calendar
    cal = Calendar.from_ical(text)
    events = []
    for ev in cal.walk("VEVENT"):
        try:
            ci = _to_date_str(ev.get("DTSTART").dt)
            co = _to_date_str(ev.get("DTEND").dt) if ev.get("DTEND") else (date.fromisoformat(ci) + timedelta(days=1)).isoformat()
            events.append({"uid": str(ev.get("UID") or f"{ci}-{co}"), "summary": str(ev.get("SUMMARY") or "OTA Guest"), "check_in": ci, "check_out": co,
                           "description": str(ev.get("DESCRIPTION") or "")[:500], "cancelled": str(ev.get("STATUS") or "").upper() == "CANCELLED"})
        except Exception as e:
            logger.warning(f"Skip ical event: {e}")
    return events


async def sync_property(p: dict) -> list:
    pid = str(p["_id"])
    feeds = p.get("ical_feeds") or []
    report = []
    for f in feeds:
        try:
            text = await run_in_threadpool(fetch_calendar, f["url"])
            events = parse_ical(text)
        except Exception as e:
            report.append({"ota": f["ota"], "ok": False, "error": str(e) if isinstance(e, CalendarFetchError) else "Calendar feed could not be read. Check its export link and try again."})
            continue
        from service_lease import business_lease
        async with business_lease(db, seconds=300):
            added = updated = 0
            conflicts = 0
            feed_id = hashlib.sha256(f["url"].encode()).hexdigest()[:16]
            worker = {"_id": "calendar-sync", "role": "admin"}
            for ev in events:
                if ev["uid"].endswith("@calendar.britsmaid"):
                    continue  # Do not import our own availability blocks back through an OTA.
                uid = f"{feed_id}:{ev['uid']}"
                existing = await db.bookings.find_one({"property_id": pid, "ical_uid": uid})
                if not existing:
                    existing = await db.bookings.find_one({"property_id": pid, "ical_uid": ev["uid"], "ota": f["ota"], "ical_feed_id": {"$exists": False}})
                if ev["cancelled"] and not existing:
                    continue
                blocked = any(w in ev["summary"].lower() for w in ["not available", "blocked", "closed"])
                payload = {**(existing or {}), "property_id": pid, "guest_name": ev["summary"], "ota": f["ota"],
                           "check_in": ev["check_in"], "check_out": ev["check_out"],
                           "status": "cancelled" if ev["cancelled"] else "blocked" if blocked else "confirmed"}
                try:
                    body = BookingIn(**payload)
                    if existing:
                        result = await update_booking(str(existing["_id"]), body, worker)
                        updated += 1
                    else:
                        result = await create_booking(body, worker)
                        added += 1
                    await db.bookings.update_one({"_id": oid(result["id"])}, {"$set": {"source": "ical", "ical_uid": uid, "ical_feed_id": feed_id}})
                except Exception:
                    # Preserve existing work and expose a sync failure rather than silently overwrite conflicts.
                    conflicts += 1
            f["last_synced"] = now_iso()
            report.append({"ota": f["ota"], "ok": not conflicts, "added": added, "updated": updated, "events": len(events), "conflicts": conflicts, **({"error": "Some events conflict with existing work or contain invalid dates. Review the calendar before retrying."} if conflicts else {})})
    await db.properties.update_one({"_id": p["_id"]}, {"$set": {"ical_feeds": feeds}})
    await issue_tracker.record("Calendar sync " + pid, any(not item["ok"] for item in report))
    return report


@api.post("/properties/{pid}/ical-sync")
async def ical_sync(pid: str, _=Depends(admin_user)):
    p = await db.properties.find_one({"_id": oid(pid)})
    if not p:
        raise HTTPException(404, "Property not found")
    if not p.get("ical_feeds"):
        raise HTTPException(400, "No iCal links added for this property")
    return {"results": await sync_property(p)}


SYNC_INTERVAL_SECONDS = 600


async def sync_all(*args, **kwargs):
    return await _sync_all_unlocked(*args, **kwargs)


async def _sync_all_unlocked(trigger: str):
    props = await db.properties.find({"is_deleted": {"$ne": True}, "ical_feeds.0": {"$exists": True}}).to_list(500)
    added = errors = 0
    for p in props:
        try:
            for r in await sync_property(p):
                added += r.get("added", 0)
                errors += 0 if r["ok"] else 1
        except Exception as e:
            errors += 1
            logger.error(f"Auto sync failed for {p.get('name')}: {e}")
    status = {"last_run": now_iso(), "trigger": trigger, "properties": len(props), "added": added, "errors": errors}
    await db.settings.update_one({"_id": "ical_sync"}, {"$set": status}, upsert=True)
    return status


async def auto_sync_loop():
    while True:
        try:
            last = await db.settings.find_one({"_id": "ical_sync"})
            due = True
            if last and last.get("last_run"):
                due = (datetime.now(timezone.utc) - datetime.fromisoformat(last["last_run"])).total_seconds() >= SYNC_INTERVAL_SECONDS
            if due:
                st = await sync_all("auto")
                logger.info(f"10-minute OTA import: {st}")
        except Exception as e:
            logger.error(f"Auto sync loop error: {e}")
        await asyncio.sleep(30)


@api.get("/sync/status")
async def sync_status(_=Depends(admin_user)):
    st = await db.settings.find_one({"_id": "ical_sync"}) or {}
    st.pop("_id", None)
    st["interval_minutes"] = SYNC_INTERVAL_SECONDS // 60
    if st.get("last_run"):
        st["next_run"] = (datetime.fromisoformat(st["last_run"]) + timedelta(seconds=SYNC_INTERVAL_SECONDS)).isoformat()
    return st


@api.post("/sync/run")
async def sync_run(_=Depends(admin_user)):
    return await sync_all("manual")

# ---------------------------------------------------------------- Calendar
@api.get("/calendar")
async def calendar(month: str, property_id: Optional[str] = None, user=Depends(finance_user)):
    month_bounds(month)
    y, m = map(int, month.split("-"))
    start = date(y, m, 1)
    end = date(y + (m // 12), (m % 12) + 1, 1)
    q: dict[str, Any] = {"status": {"$ne": "cancelled"}, "check_in": {"$lt": end.isoformat()}, "check_out": {"$gt": start.isoformat()}}
    cq: dict[str, Any] = {"date": {"$gte": start.isoformat(), "$lt": end.isoformat()}}
    if property_id:
        q["property_id"] = property_id
        cq["property_id"] = property_id
    scope(user, q)
    scope(user, cq)
    bookings = [out(b) for b in await db.bookings.find(q, {"admin_history": 0} if user["role"] != "admin" else None).to_list(3000)]
    cleanings = [out(c) for c in await db.cleaning.find(cq, {"rooms": 0, **({"admin_history": 0} if user["role"] != "admin" else {})}).to_list(3000)]
    return {"bookings": bookings, "cleanings": cleanings}

# ---------------------------------------------------------------- Cleaning
class CleaningIn(BaseModel):
    property_id: str
    date: str
    assigned_to: Optional[str] = None
    notes: str = ""


class RoomMediaIn(BaseModel):
    phase: Literal["before", "after"]
    media_id: str
    expected_revision: Optional[int] = None
    room_name: Optional[str] = None


class CleaningUpdate(BaseModel):
    assigned_to: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[Literal["pending", "in_progress", "awaiting_review", "completed"]] = None


CHECKLIST = ["Surfaces cleaned", "Linen replaced", "Bathroom sanitised", "Supplies restocked", "Damage checked"]


async def checked_cleaning(cid, user, writable=False):
    c = await db.cleaning.find_one({"_id": oid(cid)})
    if not c:
        raise HTTPException(404, "Session not found")
    check_pid(user, c["property_id"])
    if user["role"] == "cleaner" and c.get("assigned_to") != str(user["_id"]):
        raise HTTPException(404, "Session not found")
    if writable and c["status"] in ("completed", "awaiting_review", "cancelled"):
        raise HTTPException(409, "Session is locked for review or completed")
    return c


async def validate_assignee(uid, pid):
    u = await db.users.find_one({"_id": oid(uid), "active": True, "role": "cleaner", "property_ids": pid})
    if not u:
        raise HTTPException(422, "Assign an active cleaner with access to this property")


class ChecklistIn(BaseModel):
    checked: List[str]


@api.put("/cleaning/{cid}/rooms/{idx}/checklist")
async def set_checklist(cid: str, idx: int, body: ChecklistIn, user=Depends(staff_user)):
    c = await checked_cleaning(cid, user, writable=True)
    if idx < 0 or idx >= len(c.get("rooms", [])) or not set(body.checked).issubset(CHECKLIST):
        raise HTTPException(422, "Invalid room or checklist item")
    result = await db.cleaning.update_one({"_id": c["_id"], "status": c["status"], "revision": c.get("revision")}, {"$set": {f"rooms.{idx}.checked": list(set(body.checked))}, "$inc": {"revision": 1}})
    if not result.matched_count:
        raise HTTPException(409, "Session changed; refresh and retry")
    return await get_cleaning(cid, user)


class ReviewIn(BaseModel):
    approved: bool
    notes: str = Field(default="", max_length=2000)


class CleaningAdminAction(BaseModel):
    action: Literal["reopen", "complete", "reassign"]
    note: str = Field(min_length=1, max_length=2000)
    assigned_to: Optional[str] = None


@api.post("/cleaning/{cid}/admin-action")
async def cleaning_admin_action(cid: str, body: CleaningAdminAction, user=Depends(admin_user)):
    if not body.note.strip():
        raise HTTPException(422, "Add a reason for this admin action")
    c = await checked_cleaning(cid, user)
    last = (c.get("admin_history") or [{}])[-1]
    if (last.get("action") == body.action and last.get("note") == body.note.strip()
            and last.get("result_revision") == c.get("revision")
            and last.get("assigned_to") == (body.assigned_to or c.get("assigned_to"))):
        return await get_cleaning(cid, user)
    if body.assigned_to:
        await validate_assignee(body.assigned_to, c["property_id"])
    if body.action == "reassign" and not body.assigned_to:
        raise HTTPException(422, "Choose a cleaner")
    changes = {"status": "completed" if body.action == "complete" else "pending",
               "review_notes": body.note.strip()}
    if body.assigned_to:
        changes["assigned_to"] = body.assigned_to
    event = {"action": body.action, "note": body.note.strip(), "actor_id": str(user["_id"]),
             "actor_name": user.get("name", "Admin"), "at": now_iso(), "result_revision": c.get("revision", 0) + 1,
             "assigned_to": body.assigned_to or c.get("assigned_to"),
             "before": {k: c.get(k) for k in ("status", "assigned_to", "completed_at", "reviewed_at", "reviewed_by", "review_notes", "submitted_at", "submitted_by", "rooms")}}
    update = {"$set": changes, "$inc": {"revision": 1}, "$push": {"admin_history": event}}
    if body.action == "complete":
        changes.update(completed_at=now_iso(), reviewed_at=now_iso(), reviewed_by=str(user["_id"]))
    else:
        # Preserve old evidence in history; rework must collect fresh evidence.
        changes["rooms"] = [{"name": r["name"], "before": [], "after": [], "checked": []} for r in c.get("rooms", [])]
        update["$unset"] = {k: "" for k in ("completed_at", "reviewed_at", "reviewed_by", "submitted_at", "submitted_by", "photos_ready_at")}
    result = await db.cleaning.update_one({"_id": c["_id"], "status": c["status"], "revision": c.get("revision")}, update)
    if not result.matched_count:
        raise HTTPException(409, "Session changed; refresh and retry")
    return await get_cleaning(cid, user)


@api.get("/cleaning-team")
async def cleaning_team(user=Depends(staff_user)):
    if user["role"] not in ("admin", "supervisor"):
        raise HTTPException(403, "Supervisors only")
    q = {"active": True, "role": "cleaner"}
    if user["role"] == "supervisor":
        q["property_ids"] = {"$in": owner_pids(user)}
    users = await db.users.find(q, {"name": 1, "property_ids": 1}).to_list(500)
    return [out(u) for u in users]


@api.post("/cleaning/{cid}/review")
async def review_cleaning(cid: str, body: ReviewIn, user=Depends(staff_user)):
    if user["role"] not in ("admin", "supervisor"):
        raise HTTPException(403, "Supervisor review required")
    c = await checked_cleaning(cid, user)
    if c["status"] != "awaiting_review":
        raise HTTPException(409, "Session is not awaiting review")
    if not body.approved and not body.notes.strip():
        raise HTTPException(422, "Explain what needs to be corrected")
    changes = {"status": "completed" if body.approved else "in_progress", "review_notes": body.notes,
               "reviewed_by": str(user["_id"]), "reviewed_at": now_iso()}
    if body.approved:
        changes["completed_at"] = now_iso()
    result = await db.cleaning.update_one({"_id": c["_id"], "status": "awaiting_review"}, {"$set": changes})
    if not result.matched_count:
        raise HTTPException(409, "Session changed; refresh and retry")
    return await get_cleaning(cid, user)


async def enrich_cleaning(c: dict):
    o = out(c)
    ids = [oid(mid) for mid in cleaning_retention.evidence_ids(c) if ObjectId.is_valid(mid)]
    expired = await db.media.find({"_id": {"$in": ids}, "is_deleted": True, "expiry_reason": "older_cleaning_set"}, {"_id": 1}).to_list(None)
    o["expired_media_ids"] = sorted(set(o.get("expired_media_ids", [])) | {str(row["_id"]) for row in expired})
    p = await db.properties.find_one({"_id": ObjectId(o["property_id"])}, {"name": 1, "location": 1})
    o["property_name"] = p["name"] if p else "Unknown"
    if o.get("assigned_to") and ObjectId.is_valid(o["assigned_to"]):
        u = await db.users.find_one({"_id": ObjectId(o["assigned_to"])}, {"name": 1})
        o["assigned_name"] = u["name"] if u else None
    rooms = o.get("rooms") or []
    o["rooms_total"] = len(rooms)
    o["rooms_done"] = sum(1 for r in rooms if r.get("before") and r.get("after"))
    o["checklist_items"] = CHECKLIST
    return o


@api.get("/cleaning")
async def list_cleaning(status: Optional[str] = None, property_id: Optional[str] = None, user=Depends(current_user)):
    q: dict[str, Any] = {}
    if status == "open":
        q["status"] = {"$nin": ["completed", "cancelled"]}
    elif status == "unassigned":
        q.update(status={"$nin": ["completed", "cancelled"]}, assigned_to=None)
    elif status:
        q["status"] = status
    if property_id:
        q["property_id"] = property_id
    scope(user, q)
    if user["role"] == "cleaner":
        q["assigned_to"] = str(user["_id"])
    items = await db.cleaning.find(q).sort("date", 1 if status == "open" else -1).to_list(500)
    return [await enrich_cleaning(c) for c in items]


@api.post("/cleaning")
async def create_cleaning(body: CleaningIn, _=Depends(admin_user)):
    try:
        date.fromisoformat(body.date)
    except ValueError:
        raise HTTPException(422, "Invalid cleaning date")
    if body.assigned_to:
        await validate_assignee(body.assigned_to, body.property_id)
    p = await db.properties.find_one({"_id": oid(body.property_id)})
    if not p:
        raise HTTPException(404, "Property not found")
    doc = body.model_dump()
    doc.update({"booking_id": None, "status": "pending", "rooms": [{"name": r, "before": [], "after": []} for r in p.get("rooms") or []], "created_at": now_iso()})
    r = await db.cleaning.insert_one(doc)
    return await enrich_cleaning(await db.cleaning.find_one({"_id": r.inserted_id}))


@api.get("/cleaning/{cid}")
async def get_cleaning(cid: str, user=Depends(current_user)):
    c = await checked_cleaning(cid, user)
    return await enrich_cleaning(c)


@api.post("/cleaning/{cid}/rooms/{idx}/media")
async def add_room_media(cid: str, idx: int, body: RoomMediaIn, user=Depends(staff_user)):
    c = await checked_cleaning(cid, user, writable=True)
    if not c or idx < 0 or idx >= len(c.get("rooms", [])):
        raise HTTPException(404, "Room not found")
    if c["status"] == "completed":
        raise HTTPException(400, "Session already completed")
    media = await db.media.find_one({"_id": oid(body.media_id), "is_deleted": False})
    if not media or media.get("kind") != "image" or (user["role"] != "admin" and media.get("owner_id") != str(user["_id"])):
        raise HTTPException(422, "Use a photo uploaded by your account")
    # A retry after a lost acknowledgement is successful, without changing revision.
    if body.media_id in c["rooms"][idx].get(body.phase, []):
        return await get_cleaning(cid, user)
    if body.room_name is not None and body.room_name != c["rooms"][idx]["name"]:
        raise HTTPException(409, "Room changed; reopen the correct room before saving")
    if body.expected_revision is not None and body.expected_revision != c.get("revision", 0):
        raise HTTPException(409, "Task changed; refresh and check the assignment before saving")
    for session in await db.cleaning.find({"rooms": {"$elemMatch": {"$or": [{"before": body.media_id}, {"after": body.media_id}]}}}).to_list(None):
        raise HTTPException(409, "This photo is already attached to another room or phase")
    binding = f"{cid}:{idx}:{body.phase}"
    claimed = await db.media.update_one({"_id": media["_id"], "$or": [{"attachment_binding": {"$exists": False}}, {"attachment_binding": binding}]}, {"$set": {"attachment_binding": binding}})
    if not claimed.matched_count:
        raise HTTPException(409, "This photo belongs to another room or phase; take a new photo")
    photos = list(dict.fromkeys([*c["rooms"][idx].get(body.phase, []), body.media_id]))
    upd = {"$set": {f"rooms.{idx}.{body.phase}": photos, "status": "in_progress"}, "$inc": {"revision": 1}}
    result = await db.cleaning.update_one({"_id": c["_id"], "status": c["status"], "revision": c.get("revision")}, upd)
    if not result.matched_count:
        raise HTTPException(409, "Session changed; refresh and retry")
    await cleaning_retention.mark_ready(c["_id"])
    return await get_cleaning(cid, user)


@api.delete("/cleaning/{cid}/rooms/{idx}/media/{phase}/{media_id}")
async def remove_room_media(cid: str, idx: int, phase: Literal["before", "after"], media_id: str, user=Depends(staff_user)):
    c = await checked_cleaning(cid, user, writable=True)
    if idx < 0 or idx >= len(c.get("rooms", [])):
        raise HTTPException(404, "Room not found")
    photos = [mid for mid in c["rooms"][idx].get(phase, []) if mid != media_id]
    result = await db.cleaning.update_one({"_id": c["_id"], "status": c["status"], "revision": c.get("revision")}, {"$set": {f"rooms.{idx}.{phase}": photos}, "$inc": {"revision": 1}})
    if not result.matched_count:
        raise HTTPException(409, "Session changed; refresh and retry")
    return await get_cleaning(cid, user)


@api.put("/cleaning/{cid}")
async def update_cleaning(cid: str, body: CleaningUpdate, user=Depends(staff_user)):
    c = await checked_cleaning(cid, user, writable=True)
    changes = body.model_dump(exclude_unset=True)
    if "assigned_to" in changes and user["role"] not in ("admin", "supervisor"):
        raise HTTPException(403, "Only admins or supervisors can assign")
    if changes.get("assigned_to"):
        await validate_assignee(changes["assigned_to"], c["property_id"])
    if changes.get("status") in ("completed", "awaiting_review"):
        if not c.get("rooms"):
            raise HTTPException(400, "Configure rooms before submitting cleaning")
        missing = [r["name"] for r in c.get("rooms", []) if not r.get("before") or not r.get("after")]
        if missing:
            raise HTTPException(400, "Before & after photos missing for: " + ", ".join(missing))
        if any(set(r.get("checked", [])) != set(CHECKLIST) for r in c["rooms"]):
            raise HTTPException(400, "Complete every room checklist")
        changes["status"] = "awaiting_review"
        changes["submitted_at"] = now_iso()
        changes["submitted_by"] = str(user["_id"])
    if changes:
        result = await db.cleaning.update_one({"_id": c["_id"], "status": c["status"], "assigned_to": c.get("assigned_to"), "revision": c.get("revision")}, {"$set": changes, "$inc": {"revision": 1}})
        if not result.matched_count:
            raise HTTPException(409, "Session changed; refresh and retry")
    return await get_cleaning(cid, user)

# ---------------------------------------------------------------- Expenses (electricity)
class ExpenseIn(BaseModel):
    property_id: str
    month: str  # YYYY-MM
    type: Literal["electricity", "other"] = "electricity"
    amount: float = Field(ge=0, allow_inf_nan=False)
    notes: str = ""
    _month = field_validator("month")(valid_month)


@api.get("/expenses")
async def list_expenses(property_id: str, user=Depends(finance_user)):
    check_pid(user, property_id)
    return [out(e) for e in await db.expenses.find({"property_id": property_id}).sort("month", -1).to_list(500)]


@api.post("/expenses")
async def create_expense(body: ExpenseIn, _=Depends(admin_user)):
    await validate_pids([body.property_id])
    doc = body.model_dump()
    doc["created_at"] = now_iso()
    r = await db.expenses.insert_one(doc)
    return out(await db.expenses.find_one({"_id": r.inserted_id}))


@api.delete("/expenses/{eid}")
async def delete_expense(eid: str, _=Depends(admin_user)):
    await db.expenses.delete_one({"_id": oid(eid)})
    return {"ok": True}

# ---------------------------------------------------------------- Settlement & reports
def month_range(month: str):
    return month_bounds(month)


def shift_month(month: str, delta: int) -> str:
    y, m = map(int, month.split("-"))
    idx = y * 12 + (m - 1) + delta
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


async def compute_settlement(p: dict, month: str):
    start, end = month_range(month)
    bookings = await db.bookings.find({"property_id": str(p["_id"]), "status": "confirmed", "check_in": {"$gte": start, "$lt": end}}).sort("check_in", 1).to_list(1000)
    gross = sum(b.get("amount", 0) for b in bookings)
    commission = sum(b.get("ota_commission", 0) for b in bookings)
    net = gross - commission
    pct = p.get("owner_share_percent", 70)
    owner_share = round(net * pct / 100, 2)
    bm_share = round(net - owner_share, 2)
    exps = await db.expenses.find({"property_id": str(p["_id"]), "month": month}).to_list(100)
    elec = sum(e["amount"] for e in exps if e["type"] == "electricity")
    other = sum(e["amount"] for e in exps if e["type"] == "other")
    mode = p.get("electricity_mode", "owner")
    if mode == "split_half":
        owner_elec, bm_elec = round(elec / 2, 2), round(elec / 2, 2)
    else:
        owner_elec, bm_elec = 0, 0  # paid directly by owner
    owner_payout = round(owner_share - owner_elec - other, 2)
    bm_net = round(bm_share - bm_elec, 2)
    nights = 0
    occupied = await db.bookings.find({"property_id": str(p["_id"]), "status": "confirmed", "check_in": {"$lt": end}, "check_out": {"$gt": start}}).to_list(5000)
    nights = sum((min(date.fromisoformat(b["check_out"]), date.fromisoformat(end)) - max(date.fromisoformat(b["check_in"]), date.fromisoformat(start))).days for b in occupied)
    by_ota: dict[str, dict] = {}
    for b in bookings:
        n = (date.fromisoformat(b["check_out"]) - date.fromisoformat(b["check_in"])).days
        o = by_ota.setdefault(b["ota"], {"ota": b["ota"], "bookings": 0, "nights": 0, "gross": 0, "commission": 0})
        o["bookings"] += 1
        o["nights"] += n
        o["gross"] += b.get("amount", 0)
        o["commission"] += b.get("ota_commission", 0)
    for o in by_ota.values():
        o["net"] = o["gross"] - o["commission"]
    y, m = map(int, month.split("-"))
    days_in_month = (date.fromisoformat(end) - date.fromisoformat(start)).days
    return {
        "property_id": str(p["_id"]), "property_name": p["name"], "owner_name": p.get("owner_name", ""), "month": month,
        "owner_share_percent": pct, "britsmaid_share_percent": 100 - pct, "electricity_mode": mode,
        "gross": gross, "ota_commission": commission, "net_revenue": net, "owner_share": owner_share, "britsmaid_share": bm_share,
        "electricity_total": elec, "owner_electricity": owner_elec, "britsmaid_electricity": bm_elec, "other_deductions": other,
        "owner_payout": owner_payout, "britsmaid_net": bm_net, "nights": nights,
        "occupancy_percent": round(min(nights, days_in_month) / days_in_month * 100, 1),
        "by_ota": sorted(by_ota.values(), key=lambda x: -x["gross"]),
        "bookings": [{"id": str(b["_id"]), "guest_name": b["guest_name"], "ota": b["ota"], "check_in": b["check_in"], "check_out": b["check_out"],
                      "amount": b.get("amount", 0), "ota_commission": b.get("ota_commission", 0)} for b in bookings],
    }


@api.get("/reports/settlement")
async def settlement(property_id: str, month: str, months: int = 1, user=Depends(finance_user)):
    check_pid(user, property_id)
    p = await db.properties.find_one({"_id": oid(property_id)})
    if not p:
        raise HTTPException(404, "Property not found")
    main = await compute_settlement(p, month)
    trend = []
    for i in range(5, -1, -1):
        mm = shift_month(month, -i)
        s = main if mm == month else await compute_settlement(p, mm)
        trend.append({"month": mm, "gross": s["gross"], "owner_payout": s["owner_payout"], "britsmaid_net": s["britsmaid_net"], "nights": s["nights"]})
    main["trend"] = trend
    main["payout"] = out(await db.payouts.find_one({"property_id": property_id, "month": month}))
    return main


class PayoutIn(BaseModel):
    property_id: str
    month: str
    amount: float = Field(ge=0, allow_inf_nan=False)
    paid_on: str
    method: Literal["Bank transfer", "UPI", "Cash", "Cheque"] = "Bank transfer"
    reference: str = ""
    notes: str = ""
    _month = field_validator("month")(valid_month)
    _paid_on = field_validator("paid_on")(valid_date)


@api.post("/payouts")
async def create_payout(body: PayoutIn, user=Depends(admin_user)):
    p = await db.properties.find_one({"_id": oid(body.property_id)})
    if not p:
        raise HTTPException(404, "Property not found")
    if await db.payouts.find_one({"property_id": body.property_id, "month": body.month}):
        raise HTTPException(409, "Payout for this month is already recorded")
    snap = await compute_settlement(p, body.month)
    ctr = await db.counters.find_one_and_update({"_id": "payout"}, {"$inc": {"seq": 1}}, upsert=True, return_document=True)
    doc = body.model_dump()
    doc.update({"receipt_number": f"BM-PAY-{datetime.now().year}-{ctr['seq']:04d}", "property_name": p["name"], "owner_name": p.get("owner_name", ""),
                "calculated_payout": snap["owner_payout"], "gross": snap["gross"], "ota_commission": snap["ota_commission"], "owner_share": snap["owner_share"],
                "owner_share_percent": snap["owner_share_percent"], "owner_electricity": snap["owner_electricity"], "other_deductions": snap["other_deductions"],
                "nights": snap["nights"], "recorded_by": str(user["_id"]), "created_at": now_iso()})
    r = await db.payouts.insert_one(doc)
    return out(await db.payouts.find_one({"_id": r.inserted_id}))


@api.get("/payouts")
async def list_payouts(property_id: Optional[str] = None, user=Depends(finance_user)):
    q: dict[str, Any] = {"property_id": property_id} if property_id else {}
    scope(user, q)
    return [out(x) for x in await db.payouts.find(q).sort("month", -1).to_list(500)]


@api.delete("/payouts/{pid}")
async def delete_payout(pid: str, _=Depends(admin_user)):
    await db.payouts.delete_one({"_id": oid(pid)})
    return {"ok": True}


@api.get("/reports/ota")
async def ota_report(month: str, property_id: Optional[str] = None, _=Depends(admin_user)):
    start, end = month_range(month)
    q: dict[str, Any] = {"status": "confirmed", "check_in": {"$gte": start, "$lt": end}}
    if property_id:
        q["property_id"] = property_id
    bookings = await db.bookings.find(q).to_list(5000)
    props = {str(p["_id"]): p["name"] for p in await db.properties.find({}, {"name": 1}).to_list(500)}
    rows: dict[str, dict] = {}
    for b in bookings:
        n = (date.fromisoformat(b["check_out"]) - date.fromisoformat(b["check_in"])).days
        r = rows.setdefault(b["ota"], {"ota": b["ota"], "bookings": 0, "nights": 0, "gross": 0, "commission": 0, "properties": {}})
        r["bookings"] += 1
        r["nights"] += n
        r["gross"] += b.get("amount", 0)
        r["commission"] += b.get("ota_commission", 0)
        pn = props.get(b["property_id"], "Unknown")
        r["properties"][pn] = r["properties"].get(pn, 0) + b.get("amount", 0)
    result = []
    for r in rows.values():
        r["net"] = r["gross"] - r["commission"]
        r["adr"] = round(r["gross"] / r["nights"], 2) if r["nights"] else 0
        r["properties"] = [{"name": k, "gross": v} for k, v in sorted(r["properties"].items(), key=lambda x: -x[1])]
        result.append(r)
    result.sort(key=lambda x: -x["gross"])
    return {"month": month, "rows": result, "total_gross": sum(r["gross"] for r in result), "total_commission": sum(r["commission"] for r in result),
            "total_bookings": sum(r["bookings"] for r in result)}

# ---------------------------------------------------------------- Owner reports
class OwnerReportIn(BaseModel):
    property_id: str
    month: str
    title: str = ""
    condition_notes: str = ""
    media_ids: List[str] = []


@api.post("/owner-reports")
async def create_owner_report(body: OwnerReportIn, user=Depends(admin_user)):
    p = await db.properties.find_one({"_id": oid(body.property_id)})
    if not p:
        raise HTTPException(404, "Property not found")
    for mid in set(body.media_ids):
        if not ObjectId.is_valid(mid) or not await db.media.find_one({"_id": oid(mid), "is_deleted": False}):
            raise HTTPException(422, "Choose existing uploaded report attachments")
    snap = await compute_settlement(p, body.month)
    doc = body.model_dump()
    doc.update({"title": body.title or f"{p['name']} — {body.month}", "settlement": snap, "share_token": secrets.token_urlsafe(16),
                "created_by": str(user["_id"]), "created_at": now_iso()})
    r = await db.owner_reports.insert_one(doc)
    return out(await db.owner_reports.find_one({"_id": r.inserted_id}))


@api.get("/owner-reports")
async def list_owner_reports(property_id: Optional[str] = None, user=Depends(finance_user)):
    q: dict[str, Any] = {"property_id": property_id} if property_id else {}
    scope(user, q)
    return [out(r) for r in await db.owner_reports.find(q, {"settlement.bookings": 0}).sort("created_at", -1).to_list(500)]


@api.get("/owner-reports/{rid}")
async def get_owner_report(rid: str, user=Depends(finance_user)):
    r = await db.owner_reports.find_one({"_id": oid(rid)})
    if not r:
        raise HTTPException(404, "Report not found")
    check_pid(user, r["property_id"])
    return out(r)


@api.delete("/owner-reports/{rid}")
async def delete_owner_report(rid: str, _=Depends(admin_user)):
    await db.owner_reports.delete_one({"_id": oid(rid)})
    return {"ok": True}


@api.get("/public/reports/{token}/media/{media_id}")
async def public_media(token: str, media_id: str):
    r = await db.owner_reports.find_one({"share_token": token})
    if not r or media_id not in r.get("media_ids", []):
        raise HTTPException(404, "Not found")
    return await stream_media(media_id)


def inr(v):
    return "₹" + f"{v:,.0f}"


@api.get("/public/reports/{token}", response_class=HTMLResponse)
async def public_report(token: str):
    r = await db.owner_reports.find_one({"share_token": token})
    if not r:
        raise HTTPException(404, "Report not found")
    s = r["settlement"]
    medias = await db.media.find({"_id": {"$in": [ObjectId(m) for m in r.get("media_ids", []) if ObjectId.is_valid(m)]}}).to_list(100)
    e = html.escape
    gallery = "".join(
        f'<video controls src="{token}/media/{m["_id"]}"></video>' if m.get("kind") == "video" else f'<img onclick="zoom(this.src)" src="{token}/media/{m["_id"]}"/>'
        for m in medias)
    ota_rows = "".join(f'<details><summary><b>{e(o["ota"])}</b><span>{inr(o["gross"])}</span></summary><div class="row"><span>Bookings</span><span>{o["bookings"]}</span></div><div class="row"><span>Nights</span><span>{o["nights"]}</span></div><div class="row"><span>OTA commission</span><span>-{inr(o["commission"])}</span></div><div class="row"><span>Net</span><span>{inr(o["net"])}</span></div></details>' for o in s["by_ota"])
    bk_rows = "".join(f'<tr><td>{e(b["guest_name"])}<br><small>{e(b["ota"])} · {b["check_in"]} → {b["check_out"]}</small></td><td align="right">{inr(b["amount"])}</td></tr>' for b in s["bookings"])
    elec_line = (f'<div class="row"><span>Electricity (50% of {inr(s["electricity_total"])})</span><span>-{inr(s["owner_electricity"])}</span></div>'
                 if s["electricity_mode"] == "split_half" else '<div class="row"><span>Electricity</span><span>Managed by owner</span></div>')
    maxv = max([s["owner_share"], s["britsmaid_share"], s["ota_commission"], 1])
    bars = "".join(f'<div class="bar" onclick="this.classList.toggle(\'on\')"><label>{lbl}</label><div class="track"><div class="fill" style="width:{v / maxv * 100:.0f}%;background:{c}"></div></div><em>{inr(v)}</em></div>'
                   for lbl, v, c in [("Owner share", s["owner_share"], "#1B3A6B"), ("Britsmaid share", s["britsmaid_share"], "#375B96"), ("OTA commission", s["ota_commission"], "#9CA3AF")])
    return f"""<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(r['title'])}</title>
<style>body{{font-family:-apple-system,Segoe UI,sans-serif;margin:0;background:#F3F4F6;color:#111827}}header{{background:#1B3A6B;color:#fff;padding:24px 20px}}
h1{{margin:0;font-size:22px}}.wrap{{padding:16px;max-width:720px;margin:auto}}.card{{background:#fff;border-radius:12px;padding:16px;margin-bottom:12px;border:1px solid #E5E7EB}}
.big{{font-size:34px;font-weight:700;color:#1B3A6B}}.row{{display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #F3F4F6}}
details{{border-bottom:1px solid #E5E7EB;padding:10px 0}}summary{{display:flex;justify-content:space-between;cursor:pointer}}
.bar{{display:grid;grid-template-columns:120px 1fr 90px;align-items:center;gap:8px;margin:10px 0;cursor:pointer}}.track{{background:#E8EDF4;border-radius:6px;height:14px}}
.fill{{height:14px;border-radius:6px;transition:width .6s}}.bar em{{font-style:normal;text-align:right}}.bar.on label{{font-weight:700}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}.grid img,.grid video{{width:100%;aspect-ratio:1;object-fit:cover;border-radius:10px;cursor:zoom-in}}
#z{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.9);align-items:center;justify-content:center}}#z img{{max-width:95%;max-height:95%}}
table{{width:100%;border-collapse:collapse}}td{{padding:8px 0;border-bottom:1px solid #F3F4F6}}small{{color:#6B7280}}</style></head><body>
<header><div style="opacity:.8">BRITSMAID · Owner Statement</div><h1>{e(r['title'])}</h1><div>{e(s['owner_name'])} · {s['month']}</div></header>
<div class="wrap"><div class="card"><div>Your payout</div><div class="big">{inr(s['owner_payout'])}</div><small>{s['nights']} nights · {s['occupancy_percent']}% occupancy · {s['owner_share_percent']:.0f}/{s['britsmaid_share_percent']:.0f} split</small></div>
<div class="card"><b>Revenue split</b><small> (tap bars)</small>{bars}</div>
<div class="card"><b>How your payout is calculated</b><div class="row"><span>Gross booking revenue</span><span>{inr(s['gross'])}</span></div>
<div class="row"><span>OTA commissions</span><span>-{inr(s['ota_commission'])}</span></div><div class="row"><span>Net revenue</span><span>{inr(s['net_revenue'])}</span></div>
<div class="row"><span>Your share ({s['owner_share_percent']:.0f}%)</span><span>{inr(s['owner_share'])}</span></div>{elec_line}
{f'<div class="row"><span>Other deductions</span><span>-{inr(s["other_deductions"])}</span></div>' if s['other_deductions'] else ''}
<div class="row"><b>Payout</b><b>{inr(s['owner_payout'])}</b></div></div>
<div class="card"><b>By OTA</b>{ota_rows or '<p><small>No bookings this month</small></p>'}</div>
<div class="card"><b>Bookings</b><table>{bk_rows}</table></div>
<div class="card"><b>Property condition</b><p>{e(r.get('condition_notes') or '')}</p><div class="grid">{gallery}</div></div></div>
<div id="z" onclick="this.style.display='none'"><img id="zi"/></div><script>function zoom(s){{document.getElementById('zi').src=s;document.getElementById('z').style.display='flex'}}</script></body></html>"""

# ---------------------------------------------------------------- Invoices
class InvoiceItem(BaseModel):
    description: str
    qty: float = Field(default=1, gt=0, allow_inf_nan=False)
    rate: float = Field(default=0, ge=0, allow_inf_nan=False)


class InvoiceIn(BaseModel):
    type: Literal["guest", "client"]
    property_id: Optional[str] = None
    booking_id: Optional[str] = None
    bill_to_name: str
    bill_to_email: str = ""
    bill_to_phone: str = ""
    bill_to_address: str = ""
    items: List[InvoiceItem]
    tax_percent: float = Field(default=0, ge=0, le=100, allow_inf_nan=False)
    discount: float = Field(default=0, ge=0, allow_inf_nan=False)
    issue_date: str
    due_date: str = ""
    notes: str = ""
    status: Literal["unpaid", "paid"] = "unpaid"
    _issue = field_validator("issue_date")(valid_date)

    @field_validator("due_date")
    @classmethod
    def check_due(cls, value):
        return valid_date(value) if value else value


def invoice_totals(d: dict):
    sub = round(sum(i["qty"] * i["rate"] for i in d["items"]), 2)
    taxable = max(sub - d.get("discount", 0), 0)
    tax = round(taxable * d.get("tax_percent", 0) / 100, 2)
    d.update({"subtotal": sub, "tax_amount": tax, "total": round(taxable + tax, 2)})
    return d


async def enrich_invoice(i: dict):
    o = out(i)
    if o.get("property_id") and ObjectId.is_valid(o["property_id"]):
        p = await db.properties.find_one({"_id": ObjectId(o["property_id"])}, {"name": 1, "location": 1})
        o["property_name"] = p["name"] if p else None
        o["property_location"] = p.get("location") if p else None
    return o


@api.get("/invoices")
async def list_invoices(type: Optional[str] = None, _=Depends(admin_user)):
    q = {"type": type} if type else {}
    return [await enrich_invoice(i) for i in await db.invoices.find(q).sort("created_at", -1).to_list(1000)]


@api.post("/invoices")
async def create_invoice(body: InvoiceIn, _=Depends(admin_user)):
    if body.property_id:
        await validate_pids([body.property_id])
    if not body.bill_to_name.strip():
        raise HTTPException(422, "Enter the invoice recipient")
    if body.due_date and body.due_date < body.issue_date:
        raise HTTPException(422, "Due date cannot be before the issue date")
    if body.booking_id:
        booking = await db.bookings.find_one({"_id": oid(body.booking_id)})
        if not booking or (body.property_id and booking["property_id"] != body.property_id):
            raise HTTPException(422, "Choose a booking belonging to this property")
    if not body.items:
        raise HTTPException(400, "Add at least one line item")
    ctr = await db.counters.find_one_and_update({"_id": "invoice"}, {"$inc": {"seq": 1}}, upsert=True, return_document=True)
    doc = invoice_totals(body.model_dump())
    doc.update({"number": f"BM-{datetime.now().year}-{ctr['seq']:04d}", "created_at": now_iso()})
    r = await db.invoices.insert_one(doc)
    return await enrich_invoice(await db.invoices.find_one({"_id": r.inserted_id}))


@api.get("/invoices/{iid}")
async def get_invoice(iid: str, _=Depends(admin_user)):
    i = await db.invoices.find_one({"_id": oid(iid)})
    if not i:
        raise HTTPException(404, "Invoice not found")
    return await enrich_invoice(i)


class InvoiceStatus(BaseModel):
    status: Literal["unpaid", "paid"]


@api.put("/invoices/{iid}/status")
async def set_invoice_status(iid: str, body: InvoiceStatus, _=Depends(admin_user)):
    await db.invoices.update_one({"_id": oid(iid)}, {"$set": {"status": body.status}})
    return await get_invoice(iid)


@api.delete("/invoices/{iid}")
async def delete_invoice(iid: str, _=Depends(admin_user)):
    await db.invoices.delete_one({"_id": oid(iid)})
    return {"ok": True}

# ---------------------------------------------------------------- Dashboard
@api.get("/dashboard")
async def dashboard(_=Depends(admin_user)):
    today = date.today().isoformat()
    month = today[:7]
    start, end = month_range(month)
    props = await db.properties.find({"is_deleted": {"$ne": True}}).to_list(500)
    pmap = {str(p["_id"]): p["name"] for p in props}
    month_b = await db.bookings.find({"status": "confirmed", "check_in": {"$gte": start, "$lt": end}}).to_list(5000)
    arrivals = await db.bookings.find({"status": "confirmed", "check_in": today}).to_list(100)
    departures = await db.bookings.find({"status": "confirmed", "check_out": today}).to_list(100)
    occupied = await db.bookings.count_documents({"status": {"$ne": "cancelled"}, "check_in": {"$lte": today}, "check_out": {"$gt": today}})
    pending_clean = await db.cleaning.find({"status": {"$nin": ["completed", "cancelled"]}, "date": {"$lte": today}}).sort("date", 1).to_list(50)
    unpaid = await db.invoices.find({"status": "unpaid"}).to_list(1000)

    def bk(b):
        return {"id": str(b["_id"]), "guest_name": b["guest_name"], "ota": b["ota"], "property_name": pmap.get(b["property_id"], "—"), "check_in": b["check_in"], "check_out": b["check_out"]}
    return {
        "month": month, "properties": len(props), "occupied_today": occupied,
        "month_gross": sum(b.get("amount", 0) for b in month_b), "month_bookings": len(month_b),
        "arrivals": [bk(b) for b in arrivals], "departures": [bk(b) for b in departures],
        "pending_cleaning": [{"id": str(c["_id"]), "property_name": pmap.get(c["property_id"], "—"), "date": c["date"], "status": c["status"]} for c in pending_clean],
        "unpaid_invoices": len(unpaid), "unpaid_total": sum(i.get("total", 0) for i in unpaid),
    }


@api.get("/owner/dashboard")
async def owner_dashboard(user=Depends(finance_user)):
    today = date.today().isoformat()
    month = today[:7]
    q: dict[str, Any] = {"is_deleted": {"$ne": True}}
    if owner_pids(user) is not None:
        q["_id"] = {"$in": [ObjectId(x) for x in owner_pids(user)]}
    villas = []
    for p in await db.properties.find(q).sort("name", 1).to_list(100):
        pid = str(p["_id"])
        s = await compute_settlement(p, month)
        upcoming = await db.bookings.count_documents({"property_id": pid, "status": "confirmed", "check_in": {"$gte": today}})
        last_clean = await db.cleaning.find_one({"property_id": pid, "status": "completed"}, sort=[("completed_at", -1)])
        o = {"id": pid, "name": p["name"], "location": p.get("location", ""), "cover_url": p.get("cover_url", ""), "cover_media_id": p.get("cover_media_id", ""),
             "owner_share_percent": p.get("owner_share_percent"), "electricity_mode": p.get("electricity_mode"),
             "month_payout": s["owner_payout"], "month_gross": s["gross"], "month_nights": s["nights"], "occupancy_percent": s["occupancy_percent"],
             "upcoming_bookings": upcoming, "last_cleaned": last_clean.get("completed_at") if last_clean else None,
             "reports": await db.owner_reports.count_documents({"property_id": pid}),
             "month_paid": False}
        payment = await db.payouts.find_one({"property_id": pid, "month": month})
        o["paid_amount"] = payment.get("amount", 0) if payment else 0
        o["balance_due"] = max(0, round(s["owner_payout"] - o["paid_amount"], 2))
        o["month_paid"] = bool(payment) and o["balance_due"] == 0
        o.update(await property_status(pid, today))
        villas.append(o)
    return {"month": month, "villas": villas, "total_payout": sum(v["month_payout"] for v in villas), "total_paid": sum(v["paid_amount"] for v in villas), "total_balance": sum(v["balance_due"] for v in villas)}


@api.get("/meta")
async def meta():
    return {"otas": OTAS}

# ---------------------------------------------------------------- Startup
from guest_ids import register_guest_routes, BoundedGuestUploads
purge_guest_ids = register_guest_routes(api, db, admin_user, oid, now_iso)
from operations import IssueTracker
issue_tracker = IssueTracker(db)
issue_tracker.register(api, admin_user)
from training import Training
training = Training(db, oid, out)
training.register(api, admin_user, current_user)
from calendar_export import register_calendar_exports
register_calendar_exports(api, db, admin_user, oid, now_iso, OTAS)
from cleaning_retention import CleaningRetention
cleaning_retention = CleaningRetention(db, lambda path: delete_object(path), now_iso)
cleaning_retention.register(api, admin_user)
from backups import Backups
backup_service = Backups(db, None, lambda path: get_object(path))
backup_service.register(api, admin_user)
from media_migration import MediaMigration
media_migration = MediaMigration(db)
media_migration.register(api, admin_user)


@api.get("/system/readiness")
async def service_readiness(user=Depends(admin_user)):
    last = await db.backup_runs.find_one({"database_verified": True, "media_verified": True}, sort=[("created_at", -1)])
    return {"media_provider": os.getenv("MEDIA_PROVIDER", "mongo"), "last_backup": last.get("created_at") if last else None,
        "backup_configured": backup_service.store is not None, "external_monitor_configured": os.getenv("EXTERNAL_MONITOR_ENABLED", "false").lower() == "true",
        "app_environment": os.getenv("APP_ENV", "pilot"), "public_app_url": os.getenv("PUBLIC_APP_URL", ""),
        "admins_without_mfa": await db.users.count_documents({"role": "admin", "active": True, "mfa_secret": {"$exists": False}})}
from admin_mfa import AdminMFA
admin_mfa = AdminMFA(db, JWT_SECRET, verify_pw)
admin_mfa.register(api, admin_user, issue_token)
app.include_router(api)
from media_reference_guard import MediaReferenceGuard
app.add_middleware(MediaReferenceGuard, db=db, authenticate=current_user)
app.add_middleware(BoundedGuestUploads)
from request_limits import BoundedAPIBodies
app.add_middleware(BoundedAPIBodies)
app.add_middleware(CORSMiddleware, allow_credentials=True,
    allow_origins=[x.strip() for x in os.getenv("CORS_ORIGINS", "*").split(",") if x.strip()],
    allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def private_guest_responses(request: Request, call_next):
    from fastapi.responses import JSONResponse
    try:
        response = await call_next(request)
    except Exception:
        route = request.scope.get("route")
        label = request.method + " " + (getattr(route, "path", None) or "unknown route")
        reference = await issue_tracker.record(label, True)
        status = 503 if any(x in label for x in ("guest-ids", "/upload", "/files/", "/guest/documents")) else 500
        return JSONResponse({"detail": f"Service temporarily unavailable. Please try again. Reference: {reference}", "code": "SERVICE_UNAVAILABLE", "reference": reference}, status_code=status, headers={"Cache-Control": "no-store"})
    route = request.scope.get("route")
    if route and not request.url.path.startswith("/api/system/"):
        label = request.method + " " + route.path
        if response.status_code >= 500:
            await issue_tracker.record(label, True)
        elif response.status_code < 400:
            await issue_tracker.record(label, False)
    if request.url.path.startswith(("/api/guest/", "/api/guest-ids", "/api/guest-id-audit")) or request.url.path.endswith("/guest-link"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
    return response


async def training_loop():
    while True:
        try:
            from service_lease import business_lease
            async with business_lease(db):
                await training.schedule()
            await issue_tracker.record("Background training scheduler", False)
        except Exception:
            logger.error("Training scheduling failed; retrying")
            await issue_tracker.record("Background training scheduler", True)
        await asyncio.sleep(60)


async def guest_retention_loop():
    while True:
        try:
            from service_lease import business_lease
            async with business_lease(db):
                await purge_guest_ids({"_id": "retention-worker"})
            await issue_tracker.record("Background guest ID cleanup", False)
        except Exception:
            logger.error("Guest ID retention purge failed; retrying next hour")
            await issue_tracker.record("Background guest ID cleanup", True)
        await asyncio.sleep(3600)


async def cleaning_retention_loop():
    while True:
        try:
            await cleaning_retention.run("scheduled-cleanup", "Keep latest two complete cleaning photo sets")
            await issue_tracker.record("Cleaning photo retention", False)
        except Exception:
            await issue_tracker.record("Cleaning photo retention", True)
        await asyncio.sleep(3600)


async def backup_loop():
    while True:
        try:
            if backup_service.store:
                last = await db.backup_runs.find_one({"database_verified": True, "media_verified": True}, sort=[("created_at", -1)])
                requested = await db.settings.find_one({"_id": "backup_requested", "requested": True})
                hour = datetime.now(ZoneInfo("Asia/Kolkata")).hour
                due = not last or (datetime.now(timezone.utc) - datetime.fromisoformat(last["created_at"])).total_seconds() >= 20 * 3600
                overdue = not last or (datetime.now(timezone.utc) - datetime.fromisoformat(last["created_at"])).total_seconds() >= 26 * 3600
                if requested or overdue or (hour == 2 and due):
                    await backup_service.run()
                    await db.settings.update_one({"_id": "backup_requested"}, {"$set": {"requested": False}}, upsert=True)
                    await issue_tracker.record("Encrypted backup verification", False)
        except Exception:
            await issue_tracker.record("Encrypted backup verification", True)
        await asyncio.sleep(60)


async def media_migration_loop():
    while True:
        try:
            requested = await db.settings.find_one({"_id": "media_migration", "requested": True})
            if requested:
                from service_lease import business_lease
                async with business_lease(db, seconds=300):
                    moved = await media_migration.batch()
                if not moved:
                    await db.settings.update_one({"_id": "media_migration"}, {"$set": {"requested": False}})
                await issue_tracker.record("Private photo migration", False)
        except Exception:
            await issue_tracker.record("Private photo migration", True)
        await asyncio.sleep(60)


@app.on_event("startup")
async def startup():
    await training.indexes()
    await db.login_attempts.create_index("expires_at", expireAfterSeconds=0)
    await db.users.create_index("email", unique=True)
    await db.guest_links.create_index("token_hash", unique=True)
    await db.guest_ids.create_index([("booking_id", 1), ("status", 1)])
    await db.guest_ids.create_index("delete_after")
    await db.guest_ids.create_index([("booking_id", 1), ("guest_number", 1)], unique=True, partialFilterExpression={"active": True})
    await db.bookings.create_index([("property_id", 1), ("check_in", 1)])
    await db.owner_reports.create_index("share_token")
    await db.user_sessions.create_index("session_token", unique=True)
    await db.user_sessions.create_index("user_id")
    await db.user_sessions.create_index("expires_at", expireAfterSeconds=0)
    await db.revoked_sessions.create_index("expires_at", expireAfterSeconds=0)
    await db.payouts.create_index([("property_id", 1), ("month", 1)], unique=True)
    await db.calendar_exports.create_index("token", unique=True)
    await db.bookings.create_index([("property_id", 1), ("ical_uid", 1)], unique=True, partialFilterExpression={"ical_uid": {"$type": "string"}})
    app.state.sync_task = asyncio.create_task(auto_sync_loop())
    app.state.retention_task = asyncio.create_task(guest_retention_loop())
    app.state.cleaning_retention_task = asyncio.create_task(cleaning_retention_loop())
    app.state.backup_task = asyncio.create_task(backup_loop())
    app.state.media_migration_task = asyncio.create_task(media_migration_loop())
    app.state.training_task = asyncio.create_task(training_loop())
    for email, pw, name, role in [(os.environ["ADMIN_EMAIL"], os.environ["ADMIN_PASSWORD"], "Britsmaid Admin", "admin"),
                                  (os.environ["ADMIN2_EMAIL"], os.environ["ADMIN2_PASSWORD"], "Ashik", "admin"),
                                  (os.environ["CLEANER_EMAIL"], os.environ["CLEANER_PASSWORD"], os.getenv("CLEANER_NAME", "Priya (Cleaning)"), "cleaner")]:
        existing = await db.users.find_one({"email": email.lower()})
        if not existing:
            await db.users.insert_one({"email": email.lower(), "name": name, "password_hash": hash_pw(pw), "role": role, "active": True, "created_at": now_iso()})
    if os.getenv("SEED_DEMO_DATA", "false").lower() == "true" and await db.properties.count_documents({}) == 0:
        await seed_demo()
    for gmail in [e.strip().lower() for e in os.environ.get("GOOGLE_ADMIN_EMAILS", "").split(",") if e.strip()]:
        if not await db.users.find_one({"email": gmail}):
            await db.users.insert_one({"email": gmail, "name": gmail.split("@")[0], "password_hash": hash_pw(secrets.token_urlsafe(32)), "role": "admin",
                                       "property_ids": [], "phone": "", "active": True, "created_at": now_iso()})
    owner_email = os.environ["OWNER_EMAIL"].lower()
    if not await db.users.find_one({"email": owner_email}):
        first = await db.properties.find_one({"name": "Villa Azure"}) or await db.properties.find_one({})
        await db.users.insert_one({"email": owner_email, "name": os.getenv("OWNER_NAME", "Rahul Mehta (Owner)"), "password_hash": hash_pw(os.environ["OWNER_PASSWORD"]), "role": "owner",
                                   "property_ids": [str(first["_id"])] if first else [], "active": True, "created_at": now_iso()})
    try:
        init_storage()
        logger.info("Object storage ready")
    except Exception as e:
        logger.error("Storage initialization failed")
        await issue_tracker.record("Storage initialization", True)


async def seed_demo():
    t = date.today()
    props = [
        {"name": "Villa Azure", "location": "Candolim, Goa", "owner_name": "Rahul Mehta", "owner_email": "rahul@example.com", "owner_phone": "+91 98200 11111",
         "owner_share_percent": 70, "electricity_mode": "split_half", "base_rate": 12000,
         "rooms": ["Living Room", "Kitchen", "Master Bedroom", "Bedroom 2", "Bathroom 1", "Bathroom 2", "Pool Deck"],
         "cover_url": "https://images.unsplash.com/photo-1580587771525-78b9dba3b914?w=1200&q=80"},
        {"name": "Casa Palms", "location": "Assagao, Goa", "owner_name": "Anita D'Souza", "owner_email": "anita@example.com", "owner_phone": "+91 98200 22222",
         "owner_share_percent": 60, "electricity_mode": "owner", "base_rate": 8500,
         "rooms": ["Living Room", "Kitchen", "Bedroom 1", "Bedroom 2", "Bathroom 1", "Garden"],
         "cover_url": "https://images.unsplash.com/photo-1706808849780-7a04fbac83ef?w=1200&q=80"},
    ]
    ids = []
    for p in props:
        p.update({"ical_feeds": [], "notes": "", "created_at": now_iso(), "is_deleted": False})
        ids.append(str((await db.properties.insert_one(p)).inserted_id))
    demo = [
        (ids[0], "Arjun Kapoor", "Airbnb", -6, -2, 48000, 7200), (ids[0], "Sophie Turner", "Booking.com", -1, 3, 52000, 7800),
        (ids[0], "Vikram Rao", "Direct", 5, 8, 36000, 0), (ids[1], "Meera Iyer", "Agoda", -4, 0, 34000, 5100),
        (ids[1], "John Smith", "Airbnb", 2, 6, 34000, 5100), (ids[0], "Karan Shah", "MakeMyTrip", -40, -36, 44000, 6600),
        (ids[1], "Lisa Wong", "Booking.com", -35, -30, 42500, 6375),
    ]
    for pid, g, ota, a, b, amt, com in demo:
        ci, co = (t + timedelta(days=a)).isoformat(), (t + timedelta(days=b)).isoformat()
        r = await db.bookings.insert_one({"property_id": pid, "guest_name": g, "guest_phone": "", "guest_email": "", "guests": 2, "ota": ota, "check_in": ci, "check_out": co,
                                          "amount": amt, "ota_commission": com, "status": "confirmed", "notes": "", "source": "manual", "created_at": now_iso()})
        await ensure_cleaning(pid, str(r.inserted_id), co)
        if b < 0:
            await db.cleaning.update_one({"booking_id": str(r.inserted_id)}, {"$set": {"status": "completed", "completed_at": now_iso()}})
    await db.expenses.insert_one({"property_id": ids[0], "month": t.isoformat()[:7], "type": "electricity", "amount": 6400, "notes": "Monthly bill", "created_at": now_iso()})


@app.on_event("shutdown")
async def shutdown_db_client():
    tasks = [getattr(app.state, name, None) for name in ("sync_task", "retention_task", "cleaning_retention_task", "training_task", "backup_task", "media_migration_task")]
    for task in tasks:
        if task:
            task.cancel()
    await asyncio.gather(*(task for task in tasks if task), return_exceptions=True)
    client.close()
