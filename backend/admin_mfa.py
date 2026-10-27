"""Authenticator MFA without an external identity service."""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote
from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


class MFAInput(BaseModel):
    password: str = Field(max_length=200)
    code: str = Field(default="", max_length=40)


class AdminMFA:
    def __init__(self, db, key, verify_password):
        self.db, self.verify_password = db, verify_password
        self.box = Fernet(base64.urlsafe_b64encode(hashlib.sha256((key + ":admin-mfa").encode()).digest()))

    @staticmethod
    def code(secret, counter):
        key = base64.b32decode(secret + "=" * ((8 - len(secret) % 8) % 8))
        digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
        offset = digest[-1] & 15
        return str((struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7fffffff) % 1000000).zfill(6)

    def counter(self, encrypted, code):
        secret = self.box.decrypt(encrypted.encode()).decode()
        now = int(time.time()) // 30
        for candidate in (now - 1, now, now + 1):
            if hmac.compare_digest(self.code(secret, candidate), code):
                return candidate
        return None

    async def verify(self, user, code):
        if not user.get("mfa_secret"):
            return True
        recovery = hashlib.sha256(code.strip().encode()).hexdigest()
        if recovery in user.get("mfa_recovery_hashes", []):
            result = await self.db.users.update_one({"_id": user["_id"], "mfa_recovery_hashes": recovery},
                {"$pull": {"mfa_recovery_hashes": recovery}})
            return bool(result.modified_count)
        counter = self.counter(user["mfa_secret"], code.strip())
        if counter is None:
            return False
        result = await self.db.users.update_one({"_id": user["_id"], "$or": [
            {"mfa_last_counter": {"$lt": counter}}, {"mfa_last_counter": {"$exists": False}}]}, {"$set": {"mfa_last_counter": counter}})
        return bool(result.modified_count)

    def register(self, api, admin_user, issue_token):
        @api.get("/auth/mfa")
        async def status(user=Depends(admin_user)):
            return {"enabled": bool(user.get("mfa_secret")), "recovery_codes_remaining": len(user.get("mfa_recovery_hashes", []))}

        @api.post("/auth/mfa/setup")
        async def setup(body: MFAInput, user=Depends(admin_user)):
            if not self.verify_password(body.password, user["password_hash"]):
                raise HTTPException(403, "Check your password")
            if user.get("mfa_secret"):
                raise HTTPException(409, "Authenticator protection is already enabled")
            secret = base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")
            await self.db.users.update_one({"_id": user["_id"]}, {"$set": {
                "mfa_pending": self.box.encrypt(secret.encode()).decode(), "mfa_pending_until": time.time() + 600}})
            return {"setup_key": secret, "otpauth_uri": f"otpauth://totp/{quote('Britsmaid:' + user['email'])}?secret={secret}&issuer=Britsmaid"}

        @api.post("/auth/mfa/confirm")
        async def confirm(body: MFAInput, request: Request, user=Depends(admin_user)):
            if not self.verify_password(body.password, user["password_hash"]):
                raise HTTPException(403, "Check your password")
            pending = user.get("mfa_pending")
            counter = self.counter(pending, body.code.strip()) if pending and user.get("mfa_pending_until", 0) > time.time() else None
            if counter is None:
                raise HTTPException(422, "Setup expired or code incorrect. Try again.")
            recovery = [secrets.token_hex(8) for _ in range(8)]
            result = await self.db.users.update_one({"_id": user["_id"], "mfa_pending": pending, "mfa_secret": {"$exists": False}},
                {"$set": {"mfa_secret": pending, "mfa_last_counter": counter,
                    "mfa_recovery_hashes": [hashlib.sha256(item.encode()).hexdigest() for item in recovery]},
                    "$unset": {"mfa_pending": "", "mfa_pending_until": ""}, "$inc": {"session_version": 1}})
            if not result.modified_count:
                raise HTTPException(409, "Setup changed; refresh and try again")
            updated = await self.db.users.find_one({"_id": user["_id"]})
            token = issue_token(updated)
            data = {"enabled": True, "recovery_codes": recovery}
            if request.headers.get("authorization"):
                data["access_token"] = token
                return data
            response = JSONResponse(data)
            response.set_cookie("bm_session", token, max_age=7 * 86400, path="/api", secure=True, httponly=True, samesite="strict")
            return response

        @api.post("/auth/mfa/disable")
        async def disable(body: MFAInput, user=Depends(admin_user)):
            if not self.verify_password(body.password, user["password_hash"]) or not await self.verify(user, body.code):
                raise HTTPException(403, "Check your password and authenticator/recovery code")
            await self.db.users.update_one({"_id": user["_id"]}, {"$unset": {
                "mfa_secret": "", "mfa_pending": "", "mfa_pending_until": "", "mfa_recovery_hashes": "", "mfa_last_counter": ""}, "$inc": {"session_version": 1}})
            return {"enabled": False, "sign_in_again": True}
