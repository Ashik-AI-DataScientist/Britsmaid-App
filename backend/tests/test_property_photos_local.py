"""Synthetic cover-photo tests; no live accounts, storage or personal photos."""
from bson import ObjectId
import pytest
from test_role_security_local import ctx, auth, jpeg, server

pytestmark = pytest.mark.asyncio


async def photo(ctx, monkeypatch):
    monkeypatch.setattr(server, "put_object", lambda path, data, ctype: {"path": path, "size": len(data)})
    response = await ctx["client"].post("/api/upload", headers=auth(ctx), files={"file": ("villa.jpg", jpeg(), "image/jpeg")})
    assert response.status_code == 200, response.text
    return response.json()["id"]


async def save(ctx, media_id, role="admin"):
    return await ctx["client"].put(f'/api/properties/{ctx["p1"]}', headers=auth(ctx, role), json={"name": "SAMPLE villa", "cover_media_id": media_id})


async def test_upload_cover_persists_and_scoped_image_access(ctx, monkeypatch):
    mid = await photo(ctx, monkeypatch)
    result = await save(ctx, mid)
    assert result.status_code == 200, result.text
    assert result.json()["cover_media_id"] == mid
    for role in ["admin", "owner", "cleaner", "supervisor"]:
        response = await ctx["client"].get(f"/api/files/{mid}", headers=auth(ctx, role))
        assert response.status_code == 200, (role, response.text)
        assert response.headers["cache-control"] == "private, no-store"
    for role in ["other_owner", "other_cleaner"]:
        assert (await ctx["client"].get(f"/api/files/{mid}", headers=auth(ctx, role))).status_code == 404
    assert (await ctx["client"].get(f"/api/files/{mid}")).status_code == 401
    properties = (await ctx["client"].get("/api/properties", headers=auth(ctx, "owner"))).json()
    assert properties[0]["cover_media_id"] == mid
    await ctx["db"].bookings.update_one({"_id": ObjectId(ctx["bid"])}, {"$set": {"ota": "Direct"}})
    dashboard = await ctx["client"].get("/api/owner/dashboard", headers=auth(ctx, "owner"))
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["villas"][0]["cover_media_id"] == mid


@pytest.mark.parametrize("role", ["owner", "cleaner", "supervisor"])
async def test_only_admin_can_set_cover(ctx, monkeypatch, role):
    mid = await photo(ctx, monkeypatch)
    assert (await save(ctx, mid, role)).status_code == 403


async def test_replace_remove_and_retained_cover(ctx, monkeypatch):
    first = await photo(ctx, monkeypatch)
    second = await photo(ctx, monkeypatch)
    assert (await save(ctx, first)).status_code == 200
    # An unchanged cover remains valid when another admin edits the villa.
    await ctx["db"].media.update_one({"_id": ObjectId(first)}, {"$set": {"owner_id": str(ObjectId())}})
    assert (await save(ctx, first)).status_code == 200
    assert (await save(ctx, second)).status_code == 200
    assert (await ctx["client"].get(f"/api/files/{first}", headers=auth(ctx, "owner"))).status_code == 404
    assert (await save(ctx, "")).status_code == 200
    assert (await ctx["client"].get(f"/api/files/{second}", headers=auth(ctx, "owner"))).status_code == 404
    assert await ctx["db"].media.count_documents({"is_deleted": False}) == 2


@pytest.mark.parametrize("change", [{"kind": "video"}, {"is_deleted": True}, {"owner_id": "someone-else"}, {"attachment_binding": "room:before"}])
async def test_reject_unusable_or_unowned_cover(ctx, monkeypatch, change):
    mid = await photo(ctx, monkeypatch)
    await ctx["db"].media.update_one({"_id": ObjectId(mid)}, {"$set": change})
    assert (await save(ctx, mid)).status_code == 422


async def test_missing_cover_and_report_attachment_rejected(ctx, monkeypatch):
    assert (await save(ctx, str(ObjectId()))).status_code == 422
    mid = await photo(ctx, monkeypatch)
    await ctx["db"].owner_reports.insert_one({"property_id": ctx["p1"], "media_ids": [mid]})
    assert (await save(ctx, mid)).status_code == 422


async def test_new_property_legacy_cover_and_deleted_property(ctx, monkeypatch):
    mid = await photo(ctx, monkeypatch)
    response = await ctx["client"].post("/api/properties", headers=auth(ctx), json={"name": "SAMPLE new villa", "cover_media_id": mid})
    assert response.status_code == 200, response.text
    assert response.json()["cover_media_id"] == mid
    response = await ctx["client"].put(f'/api/properties/{ctx["p1"]}', headers=auth(ctx), json={"name": "SAMPLE old villa", "cover_url": "https://example.com/cover.jpg"})
    assert response.json()["cover_url"] == "https://example.com/cover.jpg"
    await ctx["db"].properties.update_one({"_id": ObjectId(ctx["p1"])}, {"$set": {"is_deleted": True}})
    assert (await save(ctx, mid)).status_code == 404


async def test_invalid_photo_has_helpful_error_without_writing_storage(ctx, monkeypatch):
    def no_write(*args):
        pytest.fail("Invalid photo reached storage")
    monkeypatch.setattr(server, "put_object", no_write)
    response = await ctx["client"].post("/api/upload", headers=auth(ctx), files={"file": ("bad.jpg", b"not-an-image", "image/jpeg")})
    assert response.status_code == 422
    assert "photo" in response.json()["detail"]
    assert "ID image" not in response.json()["detail"]
