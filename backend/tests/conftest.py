import pytest, os, requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://britsmaid-revshare.preview.emergentagent.com").rstrip("/")


@pytest.fixture(scope="session")
def base_url():
    return BASE_URL


def _login(email, pw):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw}, timeout=20)
    assert r.status_code == 200, f"Login failed {email}: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def admin_token():
    return _login("admin@britsmaid.com", "Britsmaid@2026")


@pytest.fixture(scope="session")
def cleaner_token():
    return _login("cleaner@britsmaid.com", "Cleaner@2026")


@pytest.fixture
def admin_s(admin_token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"})
    return s


@pytest.fixture
def cleaner_s(cleaner_token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {cleaner_token}", "Content-Type": "application/json"})
    return s
