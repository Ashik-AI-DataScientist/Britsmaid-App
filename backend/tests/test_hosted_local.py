"""Isolated hosted adapter/entrypoint tests. No Render, Atlas or live data."""
import os
import sys
from pathlib import Path

import httpx
import mongomock
import pytest
from fastapi import FastAPI, HTTPException
from mongomock.gridfs import enable_gridfs_integration
from test_role_security_local import ctx, auth, server

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hosted_app import SPAFiles, install_hosted_routes, validate_hosted_settings
from mongo_media import MongoMediaStore


@pytest.fixture
def store():
    enable_gridfs_integration()
    instance = MongoMediaStore(mongomock.MongoClient().hosted_media)
    # MongoMock does not implement PyMongo's client-side timeout option.
    instance.bucket._timeout = None
    return instance


def test_gridfs_bytes_persist_across_adapter_instances_and_retry(store):
    path = "britsmaid/uploads/user-a/media-one.jpg"
    result = store.put(path, b"synthetic-photo", "image/jpeg")
    assert store.put(path, b"synthetic-photo", "image/jpeg") == result
    other = MongoMediaStore(store.db)
    other.bucket._timeout = None
    assert other.get(result["path"]) == (b"synthetic-photo", "image/jpeg")
    assert store.db.app_media.files.count_documents({}) == 1
    assert store.db.app_media.chunks.count_documents({}) == 1


def test_gridfs_changed_retry_is_rejected(store):
    path = "britsmaid/uploads/user-a/same.jpg"
    store.put(path, b"one", "image/jpeg")
    with pytest.raises(HTTPException) as exc:
        store.put(path, b"different", "image/jpeg")
    assert exc.value.status_code == 409


def test_media_budget_counts_orphan_chunks(store):
    store.budget = 255 * 1024
    store.db.app_media.chunks.insert_one({"data": b"orphan"})
    with pytest.raises(HTTPException) as exc:
        store.put("britsmaid/uploads/user-a/full.jpg", b"new", "image/jpeg")
    assert exc.value.status_code == 507
    assert store.db.app_media.files.count_documents({}) == 0


@pytest.mark.parametrize("path", ["guest-ids/private.jpg", "../secret", "other/uploads/a.jpg"])
def test_private_documents_not_routed_to_ordinary_store(store, path):
    with pytest.raises(HTTPException) as exc:
        store.put(path, b"not-a-real-id", "image/jpeg")
    assert exc.value.status_code == 422


@pytest.mark.parametrize("path", ["secret", "mongo:invalid", "mongo:000000000000000000000001"])
def test_missing_media_returns_404(store, path):
    with pytest.raises(HTTPException) as exc:
        store.get(path)
    assert exc.value.status_code == 404


def settings(monkeypatch):
    for key in ["MONGO_URL", "DB_NAME", "JWT_SECRET", "ADMIN_PASSWORD", "OWNER_PASSWORD", "CLEANER_PASSWORD", "SUPERVISOR_PASSWORD"]:
        monkeypatch.setenv(key, "synthetic-setting-" + key + "-long-enough")
    monkeypatch.setenv("SEED_DEMO_DATA", "false")
    monkeypatch.delenv("GOOGLE_ADMIN_EMAILS", raising=False)


def test_hosted_configuration_requires_stable_strong_secrets(monkeypatch):
    settings(monkeypatch)
    validate_hosted_settings()
    monkeypatch.setenv("JWT_SECRET", "weak")
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        validate_hosted_settings()


@pytest.mark.parametrize("key,value", [("SEED_DEMO_DATA", "true"), ("GOOGLE_ADMIN_EMAILS", "unexpected@example.com")])
def test_hosted_refuses_automatic_demo_or_admin_provisioning(monkeypatch, key, value):
    settings(monkeypatch)
    monkeypatch.setenv(key, value)
    with pytest.raises(RuntimeError):
        validate_hosted_settings()


@pytest.mark.asyncio
async def test_spa_fallback_does_not_hide_unknown_api_or_asset(tmp_path):
    (tmp_path / "index.html").write_text("SYNTHETIC APP", encoding="utf-8")
    app = FastAPI()
    app.mount("/", SPAFiles(directory=tmp_path, html=True))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as client:
        assert (await client.get("/owner/a")).text == "SYNTHETIC APP"
        assert (await client.get("/guest-check-in")).status_code == 200
        assert (await client.get("/api/not-a-route")).status_code == 404
        assert (await client.get("/missing.js")).status_code == 404


@pytest.mark.asyncio
async def test_hosted_routes_keep_all_four_role_guards(ctx, tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("SYNTHETIC APP", encoding="utf-8")
    monkeypatch.setenv("WEB_BUILD_DIR", str(tmp_path))
    app = FastAPI()
    app.include_router(server.api)
    install_hosted_routes(app, server, mongomock.MongoClient())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as client:
        for role in ["admin", "owner", "cleaner", "supervisor"]:
            result = await client.get("/api/properties", headers=auth(ctx, role))
            assert result.status_code == 200
            assert result.headers["referrer-policy"] == "no-referrer"
        for role in ["owner", "cleaner", "supervisor"]:
            assert (await client.get("/api/guest-ids", headers=auth(ctx, role))).status_code == 403
        assert (await client.get("/api/guest-ids")).status_code == 401
        assert (await client.post("/api/auth/session", json={"session_id": "not-used"})).status_code == 503
        assert (await client.get("/openapi.json")).status_code == 404


@pytest.mark.asyncio
async def test_login_throttle_returns_clear_retry(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("SYNTHETIC APP", encoding="utf-8")
    monkeypatch.setenv("WEB_BUILD_DIR", str(tmp_path))
    app = FastAPI()
    install_hosted_routes(app, server, mongomock.MongoClient())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as client:
        for _ in range(20):
            await client.post("/api/auth/login")
        response = await client.post("/api/auth/login")
        assert response.status_code == 429
        assert response.headers["retry-after"] == "60"
