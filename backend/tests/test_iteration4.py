"""Iteration 4 tests: add/delete properties w/ contacts, Ashik admin login, user role edit, password set."""
import pytest, requests, time, os

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://britsmaid-revshare.preview.emergentagent.com").rstrip("/")


# ---------- Ashik admin login ----------
class TestAshikLogin:
    def test_ashik_login_as_admin(self):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": "ashik.ma@britsmaid.in", "password": "Britsmaid2026@ashik"}, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["user"]["role"] == "admin"
        assert data["user"]["email"] == "ashik.ma@britsmaid.in"
        assert "access_token" in data


# ---------- Property CRUD w/ contacts ----------
@pytest.fixture
def new_property(admin_s):
    payload = {
        "name": "TEST_Villa_Contacts",
        "location": "Test Beach",
        "owner_name": "Test Owner",
        "owner_email": "testo@example.com",
        "owner_phone": "+91 90000 00001",
        "owner_alt_phone": "+91 90000 00002",
        "owner_address": "Line 1, Line 2",
        "contacts": [
            {"name": "Caretaker Raj", "role": "Caretaker", "phone": "+91 90000 11111",
             "alt_phone": "+91 90000 11112", "email": "raj@x.com", "notes": "Daily", "emergency": False},
            {"name": "Local Hospital", "role": "Emergency contact", "phone": "+91 90000 22222",
             "alt_phone": "", "email": "", "notes": "24x7", "emergency": True},
            {"name": "Co-owner Sita", "role": "Co-owner", "phone": "+91 90000 33333",
             "alt_phone": "", "email": "sita@x.com", "notes": "", "emergency": False},
        ],
        "owner_share_percent": 65,
        "electricity_mode": "owner",
        "base_rate": 7500,
        "rooms": ["Living Room", "Kitchen", "BR 1"],
        "cover_url": "",
    }
    r = admin_s.post(f"{BASE_URL}/api/properties", json=payload)
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    yield pid, payload
    admin_s.delete(f"{BASE_URL}/api/properties/{pid}")


class TestPropertyContacts:
    def test_create_persists_contacts_and_owner_fields(self, admin_s, new_property):
        pid, payload = new_property
        g = admin_s.get(f"{BASE_URL}/api/properties/{pid}")
        assert g.status_code == 200
        d = g.json()
        assert d["owner_alt_phone"] == payload["owner_alt_phone"]
        assert d["owner_address"] == payload["owner_address"]
        assert len(d["contacts"]) == 3
        emergency = [c for c in d["contacts"] if c.get("emergency")]
        assert len(emergency) == 1
        assert emergency[0]["name"] == "Local Hospital"
        roles = {c["role"] for c in d["contacts"]}
        assert {"Caretaker", "Co-owner", "Emergency contact"} <= roles

    def test_update_round_trip(self, admin_s, new_property):
        pid, payload = new_property
        payload["contacts"].append({"name": "Plumber Mani", "role": "Other", "phone": "+91 90000 44444",
                                    "alt_phone": "", "email": "", "notes": "", "emergency": False})
        payload["owner_address"] = "Updated Address"
        r = admin_s.put(f"{BASE_URL}/api/properties/{pid}", json=payload)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["owner_address"] == "Updated Address"
        assert len(d["contacts"]) == 4
        assert any(c["name"] == "Plumber Mani" for c in d["contacts"])

    def test_delete_removes_from_list(self, admin_s):
        payload = {"name": "TEST_Villa_Delete", "location": "X", "rooms": ["R1"], "contacts": []}
        r = admin_s.post(f"{BASE_URL}/api/properties", json=payload)
        pid = r.json()["id"]
        # confirm appears
        lst = admin_s.get(f"{BASE_URL}/api/properties").json()
        assert any(p["id"] == pid for p in lst)
        # delete
        d = admin_s.delete(f"{BASE_URL}/api/properties/{pid}")
        assert d.status_code == 200
        # confirm absent
        lst2 = admin_s.get(f"{BASE_URL}/api/properties").json()
        assert not any(p["id"] == pid for p in lst2)


# ---------- User role/password/name/phone updates ----------
@pytest.fixture
def test_user(admin_s):
    email = f"test_iter4_{int(time.time()*1000)}@example.com"
    r = admin_s.post(f"{BASE_URL}/api/users", json={
        "name": "TEST_Iter4", "email": email, "password": "Pass@1234", "role": "cleaner", "phone": "+91 90000 00000"
    })
    assert r.status_code == 200, r.text
    uid = r.json()["id"]
    yield uid, email
    admin_s.delete(f"{BASE_URL}/api/users/{uid}")


class TestUserUpdates:
    def test_role_switch_cleaner_to_admin_and_back(self, admin_s, test_user):
        uid, _ = test_user
        r = admin_s.put(f"{BASE_URL}/api/users/{uid}", json={"role": "admin"})
        assert r.status_code == 200, r.text
        assert r.json()["role"] == "admin"
        r2 = admin_s.put(f"{BASE_URL}/api/users/{uid}", json={"role": "cleaner"})
        assert r2.status_code == 200
        assert r2.json()["role"] == "cleaner"

    def test_promote_to_owner_requires_property_ids(self, admin_s, test_user):
        uid, _ = test_user
        r = admin_s.put(f"{BASE_URL}/api/users/{uid}", json={"role": "owner"})
        assert r.status_code == 400
        # Grab a real villa (seeded Villa Azure)
        props = admin_s.get(f"{BASE_URL}/api/properties").json()
        pid = next(p["id"] for p in props if p["name"] == "Villa Azure")
        r2 = admin_s.put(f"{BASE_URL}/api/users/{uid}", json={"role": "owner", "property_ids": [pid]})
        assert r2.status_code == 200, r2.text
        assert r2.json()["role"] == "owner"
        assert pid in r2.json()["property_ids"]

    def test_switch_away_from_owner_clears_property_ids(self, admin_s, test_user):
        uid, _ = test_user
        props = admin_s.get(f"{BASE_URL}/api/properties").json()
        pid = next(p["id"] for p in props if p["name"] == "Villa Azure")
        admin_s.put(f"{BASE_URL}/api/users/{uid}", json={"role": "owner", "property_ids": [pid]})
        r = admin_s.put(f"{BASE_URL}/api/users/{uid}", json={"role": "cleaner"})
        assert r.status_code == 200
        assert r.json()["role"] == "cleaner"
        assert r.json().get("property_ids", []) == []

    def test_password_set_logs_in(self, admin_s, test_user):
        uid, email = test_user
        r = admin_s.put(f"{BASE_URL}/api/users/{uid}", json={"password": "NewPass@999"})
        assert r.status_code == 200
        # old password rejected
        bad = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "Pass@1234"})
        assert bad.status_code == 401
        good = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "NewPass@999"})
        assert good.status_code == 200

    def test_name_and_phone_update(self, admin_s, test_user):
        uid, _ = test_user
        r = admin_s.put(f"{BASE_URL}/api/users/{uid}", json={"name": "TEST_RenamedIter4", "phone": "+91 11111 11111"})
        assert r.status_code == 200
        d = r.json()
        assert d["name"] == "TEST_RenamedIter4"
        assert d["phone"] == "+91 11111 11111"

    def test_admin_cannot_change_own_role(self, admin_s):
        me = admin_s.get(f"{BASE_URL}/api/auth/me").json()
        r = admin_s.put(f"{BASE_URL}/api/users/{me['id']}", json={"role": "cleaner"})
        assert r.status_code == 400
        # confirm still admin
        me2 = admin_s.get(f"{BASE_URL}/api/auth/me").json()
        assert me2["role"] == "admin"
