"""Persistent ordinary media for the small Atlas test deployment, never guest IDs."""
import hashlib
import threading

from bson import ObjectId
from fastapi import HTTPException
from gridfs import GridFSBucket, NoFile


class MongoMediaStore:
    def __init__(self, database, budget_bytes=128 * 1024 * 1024):
        self.db = database
        self.bucket = GridFSBucket(database, bucket_name="app_media")
        self.budget = budget_bytes
        self.lock = threading.Lock()

    def ready(self):
        self.db.command("ping")
        return "mongo-gridfs"

    def put(self, path, data, content_type):
        if not path.startswith("britsmaid/uploads/"):
            raise HTTPException(422, "Only ordinary room/report media belongs in this store")
        digest = hashlib.sha256(data).hexdigest()
        file_id = ObjectId(hashlib.sha256(path.encode()).hexdigest()[:24])
        # Render Free runs one process; serialize repeated upload acknowledgements.
        # This is intentionally not a multi-worker storage implementation.
        with self.lock:
            existing = self.db.app_media.files.find_one({"_id": file_id})
            if existing:
                if existing.get("metadata", {}).get("sha256") != digest:
                    raise HTTPException(409, "The upload retry does not match the original file")
                return {"path": "mongo:" + str(file_id), "size": existing["length"]}
            # Count allocated chunks, including any orphan left by an interrupted
            # process. Round up rather than underestimating the free-tier budget.
            chunk_bytes = 255 * 1024
            used = self.db.app_media.chunks.count_documents({}) * chunk_bytes
            needed = ((len(data) + chunk_bytes - 1) // chunk_bytes) * chunk_bytes
            if used + needed > self.budget:
                raise HTTPException(507, "Photo storage allowance reached. Ask the admin to review storage before adding more.")
            self.bucket.upload_from_stream_with_id(file_id, path, data, metadata={
                "content_type": content_type, "sha256": digest,
            })
        return {"path": "mongo:" + str(file_id), "size": len(data)}

    def get(self, path):
        if not path.startswith("mongo:") or not ObjectId.is_valid(path[6:]):
            raise HTTPException(404, "File not found in this deployment")
        try:
            stream = self.bucket.open_download_stream(ObjectId(path[6:]))
            try:
                return stream.read(), (stream.metadata or {}).get("content_type", "application/octet-stream")
            finally:
                stream.close()
        except NoFile:
            raise HTTPException(404, "File not found") from None

    def delete(self, path):
        if not path.startswith("mongo:") or not ObjectId.is_valid(path[6:]):
            raise HTTPException(422, "Invalid ordinary media reference")
        try:
            self.bucket.delete(ObjectId(path[6:]))
        except NoFile:
            pass
