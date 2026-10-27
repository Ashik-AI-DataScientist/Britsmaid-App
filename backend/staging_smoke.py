"""Container integration check. Refuses to run against a non-staging server."""
import io
import json
import os
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import quote
from PIL import Image

ORIGIN = "http://127.0.0.1:10000"


def call(path, method="GET", body=None, token=None, expected=200, raw=None, content_type=None):
    headers = {}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = raw
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    elif content_type:
        headers["Content-Type"] = content_type
    try:
        response = urlopen(Request(ORIGIN + path, data=data, headers=headers, method=method), timeout=30)
        status, payload = response.status, response.read()
    except HTTPError as exc:
        status, payload = exc.code, exc.read()
    if status != expected:
        raise RuntimeError(f"Staging check failed: {method} {path.split('?')[0]} returned {status}, expected {expected}")
    try:
        return json.loads(payload)
    except (ValueError, UnicodeDecodeError):
        return payload


def main():
    if os.getenv("APP_ENV") != "staging" or os.getenv("DB_NAME") != "britsmaid_staging":
        raise RuntimeError("This smoke script is for the isolated staging container only")
    if call("/healthz").get("mode") != "staging":
        raise RuntimeError("The target is not a staging service")
    tokens = {}
    for role in ("ADMIN", "OWNER", "CLEANER", "SUPERVISOR"):
        tokens[role] = call("/api/auth/login", "POST", {"email": os.environ[role + "_EMAIL"], "password": os.environ[role + "_PASSWORD"]})["access_token"]
    admin = tokens["ADMIN"]
    first = call("/api/properties", "POST", {"name": "SYNTHETIC staging villa", "rooms": ["Room"]}, admin)
    second = call("/api/properties", "POST", {"name": "SYNTHETIC other villa", "rooms": ["Room"]}, admin)
    users = call("/api/users", token=admin)
    for role in ("owner", "cleaner", "supervisor"):
        member = next(row for row in users if row["email"] == os.environ[role.upper() + "_EMAIL"])
        call("/api/users/" + member["id"], "PUT", {"property_ids": [first["id"]]}, admin)
        assert [row["id"] for row in call("/api/properties", token=tokens[role.upper()])] == [first["id"]]
        call("/api/properties/" + second["id"], token=tokens[role.upper()], expected=404)
    call("/api/bookings", token=tokens["CLEANER"], expected=403)
    call("/api/users", token=tokens["SUPERVISOR"], expected=403)
    image = io.BytesIO()
    Image.new("RGB", (16, 16), "teal").save(image, "PNG")
    boundary = "BritsmaidSyntheticBoundary"
    multipart = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"sample.png\"\r\nContent-Type: image/png\r\n\r\n".encode()
        + image.getvalue() + f"\r\n--{boundary}--\r\n".encode())
    media = call("/api/upload", "POST", token=admin, raw=multipart, content_type="multipart/form-data; boundary=" + boundary)
    call("/api/properties/" + first["id"], "PUT", {"name": first["name"], "rooms": ["Room"], "cover_media_id": media["id"]}, admin)
    ticket = call("/api/files/" + media["id"] + "/ticket", "POST", {}, tokens["OWNER"])["ticket"]
    content = call("/api/files/" + media["id"] + "?ticket=" + quote(ticket))
    assert content.startswith(b"\xff\xd8")
    assert call("/api/system/photo-retention", token=admin)["enabled"] is False
    call("/api/system/readiness", token=tokens["OWNER"], expected=403)
    print("Staging integration passed: four roles, property isolation, private upload/cover/ticket and cleanup disabled.")


if __name__ == "__main__":
    main()
