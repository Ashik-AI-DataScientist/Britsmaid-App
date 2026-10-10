"""Iteration 3 - Sync status, Payouts, Owner invite phone, Reset password, Google session."""
import os, uuid, requests, pytest
from datetime import date

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://britsmaid-revshare.preview.emergentagent.com").rstrip("/")


# ---------------- Sync status + manual run (admin only)
class TestSync:
    def test_sync_status_admin(self, admin_s):
        r = admin_s.get(f"{BASE}/api/sync/status")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("interval_minutes") == 60
        # last_run / next_run only if an auto run has happened — background loop runs at startup so should exist
        assert "last_run" in d, f"last_run missing: {d}"
        assert "next_run" in d, f"next_run missing: {d}"

    def test_sync_status_forbidden(self, owner_s, cleaner_s):
        assert owner_s.get(f"{BASE}/api/sync/status").status_code == 403
        assert cleaner_s.get(f"{BASE}/api/sync/status").status_code == 403

    def test_sync_run_admin(self, admin_s):
        r = admin_s.post(f"{BASE}/api/sync/run")
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("properties", "added", "errors"):
            assert k in d, f"missing key {k}: {d}"

    def test_sync_run_forbidden(self, owner_s, cleaner_s):
        assert owner_s.post(f"{BASE}/api/sync/run").status_code == 403
        assert cleaner_s.post(f"{BASE}/api/sync/run").status_code == 403


# ---------------- Payouts
class TestPayouts:
    @pytest.fixture
    def villa_azure_id(self, admin_s):
        props = admin_s.get(f"{BASE}/api/properties").json()
        azure = next((p for p in props if p["name"] == "Villa Azure"), None)
        assert azure, "Villa Azure must exist"
        return azure["id"]

    @pytest.fixture
    def other_villa_id(self, admin_s):
        props = admin_s.get(f"{BASE}/api/properties").json()
        other = next((p for p in props if p["name"] != "Villa Azure"), None)
        assert other, "Need a second villa"
        return other["id"]

    def _payout_payload(self, pid, month=None):
        return {
            "property_id": pid,
            "month": month or "2025-01",
            "amount": 12345,
            "paid_on": "2025-02-05",
            "method": "UPI",
            "reference": "TEST_REF_" + uuid.uuid4().hex[:6],
            "notes": "TEST payout",
        }

    def test_create_payout_receipt_number_and_duplicate(self, admin_s, villa_azure_id):
        month = "2025-03"
        # cleanup existing
        existing = admin_s.get(f"{BASE}/api/payouts", params={"property_id": villa_azure_id}).json()
        for p in existing:
            if p.get("month") == month:
                admin_s.delete(f"{BASE}/api/payouts/{p['id']}")

        r = admin_s.post(f"{BASE}/api/payouts", json=self._payout_payload(villa_azure_id, month))
        assert r.status_code == 200, r.text
        pay = r.json()
        pid = pay["id"]
        try:
            # receipt format BM-PAY-YYYY-NNNN
            import re
            assert re.match(r"BM-PAY-\d{4}-\d{4}$", pay["receipt_number"]), pay["receipt_number"]
            assert pay["method"] == "UPI"
            # duplicate same property+month -> 409
            r2 = admin_s.post(f"{BASE}/api/payouts", json=self._payout_payload(villa_azure_id, month))
            assert r2.status_code == 409, r2.text
        finally:
            admin_s.delete(f"{BASE}/api/payouts/{pid}")

    def test_owner_sees_own_payout_only(self, admin_s, owner_s, villa_azure_id, other_villa_id):
        month = "2025-04"
        # create payout on OTHER villa (owner should NOT see it)
        r_other = admin_s.post(f"{BASE}/api/payouts", json=self._payout_payload(other_villa_id, month))
        assert r_other.status_code in (200, 409)
        other_id = r_other.json().get("id") if r_other.status_code == 200 else None
        # create payout for owner's own villa
        r_own = admin_s.post(f"{BASE}/api/payouts", json=self._payout_payload(villa_azure_id, month))
        assert r_own.status_code in (200, 409)
        own_id = r_own.json().get("id") if r_own.status_code == 200 else None
        try:
            lst = owner_s.get(f"{BASE}/api/payouts").json()
            villa_ids = {p["property_id"] for p in lst}
            assert other_villa_id not in villa_ids
            # querying another villa explicitly -> 404
            r404 = owner_s.get(f"{BASE}/api/payouts", params={"property_id": other_villa_id})
            assert r404.status_code == 404
            # querying own villa -> 200 and contains record
            rok = owner_s.get(f"{BASE}/api/payouts", params={"property_id": villa_azure_id})
            assert rok.status_code == 200
        finally:
            if other_id:
                admin_s.delete(f"{BASE}/api/payouts/{other_id}")
            if own_id:
                admin_s.delete(f"{BASE}/api/payouts/{own_id}")

    def test_delete_admin_only(self, admin_s, owner_s, villa_azure_id):
        month = "2025-05"
        r = admin_s.post(f"{BASE}/api/payouts", json=self._payout_payload(villa_azure_id, month))
        pid = r.json().get("id") if r.status_code == 200 else None
        if not pid:
            pytest.skip("Could not create payout")
        try:
            # owner cannot delete
            d_owner = owner_s.delete(f"{BASE}/api/payouts/{pid}")
            assert d_owner.status_code == 403
        finally:
            admin_s.delete(f"{BASE}/api/payouts/{pid}")

    def test_settlement_includes_payout_field(self, admin_s, villa_azure_id):
        month = "2025-06"
        # cleanup
        for p in admin_s.get(f"{BASE}/api/payouts", params={"property_id": villa_azure_id}).json():
            if p.get("month") == month:
                admin_s.delete(f"{BASE}/api/payouts/{p['id']}")
        # settlement before payout -> null
        r = admin_s.get(f"{BASE}/api/reports/settlement", params={"property_id": villa_azure_id, "month": month})
        assert r.status_code == 200
        s = r.json()
        assert "payout" in s and s["payout"] is None

        rp = admin_s.post(f"{BASE}/api/payouts", json=self._payout_payload(villa_azure_id, month))
        pid = rp.json().get("id") if rp.status_code == 200 else None
        try:
            r2 = admin_s.get(f"{BASE}/api/reports/settlement", params={"property_id": villa_azure_id, "month": month})
            s2 = r2.json()
            assert s2["payout"] is not None
            assert s2["payout"]["month"] == month
            assert s2["payout"]["method"] == "UPI"
        finally:
            if pid:
                admin_s.delete(f"{BASE}/api/payouts/{pid}")

    def test_owner_dashboard_month_paid(self, admin_s, owner_s, villa_azure_id):
        # current-month payout -> month_paid=True on owner dashboard villa card
        month = date.today().strftime("%Y-%m")
        existing = admin_s.get(f"{BASE}/api/payouts", params={"property_id": villa_azure_id}).json()
        existing_id = next((p["id"] for p in existing if p.get("month") == month), None)
        pid = existing_id
        if not existing_id:
            r = admin_s.post(f"{BASE}/api/payouts", json=self._payout_payload(villa_azure_id, month))
            assert r.status_code == 200, r.text
            pid = r.json()["id"]
        try:
            d = owner_s.get(f"{BASE}/api/owner/dashboard").json()
            villa = next((v for v in d["villas"] if v["id"] == villa_azure_id), None)
            assert villa is not None
            assert "month_paid" in villa
            assert villa["month_paid"] is True
        finally:
            if pid and not existing_id:
                admin_s.delete(f"{BASE}/api/payouts/{pid}")


# ---------------- Users: phone + reset-password
class TestUserInvite:
    def test_create_user_with_phone(self, admin_s):
        email = f"TEST_phone_{uuid.uuid4().hex[:6]}@test.com"
        r = admin_s.post(f"{BASE}/api/users", json={
            "name": "TEST Phone", "email": email, "password": "abc12345",
            "role": "cleaner", "phone": "+91 98765 43210"
        })
        assert r.status_code == 200, r.text
        uid = r.json()["id"]
        assert r.json().get("phone") == "+91 98765 43210"
        try:
            lst = admin_s.get(f"{BASE}/api/users").json()
            u = next((x for x in lst if x["id"] == uid), None)
            assert u and u.get("phone") == "+91 98765 43210"
        finally:
            admin_s.delete(f"{BASE}/api/users/{uid}")

    def test_reset_password_admin_only(self, admin_s, cleaner_s):
        # create a fresh user (never touch seeded accounts)
        email = f"TEST_reset_{uuid.uuid4().hex[:6]}@test.com"
        r = admin_s.post(f"{BASE}/api/users", json={
            "name": "TEST Reset", "email": email, "password": "orig12345", "role": "cleaner"
        })
        uid = r.json()["id"]
        try:
            # cleaner cannot reset
            r_forb = cleaner_s.post(f"{BASE}/api/users/{uid}/reset-password")
            assert r_forb.status_code == 403
            # admin can reset
            r_ok = admin_s.post(f"{BASE}/api/users/{uid}/reset-password")
            assert r_ok.status_code == 200, r_ok.text
            data = r_ok.json()
            assert "temp_password" in data
            temp = data["temp_password"]
            assert temp.startswith("BM-") and len(temp) >= 10
            # old password no longer works, new one does
            r_login_old = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": "orig12345"})
            assert r_login_old.status_code == 401
            r_login_new = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": temp})
            assert r_login_new.status_code == 200
        finally:
            admin_s.delete(f"{BASE}/api/users/{uid}")


# ---------------- Google session
class TestGoogleSession:
    def test_invalid_session_id_401(self):
        r = requests.post(f"{BASE}/api/auth/session", json={"session_id": "definitely-not-a-real-session-" + uuid.uuid4().hex})
        assert r.status_code == 401, r.text

    def test_existing_jwt_still_works(self, admin_s):
        # verify prior JWT login path still works
        r = admin_s.get(f"{BASE}/api/auth/me")
        assert r.status_code == 200
        assert r.json()["role"] == "admin"
