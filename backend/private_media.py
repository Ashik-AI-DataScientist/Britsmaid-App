"""Private S3-compatible ordinary media, with legacy reads and conservative quotas.

Guest documents deliberately use their own storage implementation and credentials.
"""
import hashlib
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from fastapi import HTTPException
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError


class PrivateMediaStore:
    def __init__(self, database, legacy, client=None):
        self.db, self.legacy = database, legacy
        self.bucket = os.environ["MEDIA_BUCKET"]
        self.prefix = os.getenv("MEDIA_PREFIX", "britsmaid/uploads/")
        if not re.fullmatch(r"britsmaid/(?:staging/)?uploads/", self.prefix):
            raise RuntimeError("Use a dedicated ordinary-media prefix")
        # Do not permit a configuration typo to silently remove free-tier safeguards.
        self.free_guard = os.getenv("FREE_TIER_GUARD", "true").lower() == "true"
        requested_budget = int(os.getenv("MEDIA_BUDGET_BYTES", str(3 * 1024**3)))
        free_limit = 512 * 1024**2 if os.getenv("APP_ENV") == "staging" else 3 * 1024**3
        self.budget = min(requested_budget, free_limit) if self.free_guard else requested_budget
        if self.budget <= 0:
            raise RuntimeError("MEDIA_BUDGET_BYTES must be positive")
        endpoint = os.environ["MEDIA_ENDPOINT"]
        if not re.fullmatch(r"https://[a-f0-9]{32}\.r2\.cloudflarestorage\.com", endpoint):
            raise RuntimeError("Use the account's HTTPS R2 endpoint")
        self.client = client or boto3.client("s3", endpoint_url=endpoint, region_name="auto",
            aws_access_key_id=os.environ["MEDIA_ACCESS_KEY_ID"], aws_secret_access_key=os.environ["MEDIA_SECRET_ACCESS_KEY"],
            config=Config(signature_version="s3v4", connect_timeout=10, read_timeout=25,
                retries={"total_max_attempts": 1}, request_checksum_calculation="when_required", response_checksum_validation="when_required", s3={"addressing_style": "path"}))

    def operation(self, kind):
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        key = f"{self.bucket}:{self.prefix}:{month}:{kind}"
        limit = 20000 if kind == "write" else 1000000
        self.db.media_usage.update_one({"_id": key}, {"$setOnInsert": {"count": 0}}, upsert=True)
        if not self.db.media_usage.update_one({"_id": key, "count": {"$lt": limit}}, {"$inc": {"count": 1}}).matched_count:
            raise HTTPException(507, "Photo request allowance reached. Contact your administrator.")

    def ready(self):
        self.operation("read")
        self.client.head_bucket(Bucket=self.bucket)
        return "private-object-storage"

    def key(self, path):
        if not re.fullmatch(r"britsmaid/uploads/[a-f0-9]{24}/[a-f0-9]{24}-[a-f0-9]{32}\.(jpg|mp4|mov)", path):
            raise HTTPException(422, "Invalid ordinary media path")
        return self.prefix + path.removeprefix("britsmaid/uploads/")

    def put(self, path, data, content_type):
        key = self.key(path)
        digest = hashlib.sha256(data).hexdigest()
        identity = f"{self.bucket}:{key}"
        now, owner = datetime.now(timezone.utc), secrets.token_hex(16)
        try:
            self.db.media_allocations.insert_one({"_id": identity, "digest": digest, "size": len(data),
                "quota_reserved": False, "state": "pending", "lease_until": now - timedelta(seconds=1)})
        except DuplicateKeyError:
            pass
        row = self.db.media_allocations.find_one({"_id": identity})
        if row["digest"] != digest or row["size"] != len(data) or row["state"] == "deleted":
            raise HTTPException(409, "Photo retry does not match the original upload")
        if row["state"] == "ready":
            return {"path": "r2:" + key, "size": len(data)}
        locked = self.db.media_allocations.find_one_and_update({"_id": identity, "lease_until": {"$lte": now}},
            {"$set": {"lease_until": now + timedelta(minutes=5), "lease_owner": owner}}, return_document=ReturnDocument.AFTER)
        if not locked:
            raise HTTPException(409, "This photo is still processing. Please retry shortly.")
        try:
            budget_key = f"{self.bucket}:{self.prefix}"
            self.db.media_usage.update_one({"_id": budget_key}, {"$setOnInsert": {"bytes": 0}}, upsert=True)
            if not locked.get("quota_reserved"):
                if not self.db.media_usage.update_one({"_id": budget_key, "bytes": {"$lte": self.budget - len(data)}},
                    {"$inc": {"bytes": len(data)}}).matched_count:
                    raise HTTPException(507, "Private photo storage allowance reached. Contact your administrator.")
                # A crash between these writes overcounts capacity; it never grants extra space.
                self.db.media_allocations.update_one({"_id": identity}, {"$set": {"quota_reserved": True}})
            self.operation("write")
            self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type,
                Metadata={"sha256": digest}, CacheControl="private, no-store")
            self.db.media_allocations.update_one({"_id": identity}, {"$set": {"state": "ready"}})
            return {"path": "r2:" + key, "size": len(data)}
        finally:
            self.db.media_allocations.update_one({"_id": identity, "lease_owner": owner},
                {"$set": {"lease_until": datetime.now(timezone.utc)}})

    def get(self, path):
        if not path.startswith("r2:"):
            return self.legacy.get(path)
        key = path[3:]
        self.key("britsmaid/uploads/" + key.removeprefix(self.prefix))
        if not key.startswith(self.prefix):
            raise HTTPException(404, "File not found")
        self.operation("read")
        try:
            result = self.client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("NoSuchKey", "404"):
                raise HTTPException(404, "File not found") from None
            raise
        stream = result["Body"]
        try:
            data = stream.read(100 * 1024**2 + 1)
            allocation = self.db.media_allocations.find_one({"_id": f"{self.bucket}:{key}", "state": "ready"})
            if len(data) > 100 * 1024**2 or not allocation or hashlib.sha256(data).hexdigest() != allocation["digest"]:
                raise HTTPException(503, "Photo integrity check failed. Contact your administrator.")
            return data, result["ContentType"]
        finally:
            stream.close()

    def delete(self, path):
        if not path.startswith("r2:"):
            return self.legacy.delete(path)
        key = path[3:]
        self.key("britsmaid/uploads/" + key.removeprefix(self.prefix))
        if not key.startswith(self.prefix):
            raise HTTPException(422, "Invalid ordinary media reference")
        self.operation("write")
        self.client.delete_object(Bucket=self.bucket, Key=key)
        row = self.db.media_allocations.find_one_and_update({"_id": f"{self.bucket}:{key}", "quota_reserved": True},
            {"$set": {"state": "deleted", "quota_reserved": False}}, return_document=ReturnDocument.BEFORE)
        if row:
            self.db.media_usage.update_one({"_id": f"{self.bucket}:{self.prefix}"}, {"$inc": {"bytes": -row["size"]}})
