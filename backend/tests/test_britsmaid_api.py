"""Britsmaid backend API tests - comprehensive critical path."""
import io, os, requests, pytest
from datetime import date, timedelta

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://britsmaid-revshare.preview.emergentagent.com").rstrip("/")


# ---------------- Auth
class TestAuth:
    def test_login_admin(self, admin_s):
        r = admin_s.get(f"{BASE}/api/auth/me")
        assert r.status_code == 200
        assert r.json()["role"] == "admin"

    def test_login_cleaner(self, cleaner_s):
        r = cleaner_s.get(f"{BASE}/api/auth/me")
        assert r.status_code == 200
        assert r.json()["role"] == "cleaner"

    def test_login_wrong_password(self):
        r = requests.post(f"{BASE}/api/auth/login", json={"email": "admin@britsmaid.com", "password": "bad"})
        assert r.status_code == 401

    def test_me_requires_token(self):
        assert requests.get(f"{BASE}/api/auth/me").status_code == 401

    def test_cleaner_cannot_dashboard(self, cleaner_s):
        assert cleaner_s.get(f"{BASE}/api/dashboard").status_code == 403

    def test_cleaner_cannot_list_invoices(self, cleaner_s):
        assert cleaner_s.get(f"{BASE}/api/invoices").status_code == 403


# ---------------- Properties
class TestProperties:
    def test_list(self, admin_s):
        r = admin_s.get(f"{BASE}/api/properties")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list) and len(data) >= 1
        p = data[0]
        for k in ("id", "name", "owner_share_percent", "electricity_mode", "occupied"):
            assert k in p

    def test_create_update_delete(self, admin_s):
        payload = {"name": "TEST_Villa", "location": "Goa", "owner_share_percent": 65, "electricity_mode": "split_half", "rooms": ["Living Room", "Bedroom 1"]}
        r = admin_s.post(f"{BASE}/api/properties", json=payload)
        assert r.status_code == 200
        pid = r.json()["id"]
        # verify persistence
        g = admin_s.get(f"{BASE}/api/properties/{pid}")
        assert g.status_code == 200 and g.json()["name"] == "TEST_Villa"
        # update
        payload["name"] = "TEST_Villa2"
        u = admin_s.put(f"{BASE}/api/properties/{pid}", json=payload)
        assert u.status_code == 200 and u.json()["name"] == "TEST_Villa2"
        # delete (soft)
        d = admin_s.delete(f"{BASE}/api/properties/{pid}")
        assert d.status_code == 200

    def test_ical_sync_no_feeds(self, admin_s):
        pid = admin_s.get(f"{BASE}/api/properties").json()[0]["id"]
        r = admin_s.post(f"{BASE}/api/properties/{pid}/ical-sync")
        assert r.status_code == 400

    def test_ical_sync_bad_url(self, admin_s):
        payload = {"name": "TEST_IcalVilla", "ical_feeds": [{"ota": "Airbnb", "url": "https://invalid.example.invalid/notfound.ics"}]}
        r = admin_s.post(f"{BASE}/api/properties", json=payload)
        pid = r.json()["id"]
        try:
            r2 = admin_s.post(f"{BASE}/api/properties/{pid}/ical-sync")
            assert r2.status_code == 200
            results = r2.json()["results"]
            assert len(results) == 1 and results[0]["ok"] is False
        finally:
            admin_s.delete(f"{BASE}/api/properties/{pid}")


# ---------------- Bookings
class TestBookings:
    @pytest.fixture
    def pid(self, admin_s):
        return admin_s.get(f"{BASE}/api/properties").json()[0]["id"]

    def test_overlap_409(self, admin_s, pid):
        t = date.today()
        p = {"property_id": pid, "guest_name": "TEST_Overlap", "ota": "Direct",
             "check_in": (t + timedelta(days=60)).isoformat(), "check_out": (t + timedelta(days=63)).isoformat(),
             "amount": 10000}
        r1 = admin_s.post(f"{BASE}/api/bookings", json=p)
        assert r1.status_code == 200, r1.text
        bid = r1.json()["id"]
        try:
            p2 = dict(p); p2["guest_name"] = "TEST_Overlap2"
            p2["check_in"] = (t + timedelta(days=61)).isoformat()
            r2 = admin_s.post(f"{BASE}/api/bookings", json=p2)
            assert r2.status_code == 409
        finally:
            admin_s.delete(f"{BASE}/api/bookings/{bid}")

    def test_booking_auto_cleaning(self, admin_s, pid):
        t = date.today()
        checkout = (t + timedelta(days=73)).isoformat()
        p = {"property_id": pid, "guest_name": "TEST_Clean", "ota": "Direct",
             "check_in": (t + timedelta(days=70)).isoformat(), "check_out": checkout, "amount": 10000}
        r = admin_s.post(f"{BASE}/api/bookings", json=p)
        bid = r.json()["id"]
        try:
            # cleaning session created on checkout
            cl = admin_s.get(f"{BASE}/api/cleaning").json()
            assert any(c for c in cl if c.get("date") == checkout), "cleaning session not auto-created"
        finally:
            admin_s.delete(f"{BASE}/api/bookings/{bid}")

    def test_calendar(self, admin_s):
        m = date.today().strftime("%Y-%m")
        r = admin_s.get(f"{BASE}/api/calendar", params={"month": m})
        assert r.status_code == 200
        d = r.json()
        assert "bookings" in d and "cleanings" in d


# ---------------- Cleaning
class TestCleaning:
    def test_upload_and_media_flow(self, admin_s):
        # upload
        fdata = {"file": ("t.jpg", io.BytesIO(b"\xff\xd8\xff\xe0JPEGx"), "image/jpeg")}
        # need to drop content-type header for multipart
        hdrs = {"Authorization": admin_s.headers["Authorization"]}
        r = requests.post(f"{BASE}/api/upload", files=fdata, headers=hdrs, timeout=60)
        if r.status_code == 402:
            pytest.skip("Storage credits exhausted")
        assert r.status_code == 200, r.text
        media_id = r.json()["id"]
        # list cleaning sessions
        cl = admin_s.get(f"{BASE}/api/cleaning").json()
        session = next((c for c in cl if c.get("status") != "completed" and c.get("rooms_total", 0) > 0), None)
        if not session:
            pytest.skip("No open cleaning session")
        cid = session["id"]
        # mark completed should fail - missing photos
        r_fail = admin_s.put(f"{BASE}/api/cleaning/{cid}", json={"status": "completed"})
        assert r_fail.status_code == 400

        # add before+after media to room 0
        for phase in ("before", "after"):
            r2 = admin_s.post(f"{BASE}/api/cleaning/{cid}/rooms/0/media", json={"phase": phase, "media_id": media_id})
            assert r2.status_code == 200
        # cannot complete yet (other rooms missing)
        rooms_total = session["rooms_total"]
        if rooms_total > 1:
            r3 = admin_s.put(f"{BASE}/api/cleaning/{cid}", json={"status": "completed"})
            assert r3.status_code == 400

    def test_file_requires_token(self, admin_s):
        fdata = {"file": ("t.jpg", io.BytesIO(b"\xff\xd8\xff\xe0JPEG"), "image/jpeg")}
        hdrs = {"Authorization": admin_s.headers["Authorization"]}
        r = requests.post(f"{BASE}/api/upload", files=fdata, headers=hdrs, timeout=60)
        if r.status_code == 402:
            pytest.skip("Storage credits exhausted")
        mid = r.json()["id"]
        # unauth
        r2 = requests.get(f"{BASE}/api/files/{mid}")
        assert r2.status_code == 401
        # with query token
        r3 = requests.get(f"{BASE}/api/files/{mid}", params={"token": admin_s.headers["Authorization"].split()[1]})
        assert r3.status_code == 200


# ---------------- Reports
class TestReports:
    def test_settlement(self, admin_s):
        pid = admin_s.get(f"{BASE}/api/properties").json()[0]["id"]
        m = date.today().strftime("%Y-%m")
        r = admin_s.get(f"{BASE}/api/reports/settlement", params={"property_id": pid, "month": m})
        assert r.status_code == 200
        s = r.json()
        for k in ("gross", "net_revenue", "owner_share", "owner_payout", "britsmaid_net", "trend", "by_ota", "bookings"):
            assert k in s
        assert len(s["trend"]) == 6
        # math: owner_share + bm_share should equal net (within rounding)
        assert abs((s["owner_share"] + s["britsmaid_share"]) - s["net_revenue"]) < 1

    def test_settlement_split_half(self, admin_s):
        # villa Azure is split_half
        props = admin_s.get(f"{BASE}/api/properties").json()
        azure = next((p for p in props if p["electricity_mode"] == "split_half"), None)
        if not azure:
            pytest.skip("No split_half property")
        m = date.today().strftime("%Y-%m")
        s = admin_s.get(f"{BASE}/api/reports/settlement", params={"property_id": azure["id"], "month": m}).json()
        if s["electricity_total"] > 0:
            assert abs(s["owner_electricity"] - s["electricity_total"] / 2) < 1
            assert abs(s["britsmaid_electricity"] - s["electricity_total"] / 2) < 1

    def test_ota_report(self, admin_s):
        m = date.today().strftime("%Y-%m")
        r = admin_s.get(f"{BASE}/api/reports/ota", params={"month": m})
        assert r.status_code == 200
        d = r.json()
        assert "rows" in d and "total_gross" in d


# ---------------- Invoices
class TestInvoices:
    def test_create_and_toggle(self, admin_s):
        payload = {"type": "guest", "bill_to_name": "TEST_Guest", "items": [{"description": "Stay", "qty": 2, "rate": 5000}],
                   "tax_percent": 18, "discount": 500, "issue_date": date.today().isoformat()}
        r = admin_s.post(f"{BASE}/api/invoices", json=payload)
        assert r.status_code == 200, r.text
        inv = r.json()
        iid = inv["id"]
        # BM-YYYY-NNNN
        assert inv["number"].startswith(f"BM-{date.today().year}-")
        # math: sub=10000, taxable=9500, tax=1710, total=11210
        assert inv["subtotal"] == 10000
        assert inv["tax_amount"] == 1710
        assert inv["total"] == 11210
        # toggle status
        s = admin_s.put(f"{BASE}/api/invoices/{iid}/status", json={"status": "paid"})
        assert s.status_code == 200 and s.json()["status"] == "paid"
        # delete
        d = admin_s.delete(f"{BASE}/api/invoices/{iid}")
        assert d.status_code == 200

    def test_create_empty_items_rejected(self, admin_s):
        payload = {"type": "guest", "bill_to_name": "TEST", "items": [], "issue_date": date.today().isoformat()}
        r = admin_s.post(f"{BASE}/api/invoices", json=payload)
        assert r.status_code == 400


# ---------------- Owner reports
class TestOwnerReports:
    def test_create_and_public(self, admin_s):
        pid = admin_s.get(f"{BASE}/api/properties").json()[0]["id"]
        m = date.today().strftime("%Y-%m")
        r = admin_s.post(f"{BASE}/api/owner-reports", json={"property_id": pid, "month": m, "title": "TEST_Report", "condition_notes": "Looks good"})
        assert r.status_code == 200
        rep = r.json()
        token = rep["share_token"]
        rid = rep["id"]
        try:
            # Public endpoint no auth
            pub = requests.get(f"{BASE}/api/public/reports/{token}")
            assert pub.status_code == 200
            assert "text/html" in pub.headers.get("Content-Type", "")
            assert "Owner Statement" in pub.text
        finally:
            admin_s.delete(f"{BASE}/api/owner-reports/{rid}")


# ---------------- Users
class TestUsers:
    def test_admin_create_and_deactivate_cleaner(self, admin_s):
        import uuid
        email = f"TEST_cleaner_{uuid.uuid4().hex[:8]}@test.com"
        r = admin_s.post(f"{BASE}/api/users", json={"name": "TEST", "email": email, "password": "abc12345", "role": "cleaner"})
        assert r.status_code == 200, r.text
        uid = r.json()["id"]
        # list contains it
        lst = admin_s.get(f"{BASE}/api/users").json()
        assert any(u["id"] == uid for u in lst)
        # deactivate
        d = admin_s.delete(f"{BASE}/api/users/{uid}")
        assert d.status_code == 200
        lst2 = admin_s.get(f"{BASE}/api/users").json()
        assert not any(u["id"] == uid for u in lst2)


# ---------------- Dashboard
class TestDashboard:
    def test_dashboard(self, admin_s):
        r = admin_s.get(f"{BASE}/api/dashboard")
        assert r.status_code == 200
        d = r.json()
        for k in ("month", "properties", "occupied_today", "month_gross", "arrivals", "departures", "pending_cleaning", "unpaid_invoices"):
            assert k in d
