"""Synthetic security tests. No live service, DNS, accounts or storage are used."""
import gzip
import asyncio
import socket
from datetime import datetime, timedelta, timezone
from bson import ObjectId
import jwt
import pytest
import httpx
import mongomock
import base64
import hashlib
from fastapi import FastAPI
from hosted_app import install_hosted_routes
from request_limits import BoundedAPIBodies
from test_role_security_local import ctx, auth, server
import safe_calendar_fetch as fetcher


@pytest.mark.parametrize("url", ["http://example.com/feed", "https://localhost/feed", "https://user:secret@example.com/feed", "https://example.com:8443/feed", "https://example.com/feed#fragment", "https://example.com/\r\nheader", "file:///etc/passwd", "https://example.com\\@localhost/"])
def test_calendar_rejects_unsafe_url(url):
    with pytest.raises(fetcher.CalendarFetchError):
        fetcher.validate_url(url)


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "192.168.0.1", "::1", "fc00::1", "224.0.0.1", "::ffff:127.0.0.1"])
def test_calendar_rejects_private_dns_and_mixed_answers(monkeypatch, ip):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(2, 1, 6, "", ("8.8.8.8", 443)), (2, 1, 6, "", (ip, 443))])
    with pytest.raises(fetcher.CalendarFetchError):
        fetcher.public_addresses("synthetic.invalid")


def mock_provider(monkeypatch, responses):
    calls = []
    class Connection:
        def __init__(self, host, address):
            calls.append((host, address))
        def request(self, *a, **kw):
            pass
        def getresponse(self):
            status, headers, body = responses.pop(0)
            class Response:
                def getheader(self, name, default=None):
                    return headers.get(name, default)
                def read(self, size):
                    return body[:size]
            response = Response()
            response.status = status
            return response
        def close(self):
            pass
    monkeypatch.setattr(fetcher, "PinnedHTTPSConnection", Connection)
    def addresses(host, *a, **kw):
        ip = "127.0.0.1" if host == "localhost.invalid" else "8.8.8.8"
        return [(2, 1, 6, "", (ip, 443))]
    monkeypatch.setattr(socket, "getaddrinfo", addresses)
    return calls


def test_redirect_is_checked_before_connecting(monkeypatch):
    calls = mock_provider(monkeypatch, [(302, {"Location": "https://localhost.invalid/private"}, b"")])
    with pytest.raises(fetcher.CalendarFetchError):
        fetcher.fetch_calendar("https://public.invalid/feed")
    assert calls == [("public.invalid", "8.8.8.8")]


@pytest.mark.parametrize("headers,body", [({"Content-Length": str(fetcher.MAX_FEED_BYTES + 1)}, b""), ({}, b"x" * (fetcher.MAX_FEED_BYTES + 1)), ({"Content-Encoding": "gzip"}, gzip.compress(b"x" * (fetcher.MAX_FEED_BYTES + 1)))], ids=["declared-large", "stream-large", "gzip-bomb"])
def test_calendar_size_and_compression_bombs(monkeypatch, headers, body):
    mock_provider(monkeypatch, [(200, headers, body)])
    with pytest.raises(fetcher.CalendarFetchError):
        fetcher.fetch_calendar("https://public.invalid/feed")


def test_public_redirect_and_gzip_work(monkeypatch):
    mock_provider(monkeypatch, [(302, {"Location": "/final"}, b""), (200, {"Content-Encoding": "gzip"}, gzip.compress(b"BEGIN:VCALENDAR"))])
    assert fetcher.fetch_calendar("https://public.invalid/feed") == "BEGIN:VCALENDAR"


async def photo(ctx):
    mid = str(ObjectId())
    await ctx["db"].media.insert_one({"_id": ObjectId(mid), "is_deleted": False, "storage_path": "synthetic-photo", "owner_id": str(ctx["users"]["admin"]["_id"]), "content_type": "image/jpeg"})
    await ctx["db"].properties.update_one({"_id": ObjectId(ctx["p1"])}, {"$set": {"cover_media_id": mid}})
    return mid


@pytest.mark.asyncio
async def test_photo_ticket_scoped_not_an_api_login_and_revoked_on_logout(ctx):
    mid = await photo(ctx)
    headers = auth(ctx, "owner")
    result = await ctx["client"].post(f"/api/files/{mid}/ticket", headers=headers)
    assert result.status_code == 200
    ticket = result.json()["ticket"]
    payload = jwt.decode(ticket, server.JWT_SECRET, algorithms=[server.JWT_ALG], audience="britsmaid-media")
    assert payload["exp"] - payload["iat"] == 300
    url = f"/api/files/{mid}?ticket={ticket}"
    assert (await ctx["client"].get(url)).content == b"photo"
    assert (await ctx["client"].get(f"/api/files/{ObjectId()}?ticket={ticket}")).status_code == 401
    assert (await ctx["client"].get("/api/auth/me", headers={"Authorization": f"Bearer {ticket}"})).status_code == 401
    assert (await ctx["client"].get(f'/api/files/{mid}?token={headers["Authorization"][7:]}')).status_code == 401
    assert (await ctx["client"].post("/api/auth/logout", headers=headers)).status_code == 200
    assert (await ctx["client"].get(url)).status_code == 401
    assert (await ctx["client"].get("/api/auth/me", headers=headers)).status_code == 401
    assert await ctx["db"].revoked_sessions.count_documents({}) == 1


@pytest.mark.asyncio
async def test_ticket_rechecks_property_access_and_account_active(ctx):
    mid = await photo(ctx)
    assert (await ctx["client"].post(f"/api/files/{mid}/ticket", headers=auth(ctx, "other_owner"))).status_code == 404
    ticket = (await ctx["client"].post(f"/api/files/{mid}/ticket", headers=auth(ctx, "owner"))).json()["ticket"]
    await ctx["db"].users.update_one({"_id": ctx["users"]["owner"]["_id"]}, {"$set": {"property_ids": []}})
    assert (await ctx["client"].get(f"/api/files/{mid}?ticket={ticket}")).status_code == 404
    await ctx["db"].users.update_one({"_id": ctx["users"]["owner"]["_id"]}, {"$set": {"active": False}})
    assert (await ctx["client"].get(f"/api/files/{mid}?ticket={ticket}")).status_code == 401


@pytest.mark.asyncio
async def test_expired_ticket_and_password_change_fail_closed(ctx):
    mid = await photo(ctx)
    ticket = (await ctx["client"].post(f"/api/files/{mid}/ticket", headers=auth(ctx))).json()["ticket"]
    payload = jwt.decode(ticket, server.JWT_SECRET, algorithms=[server.JWT_ALG], audience="britsmaid-media")
    expired = jwt.encode({**payload, "exp": datetime.now(timezone.utc) - timedelta(seconds=1)}, server.JWT_SECRET, algorithm=server.JWT_ALG)
    assert (await ctx["client"].get(f"/api/files/{mid}?ticket={expired}")).status_code == 401
    await ctx["db"].users.update_one({"_id": ctx["users"]["admin"]["_id"]}, {"$inc": {"session_version": 1}})
    assert (await ctx["client"].get(f"/api/files/{mid}?ticket={ticket}")).status_code == 401


def test_separate_logins_have_separate_session_tokens():
    user = {"_id": ObjectId(), "role": "admin"}
    assert server.issue_token(user) != server.issue_token(user)


@pytest.mark.asyncio
async def test_security_headers_cover_web_api_and_early_errors(tmp_path, monkeypatch):
    script = "window.installReady = true;"
    (tmp_path / "index.html").write_text("<html>App</html>", encoding="utf-8")
    (tmp_path / "install.html").write_text(f"<script>{script}</script>", encoding="utf-8")
    monkeypatch.setenv("WEB_BUILD_DIR", str(tmp_path))
    app = FastAPI()
    app.include_router(server.api)
    install_hosted_routes(app, server, mongomock.MongoClient())
    digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as client:
        for path in ["/", "/install.html", "/api/auth/me", "/api/auth/session"]:
            result = await client.get(path) if path != "/api/auth/session" else await client.post(path)
            policy = result.headers["content-security-policy"]
            assert f"'sha256-{digest}'" in policy
            assert "script-src 'self'" in policy and "'unsafe-eval'" not in policy
            assert result.headers["strict-transport-security"] == "max-age=31536000"
            assert result.headers["referrer-policy"] == "no-referrer"
            assert result.headers["x-frame-options"] == "DENY"
            assert "camera=(self)" in result.headers["permissions-policy"]
            if path.startswith("/api/"):
                assert result.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_chunked_upload_stops_receiving_at_request_limit():
    received = 0
    messages = []
    async def receive():
        nonlocal received
        received += 1
        return {"type": "http.request", "body": b"x" * (1024 * 1024), "more_body": True}
    async def send(message):
        messages.append(message)
    async def parser(scope, receive, send):
        try:
            while True:
                await receive()
        except Exception:
            # Simulate multipart parser translating the receive exception to 400.
            await send({"type": "http.response.start", "status": 400, "headers": []})
            await send({"type": "http.response.body", "body": b"bad multipart"})
    await BoundedAPIBodies(parser)({"type": "http", "path": "/api/upload", "headers": []}, receive, send)
    assert received == 101
    assert messages[0]["status"] == 413
    assert b"too large" in messages[1]["body"]


@pytest.mark.asyncio
async def test_concurrent_upload_gets_retry_and_slot_is_released():
    started, release = asyncio.Event(), asyncio.Event()
    messages = []
    async def app(scope, receive, send):
        started.set()
        await release.wait()
    async def receive():
        return {"type": "http.request", "body": b""}
    async def send(message):
        messages.append(message)
    middleware = BoundedAPIBodies(app)
    scope = {"type": "http", "path": "/api/upload", "method": "POST", "headers": []}
    first = asyncio.create_task(middleware(scope, receive, send))
    await started.wait()
    await middleware(scope, receive, send)
    assert messages[0]["status"] == 429
    assert (b"retry-after", b"2") in messages[0]["headers"]
    release.set()
    await first
    assert not middleware.upload_active


@pytest.mark.asyncio
async def test_stalled_upload_times_out_and_releases_slot():
    messages = []
    async def app(scope, receive, send):
        await asyncio.Event().wait()
    async def receive():
        return {"type": "http.request", "body": b""}
    async def send(message):
        messages.append(message)
    middleware = BoundedAPIBodies(app)
    middleware.upload_timeout = 0.01
    await middleware({"type": "http", "path": "/api/upload", "method": "POST", "headers": []}, receive, send)
    assert messages[0]["status"] == 408
    assert not middleware.upload_active


@pytest.mark.asyncio
@pytest.mark.parametrize("chunked", [False, True])
async def test_oversized_json_returns_clear_413(ctx, chunked):
    data = b'x' * (1024 * 1024 + 1)
    async def chunks():
        yield data[:500000]
        yield data[500000:]
    result = await ctx["client"].post("/api/auth/login", content=chunks() if chunked else data, headers={"Content-Type": "application/json"})
    assert result.status_code == 413, result.text
    assert "too large" in result.json()["detail"]


@pytest.mark.asyncio
async def test_invalid_calendar_link_returns_field_error_without_saving(ctx):
    result = await ctx["client"].post("/api/properties", headers=auth(ctx), json={"name": "Synthetic property", "ical_feeds": [{"ota": "Other", "url": "http://localhost/private"}]})
    assert result.status_code == 422
    assert "HTTPS" in result.text
    assert await ctx["db"].properties.count_documents({}) == 2
