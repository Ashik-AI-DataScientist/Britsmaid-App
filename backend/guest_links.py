"""Stable, booking-bound invitations. No plaintext invitation is retained."""
import base64
import hashlib
import secrets
from datetime import date, datetime, timedelta, timezone

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

INDIA_TZ = timezone(timedelta(hours=5, minutes=30))


def upload_cutoff(check_out):
    # Date-only stays: include the entire following calendar day in India.
    return datetime.combine(date.fromisoformat(check_out) + timedelta(days=2),
                            datetime.min.time(), INDIA_TZ).astimezone(timezone.utc).isoformat()


class StableGuestLinks:
    def __init__(self, db, secret):
        self.db = db
        self.box = Fernet(base64.urlsafe_b64encode(hashlib.sha256(
            (secret + ":guest-invitations:v1").encode()).digest()))

    async def get(self, bid, expiry, replace=False):
        key = "booking:" + bid
        current = await self.db.guest_links.find_one({"_id": key})
        if current and current.get("revoked") and not replace:
            raise HTTPException(409, "Upload link disabled. Use Create replacement link in admin options.")
        if replace or not current:
            token = secrets.token_urlsafe(32)
            record = {"_id": key, "booking_id": bid,
                      "token_hash": hashlib.sha256(token.encode()).hexdigest(),
                      "token_encrypted": self.box.encrypt((bid + ":" + token).encode()).decode(),
                      "expires_at": expiry, "revoked": False, "attempts": 0}
            if replace:
                # Explicit replacement only; ordinary sharing never revokes recipients.
                await self.db.guest_links.update_many({"booking_id": bid}, {"$set": {"revoked": True}})
                await self.db.guest_links.replace_one({"_id": key}, record, upsert=True)
                current = record
            else:
                try:
                    await self.db.guest_links.insert_one(record)
                    current = record
                except DuplicateKeyError:
                    current = await self.db.guest_links.find_one({"_id": key})
        if not current or current.get("revoked"):
            raise HTTPException(409, "Upload link changed. Refresh and retry.")
        try:
            payload = self.box.decrypt(current["token_encrypted"].encode()).decode()
            booking_id, token = payload.split(":", 1)
            if booking_id != bid or hashlib.sha256(token.encode()).hexdigest() != current["token_hash"]:
                raise ValueError("Invitation binding mismatch")
        except (InvalidToken, KeyError, ValueError, UnicodeError):
            raise HTTPException(503, "Cannot recover this invitation. Contact the administrator; no link was replaced.")
        await self.db.guest_links.update_one({"_id": key, "token_hash": current["token_hash"], "revoked": False},
                                            {"$set": {"expires_at": expiry}})
        return token
