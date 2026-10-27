"""Separate encrypted recovery bucket with a conservative shared capacity ledger."""
import os
import tempfile
import boto3
from botocore.config import Config
from fastapi import HTTPException


class BackupStore:
    def __init__(self, database, client=None):
        self.db = database
        self.bucket = os.environ["BACKUP_BUCKET"]
        if self.bucket == os.getenv("MEDIA_BUCKET"):
            raise RuntimeError("Backups require a separate private bucket")
        self.client = client or boto3.client("s3", endpoint_url=os.environ["MEDIA_ENDPOINT"], region_name="auto",
            aws_access_key_id=os.environ["BACKUP_ACCESS_KEY_ID"], aws_secret_access_key=os.environ["BACKUP_SECRET_ACCESS_KEY"],
            config=Config(signature_version="s3v4", connect_timeout=10, read_timeout=25, retries={"total_max_attempts": 1}, request_checksum_calculation="when_required", response_checksum_validation="when_required", s3={"addressing_style": "path"}))

    def operation(self):
        from datetime import datetime, timezone
        identity = "backups:" + datetime.now(timezone.utc).strftime("%Y-%m")
        self.db.media_usage.update_one({"_id": identity}, {"$setOnInsert": {"count": 0}}, upsert=True)
        if not self.db.media_usage.update_one({"_id": identity, "count": {"$lt": 20000}}, {"$inc": {"count": 1}}).matched_count:
            raise HTTPException(507, "Backup request allowance reached")

    def put(self, key, stream):
        if not key.startswith(("media/", "database/")) or not key.endswith(".bmbak"):
            raise HTTPException(422, "Invalid backup name")
        stream.seek(0, 2)
        size = stream.tell()
        stream.seek(0)
        # Never reuse keys for different database snapshots or immutable media IDs.
        identity = self.bucket + ":" + key
        row = self.db.backup_allocations.find_one({"_id": identity})
        if not row:
            quota = "backup-capacity:" + self.bucket
            self.db.media_usage.update_one({"_id": quota}, {"$setOnInsert": {"bytes": 0}}, upsert=True)
            if not self.db.media_usage.update_one({"_id": quota, "bytes": {"$lte": 4 * 1024**3 - size}}, {"$inc": {"bytes": size}}).matched_count:
                raise HTTPException(507, "Backup capacity allowance reached")
            # A crash here can overcount capacity, never undercount it.
            self.db.backup_allocations.update_one({"_id": identity}, {"$setOnInsert": {"size": size, "key": key}}, upsert=True)
        elif row["size"] != size:
            raise HTTPException(409, "Backup retry has a different size")
        self.operation()
        self.client.put_object(Bucket=self.bucket, Key=key, Body=stream, ContentLength=size, ContentType="application/octet-stream", CacheControl="no-store")

    def read(self, key):
        self.operation()
        result = self.client.get_object(Bucket=self.bucket, Key=key)
        source = result["Body"]
        target = tempfile.TemporaryFile()
        try:
            count = 0
            while block := source.read(1024 * 1024):
                count += len(block)
                if count > 150 * 1024**2:
                    raise HTTPException(507, "Backup object is unexpectedly large")
                target.write(block)
            target.seek(0)
            return target
        except BaseException:
            target.close()
            raise
        finally:
            source.close()

    def delete(self, key):
        self.operation()
        self.client.delete_object(Bucket=self.bucket, Key=key)
        row = self.db.backup_allocations.find_one_and_delete({"_id": self.bucket + ":" + key})
        if row:
            self.db.media_usage.update_one({"_id": "backup-capacity:" + self.bucket}, {"$inc": {"bytes": -row["size"]}})
