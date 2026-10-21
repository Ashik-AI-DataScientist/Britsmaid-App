"""Render entry point: persistent MongoDB, private ordinary files and same-origin web."""
import os
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pymongo import MongoClient
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles


def validate_hosted_settings():
    required = ["MONGO_URL", "DB_NAME", "JWT_SECRET", "ADMIN_PASSWORD", "OWNER_PASSWORD",
                "CLEANER_PASSWORD", "SUPERVISOR_PASSWORD"]
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise RuntimeError("Missing hosted configuration: " + ", ".join(missing))
    for key in required[2:]:
        if len(os.environ[key]) < 24:
            raise RuntimeError(key + " must be a unique generated secret of at least 24 characters")
    if os.getenv("SEED_DEMO_DATA", "false").lower() != "false":
        raise RuntimeError("Hosted accounts must start without demonstration data")
    if os.getenv("GOOGLE_ADMIN_EMAILS"):
        raise RuntimeError("Automatic Google admin provisioning is disabled for this deployment")
    os.environ.setdefault("ADMIN_EMAIL", "admin@example.com")
    os.environ.setdefault("OWNER_EMAIL", "owner@example.com")
    os.environ.setdefault("CLEANER_EMAIL", "cleaner@example.com")
    os.environ.setdefault("SUPERVISOR_EMAIL", "supervisor@example.com")
    os.environ["ADMIN2_EMAIL"] = os.environ["ADMIN_EMAIL"]
    os.environ["ADMIN2_PASSWORD"] = os.environ["ADMIN_PASSWORD"]
    os.environ.setdefault("CLEANER_NAME", "Britsmaid Cleaner")
    os.environ.setdefault("OWNER_NAME", "Britsmaid Owner")
    os.environ["CORS_ORIGINS"] = os.getenv("CORS_ORIGINS", "")


class SPAFiles(StaticFiles):
    async def get_response(self, path, scope):
        route_path = path.replace("\\", "/").lstrip("/")
        if route_path == "api" or route_path.startswith("api/"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or "." in route_path.rsplit("/", 1)[-1]:
                raise
            return await super().get_response("index.html", scope)


def install_hosted_routes(application, api_server, media_client):
    attempts = defaultdict(deque)

    @application.middleware("http")
    async def hosted_security(request: Request, call_next):
        if request.url.path == "/api/auth/session":
            return JSONResponse({"detail": "Google sign-in is not configured. Use your assigned email and password."}, status_code=503)
        if request.url.path == "/api/auth/login" and request.method == "POST":
            key = request.client.host if request.client else "unknown"
            now = time.monotonic()
            queue = attempts[key]
            while queue and queue[0] < now - 60:
                queue.popleft()
            if len(queue) >= 20:
                return JSONResponse({"detail": "Too many sign-in attempts. Wait one minute and try again."}, status_code=429, headers={"Retry-After": "60"})
            queue.append(now)
            if len(attempts) > 1000:
                for old_key in list(attempts):
                    if not attempts[old_key] or attempts[old_key][-1] < now - 60:
                        del attempts[old_key]
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    @application.get("/healthz", include_in_schema=False)
    async def health():
        try:
            await api_server.db.command("ping")
        except Exception:
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return {"status": "ok", "mode": "persistent-test", "source": os.getenv("RENDER_GIT_COMMIT", "")}

    @application.on_event("startup")
    async def supervisor_account():
        email = os.environ["SUPERVISOR_EMAIL"].lower()
        if not await api_server.db.users.find_one({"email": email}):
            await api_server.db.users.insert_one({"email": email, "name": "Britsmaid Supervisor",
                "password_hash": api_server.hash_pw(os.environ["SUPERVISOR_PASSWORD"]),
                "role": "supervisor", "active": True, "property_ids": [], "created_at": api_server.now_iso()})

    @application.on_event("shutdown")
    async def close_storage():
        media_client.close()

    # API documentation is kept in source, not anonymously exposed by this host.
    application.router.routes[:] = [r for r in application.router.routes
        if getattr(r, "path", "") not in ("/docs", "/redoc", "/docs/oauth2-redirect", "/openapi.json")]
    web = Path(os.getenv("WEB_BUILD_DIR", "/app/web"))
    if not (web / "index.html").is_file():
        raise RuntimeError("The hosted web export is missing")
    application.mount("/", SPAFiles(directory=web, html=True), name="web")


def create_app():
    validate_hosted_settings()
    import server
    from mongo_media import MongoMediaStore
    storage_client = MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=10000,
                                 maxPoolSize=5, appname="BritsmaidMedia")
    store = MongoMediaStore(storage_client[os.environ["DB_NAME"]])
    server.init_storage = store.ready
    server.put_object = store.put
    server.get_object = store.get
    install_hosted_routes(server.app, server, storage_client)
    return server.app
