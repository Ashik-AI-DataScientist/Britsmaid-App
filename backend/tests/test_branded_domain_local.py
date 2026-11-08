"""Synthetic custom-domain cutover tests; no public DNS or hosted writes."""
import httpx
import mongomock
import pytest
from fastapi import FastAPI
from test_role_security_local import ctx, auth, server
from hosted_app import install_hosted_routes

OLD = "https://britsmaid-test.onrender.com"
NEW = "https://app.britsmaid.in"


@pytest.fixture
def domain_app(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("SYNTHETIC APP", encoding="utf-8")
    (tmp_path / "install.html").write_text("SYNTHETIC INSTALL", encoding="utf-8")
    monkeypatch.setenv("WEB_BUILD_DIR", str(tmp_path))
    monkeypatch.setenv("PUBLIC_APP_URL", NEW)
    monkeypatch.setenv("LEGACY_APP_ORIGIN", OLD)
    app = FastAPI()
    app.include_router(server.api)
    install_hosted_routes(app, server, mongomock.MongoClient())
    return app


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/", "/login", "/calendar?month=2026-11", "/install.html", "/guest-check-in", "/owner/test?note=a%26b"])
async def test_only_old_web_links_redirect_and_keep_path_query(domain_app, path):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=domain_app), base_url=OLD) as client:
        for method in ("GET", "HEAD"):
            result = await client.request(method, path)
            assert result.status_code == 307
            assert result.headers["location"] == NEW + path
            assert result.headers["cache-control"] == "no-store"
            assert result.headers["referrer-policy"] == "no-referrer"
            assert "set-cookie" not in result.headers


@pytest.mark.asyncio
async def test_new_origin_no_loop_unknown_host_no_redirect(domain_app):
    for origin in (NEW, "https://unrelated.invalid"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=domain_app), base_url=origin) as client:
            result = await client.get("/")
            assert result.status_code == 200
            assert "location" not in result.headers


@pytest.mark.asyncio
async def test_legacy_api_and_health_are_not_redirected(ctx, domain_app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=domain_app), base_url=OLD) as client:
        for path in ("/healthz", "/healthz/backup", "/api/auth/me", "/api/does-not-exist"):
            result = await client.get(path)
            assert result.status_code not in (301, 302, 307, 308)
            assert "location" not in result.headers
        assert (await client.post("/login")).status_code not in (301, 302, 307, 308)
        export = await client.post(f'/api/properties/{ctx["p1"]}/ical-export', headers=auth(ctx))
        assert export.status_code == 200
        feed = await client.get('/api/ical/' + export.json()["token"] + '.ics')
        assert feed.status_code == 200
        assert 'BEGIN:VCALENDAR' in feed.text
        assert 'Guest' not in feed.text


@pytest.mark.asyncio
async def test_cookie_actions_require_new_origin_but_bearer_clients_still_work(ctx, domain_app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=domain_app), base_url=NEW) as client:
        client.cookies.set("bm_session", server.issue_token(ctx["users"]["admin"]))
        route = '/api/users/' + str(ctx["users"]["owner"]["_id"])
        for origin in (OLD, "https://untrusted.invalid"):
            result = await client.put(route, headers={"Origin": origin}, json={"name": "Untrusted change"})
            assert result.status_code == 403
        result = await client.put(route, headers={"Origin": NEW, "Sec-Fetch-Site": "same-origin"}, json={"name": "SAMPLE renamed"})
        assert result.status_code == 200, result.text
        assert result.json()["name"] == "SAMPLE renamed"
        cross_site = await client.put(route, headers={"Origin": NEW, "Sec-Fetch-Site": "cross-site"}, json={"name": "Blocked"})
        assert cross_site.status_code == 403
        assert (await client.get('/api/properties', headers=auth(ctx, "owner"))).status_code == 200
