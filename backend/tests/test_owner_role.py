"""Owner role scoping + admin owner-user management + cleaner forbidden paths."""
import os, uuid, requests, pytest
from datetime import date

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://britsmaid-revshare.preview.emergentagent.com").rstrip("/")


# ---------------- Owner scoping (owner@britsmaid.com → Villa Azure only)
class TestOwnerScoping:
    def test_me_owner(self, owner_s):
        r = owner_s.get(f"{BASE}/api/auth/me")
        assert r.status_code == 200
        d = r.json()
        assert d["role"] == "owner"
        assert isinstance(d.get("property_ids"), list) and len(d["property_ids"]) >= 1

    def test_properties_list_scoped(self, owner_s, admin_s):
        all_props = admin_s.get(f"{BASE}/api/properties").json()
        owner_me = owner_s.get(f"{BASE}/api/auth/me").json()
        allowed_ids = set(owner_me["property_ids"])
        own = owner_s.get(f"{BASE}/api/properties").json()
        own_ids = {p["id"] for p in own}
        assert own_ids == allowed_ids, f"owner must only see its villas: got {own_ids}, allowed {allowed_ids}"
        # Should NOT include properties outside its allowed set
        other = next((p["id"] for p in all_props if p["id"] not in allowed_ids), None)
        assert other, "need at least one other villa to test"
        r = owner_s.get(f"{BASE}/api/properties/{other}")
        assert r.status_code == 404

    def test_settlement_other_villa_404(self, owner_s, admin_s):
        all_props = admin_s.get(f"{BASE}/api/properties").json()
        owner_me = owner_s.get(f"{BASE}/api/auth/me").json()
        allowed = set(owner_me["property_ids"])
        other = next((p["id"] for p in all_props if p["id"] not in allowed), None)
        assert other
        m = date.today().strftime("%Y-%m")
        r = owner_s.get(f"{BASE}/api/reports/settlement", params={"property_id": other, "month": m})
        assert r.status_code == 404

    def test_settlement_own_villa_ok(self, owner_s):
        owner_me = owner_s.get(f"{BASE}/api/auth/me").json()
        pid = owner_me["property_ids"][0]
        m = date.today().strftime("%Y-%m")
        r = owner_s.get(f"{BASE}/api/reports/settlement", params={"property_id": pid, "month": m})
        assert r.status_code == 200
        assert r.json()["property_id"] == pid

    def test_bookings_scoped(self, owner_s):
        owner_me = owner_s.get(f"{BASE}/api/auth/me").json()
        allowed = set(owner_me["property_ids"])
        bs = owner_s.get(f"{BASE}/api/bookings").json()
        for b in bs:
            assert b["property_id"] in allowed

    def test_calendar_scoped(self, owner_s):
        owner_me = owner_s.get(f"{BASE}/api/auth/me").json()
        allowed = set(owner_me["property_ids"])
        m = date.today().strftime("%Y-%m")
        r = owner_s.get(f"{BASE}/api/calendar", params={"month": m})
        assert r.status_code == 200
        d = r.json()
        for b in d["bookings"]:
            assert b["property_id"] in allowed
        for c in d["cleanings"]:
            assert c["property_id"] in allowed

    def test_cleaning_scoped(self, owner_s):
        owner_me = owner_s.get(f"{BASE}/api/auth/me").json()
        allowed = set(owner_me["property_ids"])
        cs = owner_s.get(f"{BASE}/api/cleaning").json()
        for c in cs:
            assert c["property_id"] in allowed

    def test_owner_reports_scoped(self, owner_s):
        owner_me = owner_s.get(f"{BASE}/api/auth/me").json()
        allowed = set(owner_me["property_ids"])
        rs = owner_s.get(f"{BASE}/api/owner-reports").json()
        for r in rs:
            assert r["property_id"] in allowed

    def test_owner_dashboard_ok_and_scoped(self, owner_s):
        owner_me = owner_s.get(f"{BASE}/api/auth/me").json()
        allowed = set(owner_me["property_ids"])
        r = owner_s.get(f"{BASE}/api/owner/dashboard")
        assert r.status_code == 200
        d = r.json()
        assert "villas" in d and "total_payout" in d
        got = {v["id"] for v in d["villas"]}
        assert got == allowed

    # Owner forbidden endpoints
    def test_owner_403_admin_dashboard(self, owner_s):
        assert owner_s.get(f"{BASE}/api/dashboard").status_code == 403

    def test_owner_403_invoices(self, owner_s):
        assert owner_s.get(f"{BASE}/api/invoices").status_code == 403

    def test_owner_403_ota_report(self, owner_s):
        m = date.today().strftime("%Y-%m")
        assert owner_s.get(f"{BASE}/api/reports/ota", params={"month": m}).status_code == 403

    def test_owner_403_upload(self, owner_s):
        import io
        hdrs = {"Authorization": owner_s.headers["Authorization"]}
        r = requests.post(f"{BASE}/api/upload",
                          files={"file": ("t.jpg", io.BytesIO(b"\xff\xd8xx"), "image/jpeg")}, headers=hdrs, timeout=30)
        assert r.status_code == 403

    def test_owner_403_create_property(self, owner_s):
        r = owner_s.post(f"{BASE}/api/properties", json={"name": "TEST_OwnerCantCreate"})
        assert r.status_code == 403

    def test_owner_403_create_booking(self, owner_s):
        owner_me = owner_s.get(f"{BASE}/api/auth/me").json()
        pid = owner_me["property_ids"][0]
        p = {"property_id": pid, "guest_name": "x", "ota": "Direct",
             "check_in": "2030-01-01", "check_out": "2030-01-02", "amount": 1000}
        assert owner_s.post(f"{BASE}/api/bookings", json=p).status_code == 403

    def test_owner_403_cleaning_media(self, owner_s, admin_s):
        cs = admin_s.get(f"{BASE}/api/cleaning").json()
        session = next((c for c in cs if c.get("status") != "completed"), None)
        if not session:
            pytest.skip("no open cleaning session")
        r = owner_s.post(f"{BASE}/api/cleaning/{session['id']}/rooms/0/media",
                         json={"phase": "before", "media_id": "x"})
        assert r.status_code == 403

    def test_owner_403_complete_cleaning(self, owner_s, admin_s):
        cs = admin_s.get(f"{BASE}/api/cleaning").json()
        session = next((c for c in cs if c.get("status") != "completed"), None)
        if not session:
            pytest.skip("no open cleaning session")
        r = owner_s.put(f"{BASE}/api/cleaning/{session['id']}", json={"status": "completed"})
        assert r.status_code == 403


# ---------------- Cleaner forbidden on finance endpoints
class TestCleanerForbidden:
    def test_cleaner_403_settlement(self, cleaner_s, admin_s):
        pid = admin_s.get(f"{BASE}/api/properties").json()[0]["id"]
        m = date.today().strftime("%Y-%m")
        assert cleaner_s.get(f"{BASE}/api/reports/settlement",
                             params={"property_id": pid, "month": m}).status_code == 403

    def test_cleaner_403_owner_reports(self, cleaner_s):
        assert cleaner_s.get(f"{BASE}/api/owner-reports").status_code == 403

    def test_cleaner_403_owner_dashboard(self, cleaner_s):
        assert cleaner_s.get(f"{BASE}/api/owner/dashboard").status_code == 403

    def test_cleaner_403_expenses(self, cleaner_s, admin_s):
        pid = admin_s.get(f"{BASE}/api/properties").json()[0]["id"]
        r = cleaner_s.get(f"{BASE}/api/expenses", params={"property_id": pid})
        assert r.status_code == 403

    def test_cleaner_still_can_list_cleaning(self, cleaner_s):
        r = cleaner_s.get(f"{BASE}/api/cleaning")
        assert r.status_code == 200


# ---------------- Admin manages owner users
class TestAdminOwnerUserMgmt:
    def test_create_owner_requires_property_ids(self, admin_s):
        email = f"TEST_owner_{uuid.uuid4().hex[:8]}@test.com"
        r = admin_s.post(f"{BASE}/api/users", json={
            "name": "TEST_Owner", "email": email, "password": "abc12345",
            "role": "owner", "property_ids": []
        })
        assert r.status_code == 400

    def test_create_owner_rejects_nonexistent_property(self, admin_s):
        email = f"TEST_owner_{uuid.uuid4().hex[:8]}@test.com"
        # Valid ObjectId format but non-existent
        r = admin_s.post(f"{BASE}/api/users", json={
            "name": "TEST", "email": email, "password": "abc12345",
            "role": "owner", "property_ids": ["000000000000000000000000"]
        })
        assert r.status_code == 400

    def test_create_owner_reject_invalid_oid(self, admin_s):
        email = f"TEST_owner_{uuid.uuid4().hex[:8]}@test.com"
        r = admin_s.post(f"{BASE}/api/users", json={
            "name": "TEST", "email": email, "password": "abc12345",
            "role": "owner", "property_ids": ["not-a-valid-oid"]
        })
        assert r.status_code == 422

    def test_create_owner_full_flow_and_scoped_login(self, admin_s):
        props = admin_s.get(f"{BASE}/api/properties").json()
        assert len(props) >= 2
        pid1, pid2 = props[0]["id"], props[1]["id"]
        email = f"TEST_owner_{uuid.uuid4().hex[:8]}@test.com"
        pw = "ownerpass123"
        # Create owner with pid1
        r = admin_s.post(f"{BASE}/api/users", json={
            "name": "TEST_Owner", "email": email, "password": pw,
            "role": "owner", "property_ids": [pid1]
        })
        assert r.status_code == 200, r.text
        uid = r.json()["id"]
        assert r.json()["role"] == "owner"
        assert r.json()["property_ids"] == [pid1]
        try:
            # New owner can login and sees only pid1
            tok = requests.post(f"{BASE}/api/auth/login",
                                json={"email": email, "password": pw}).json()["access_token"]
            s = requests.Session()
            s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
            seen = s.get(f"{BASE}/api/properties").json()
            assert {p["id"] for p in seen} == {pid1}

            # Reassign to pid2 via PUT
            u = admin_s.put(f"{BASE}/api/users/{uid}", json={"property_ids": [pid2]})
            assert u.status_code == 200
            assert u.json()["property_ids"] == [pid2]

            seen2 = s.get(f"{BASE}/api/properties").json()
            assert {p["id"] for p in seen2} == {pid2}

            # Empty reassignment rejected
            bad = admin_s.put(f"{BASE}/api/users/{uid}", json={"property_ids": []})
            assert bad.status_code == 400
        finally:
            admin_s.delete(f"{BASE}/api/users/{uid}")

    def test_update_cleaner_with_property_ids_rejected(self, admin_s):
        import uuid as uu
        email = f"TEST_cl_{uu.uuid4().hex[:8]}@test.com"
        r = admin_s.post(f"{BASE}/api/users", json={
            "name": "TEST_Cl", "email": email, "password": "abc12345", "role": "cleaner"
        })
        uid = r.json()["id"]
        try:
            props = admin_s.get(f"{BASE}/api/properties").json()
            bad = admin_s.put(f"{BASE}/api/users/{uid}", json={"property_ids": [props[0]["id"]]})
            assert bad.status_code == 400
        finally:
            admin_s.delete(f"{BASE}/api/users/{uid}")
