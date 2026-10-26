"""Local synthetic regression tests. No live calendars, accounts or storage."""
import asyncio
import io
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from bson import ObjectId
from icalendar import Calendar
from PIL import Image
import pytest
from test_role_security_local import ctx, auth, server
from media_images import normalise_photo


async def feed(ctx):
    response = await ctx["client"].post(f'/api/properties/{ctx["p1"]}/ical-export', headers=auth(ctx))
    assert response.status_code == 200, response.text
    return "/api/ical/" + response.json()["token"] + ".ics"


@pytest.mark.asyncio
async def test_export_is_stable_private_and_reflects_cancel_and_blocks(ctx):
    path = await feed(ctx)
    assert await feed(ctx) == path
    response = await ctx["client"].get(path)
    assert response.status_code == 200
    events = Calendar.from_ical(response.content).walk("VEVENT")
    assert len(events) == 1
    event = events[0]
    booking = await ctx["db"].bookings.find_one({"_id": ObjectId(ctx["bid"])})
    assert event.decoded("dtstart") == date.fromisoformat(booking["check_in"])
    assert event.decoded("dtend") == date.fromisoformat(booking["check_out"])
    assert str(event["uid"]) == f'{ctx["bid"]}@calendar.britsmaid'
    assert str(event["summary"]) == "Britsmaid - Unavailable"
    assert all(field not in response.text for field in ["Guest", "private", "1000", "guest_name", "owner_phone"])
    assert response.headers["cache-control"] == "private, no-store"
    await ctx["db"].bookings.update_one({"_id": booking["_id"]}, {"$set": {"status": "blocked"}})
    assert len(Calendar.from_ical((await ctx["client"].get(path)).content).walk("VEVENT")) == 1
    await ctx["db"].bookings.update_one({"_id": booking["_id"]}, {"$set": {"status": "cancelled"}})
    assert not Calendar.from_ical((await ctx["client"].get(path)).content).walk("VEVENT")


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["owner", "other_owner", "cleaner", "supervisor"])
async def test_only_admin_can_manage_feed_links(ctx, role):
    url = f'/api/properties/{ctx["p1"]}/ical-export'
    for method in ["GET", "POST", "DELETE"]:
        assert (await ctx["client"].request(method, url, headers=auth(ctx, role))).status_code == 403


@pytest.mark.asyncio
async def test_destination_exclusion_scoping_and_revocation(ctx):
    path = await feed(ctx)
    first = await ctx["db"].bookings.find_one({"_id": ObjectId(ctx["bid"])})
    await ctx["db"].bookings.update_one({"_id": first["_id"]}, {"$set": {"ota": "Airbnb"}})
    other = {**first, "_id": ObjectId(), "property_id": ctx["p2"], "guest_name": "NEVER EXPORT OTHER VILLA"}
    await ctx["db"].bookings.insert_one(other)
    assert not Calendar.from_ical((await ctx["client"].get(path + "?exclude_ota=Airbnb")).content).walk("VEVENT")
    assert len(Calendar.from_ical((await ctx["client"].get(path + "?exclude_ota=Booking.com")).content).walk("VEVENT")) == 1
    assert (await ctx["client"].get(path + "?exclude_ota=invalid")).status_code == 422
    await ctx["client"].delete(f'/api/properties/{ctx["p1"]}/ical-export', headers=auth(ctx))
    assert (await ctx["client"].get(path)).status_code == 404
    assert await feed(ctx) != path


@pytest.mark.asyncio
async def test_deleted_property_and_invalid_feed_fail_closed(ctx):
    path = await feed(ctx)
    await ctx["db"].properties.update_one({"_id": ObjectId(ctx["p1"])}, {"$set": {"is_deleted": True}})
    assert (await ctx["client"].get(path)).status_code == 404
    assert (await ctx["client"].get("/api/ical/not-a-link.ics")).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("age,expected", [(599, 0), (601, 1), (3601, 1)])
async def test_ten_minute_sync_cadence(ctx, monkeypatch, age, expected):
    assert server.SYNC_INTERVAL_SECONDS == 600
    await ctx["db"].settings.insert_one({"_id": "ical_sync", "last_run": (datetime.now(timezone.utc) - timedelta(seconds=age)).isoformat()})
    calls = []
    async def sync(trigger):
        calls.append(trigger)
        return {}
    async def stop(seconds):
        assert seconds <= 60
        raise asyncio.CancelledError()
    monkeypatch.setattr(server, "sync_all", sync)
    monkeypatch.setattr(server.asyncio, "sleep", stop)
    with pytest.raises(asyncio.CancelledError):
        await server.auto_sync_loop()
    assert len(calls) == expected
    status = (await ctx["client"].get("/api/sync/status", headers=auth(ctx))).json()
    assert status["interval_minutes"] == 10
    assert datetime.fromisoformat(status["next_run"]) - datetime.fromisoformat(status["last_run"]) == timedelta(minutes=10)


@pytest.mark.asyncio
async def test_import_ignores_our_exported_event_to_avoid_loop(ctx, monkeypatch):
    path = await feed(ctx)
    contents = (await ctx["client"].get(path)).text
    monkeypatch.setattr(server.requests, "get", lambda *a, **kw: SimpleNamespace(text=contents, raise_for_status=lambda: None))
    prop = await ctx["db"].properties.find_one({"_id": ObjectId(ctx["p1"])})
    prop["ical_feeds"] = [{"ota": "Airbnb", "url": "https://example.invalid/feed.ics"}]
    result = await server.sync_property(prop)
    assert result[0]["added"] == result[0]["updated"] == result[0]["conflicts"] == 0
    assert await ctx["db"].bookings.count_documents({}) == 1


@pytest.mark.asyncio
async def test_owners_have_only_assigned_property_access(ctx):
    for role, own, other in [("owner", "p1", "p2"), ("other_owner", "p2", "p1")]:
        rows = (await ctx["client"].get("/api/properties", headers=auth(ctx, role))).json()
        assert [p["id"] for p in rows] == [ctx[own]]
        assert (await ctx["client"].get(f'/api/properties/{ctx[other]}', headers=auth(ctx, role))).status_code == 404
        for route in ["bookings", "cleaning", "calendar?month=" + date.today().isoformat()[:7] + "&"]:
            sep = "" if "?" in route else "?"
            response = await ctx["client"].get(f'/api/{route}{sep}property_id={ctx[other]}', headers=auth(ctx, role))
            assert response.status_code == 404, response.text


@pytest.mark.asyncio
async def test_cleaning_completion_reopen_and_other_pending_task(ctx):
    await ctx["db"].cleaning.update_one({"_id": ObjectId(ctx["cid"])}, {"$set": {"date": date.today().isoformat()}})
    async def needs():
        return (await ctx["client"].get(f'/api/properties/{ctx["p1"]}', headers=auth(ctx))).json()["needs_cleaning"]
    assert await needs()
    response = await ctx["client"].post(f'/api/cleaning/{ctx["cid"]}/admin-action', headers=auth(ctx), json={"action": "complete", "note": "Synthetic approval"})
    assert response.status_code == 200, response.text
    assert not await needs()
    await ctx["db"].cleaning.insert_one({"property_id": ctx["p1"], "date": date.today().isoformat(), "status": "pending"})
    assert await needs()  # Do not hide a genuinely different pending cleaning.
    response = await ctx["client"].post(f'/api/cleaning/{ctx["cid"]}/admin-action', headers=auth(ctx), json={"action": "reopen", "note": "Synthetic rework"})
    assert response.status_code == 200
    assert await needs()


@pytest.mark.parametrize("format", ["JPEG", "PNG", "WEBP", "AVIF", "HEIF", "BMP", "TIFF", "GIF"])
def test_common_photo_formats_convert_to_metadata_free_jpeg(format):
    original = Image.new("RGB", (24, 16), "blue")
    stream = io.BytesIO()
    original.save(stream, format)
    converted = normalise_photo(stream.getvalue())
    with Image.open(io.BytesIO(converted)) as result:
        assert result.format == "JPEG"
        assert result.size == (24, 16)
        assert not result.getexif()


def test_large_small_file_is_resized_not_rejected():
    stream = io.BytesIO()
    Image.new("RGB", (6000, 4000), "blue").save(stream, "JPEG")  # 24 MP, under 1 MB.
    assert len(stream.getvalue()) < 1024 * 1024
    with Image.open(io.BytesIO(normalise_photo(stream.getvalue()))) as result:
        assert result.size == (2400, 1600)


def test_rotation_and_transparency_are_preserved_without_metadata():
    stream = io.BytesIO()
    image = Image.new("RGB", (20, 10), "blue")
    exif = Image.Exif(); exif[274] = 6
    image.save(stream, "JPEG", exif=exif)
    with Image.open(io.BytesIO(normalise_photo(stream.getvalue()))) as result:
        assert result.size == (10, 20)
        assert not result.getexif()
    stream = io.BytesIO()
    Image.new("RGBA", (10, 10), (0, 0, 0, 0)).save(stream, "PNG")
    with Image.open(io.BytesIO(normalise_photo(stream.getvalue()))) as result:
        assert min(result.getpixel((0, 0))) > 250
