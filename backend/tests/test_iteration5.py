"""Iteration 5: Bug-fix verification for 'Unmatched route on every tab in Expo Go'.
Quick backend regression: admin auth login + /api/dashboard returns data,
plus login for cleaner and owner (used by deep-route frontend checks)."""
import requests, os

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://britsmaid-revshare.preview.emergentagent.com").rstrip("/")


# ---------- Auth regression ----------
class TestAuthLogin:
    def test_admin_login(self):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": "admin@britsmaid.com", "password": "Britsmaid@2026"}, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["user"]["role"] == "admin"
        assert "access_token" in data

    def test_cleaner_login(self):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": "cleaner@britsmaid.com", "password": "Cleaner@2026"}, timeout=20)
        assert r.status_code == 200, r.text
        assert r.json()["user"]["role"] == "cleaner"

    def test_owner_login(self):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": "owner@britsmaid.com", "password": "Owner@2026"}, timeout=20)
        assert r.status_code == 200, r.text
        assert r.json()["user"]["role"] == "owner"


# ---------- Dashboard regression ----------
class TestDashboard:
    def test_admin_dashboard_returns_data(self, admin_s):
        r = admin_s.get(f"{BASE_URL}/api/dashboard", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, dict) and len(data) > 0

    def test_auth_me(self, admin_s):
        r = admin_s.get(f"{BASE_URL}/api/auth/me", timeout=20)
        assert r.status_code == 200
        assert r.json()["role"] == "admin"

    def test_properties_list(self, admin_s):
        r = admin_s.get(f"{BASE_URL}/api/properties", timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_unauthenticated_dashboard_rejected(self):
        r = requests.get(f"{BASE_URL}/api/dashboard", timeout=20)
        assert r.status_code in (401, 403)
