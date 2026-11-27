"""Private guest documents encrypted before entering the existing private R2 bucket."""
import hashlib
import io
import os
from fastapi import HTTPException
from backup_crypto import seal, unseal


class EncryptedGuestStore:
    def __init__(self, backup_store):
        self.store = backup_store
        self.bucket = backup_store.bucket

    @staticmethod
    def encryption_key():
        key = os.environ.get('BACKUP_ENCRYPTION_KEY', '')
        if len(key) < 32:
            raise HTTPException(503, 'Guest document encryption is not configured')
        return hashlib.sha256((key + '|britsmaid-guest-documents-v1').encode()).hexdigest()

    def put(self, identity, data):
        key = 'guest-documents/' + identity.rsplit('/', 1)[-1].removesuffix('.jpg') + '.bmbak'
        encrypted = io.BytesIO()
        seal(io.BytesIO(data), encrypted, self.encryption_key())
        ledger = self.store.db
        allocation_id = self.bucket + ':' + key
        if not ledger.guest_document_allocations.find_one({'_id': allocation_id}):
            quota = 'guest-document-capacity:' + self.bucket
            size = encrypted.tell()
            ledger.media_usage.update_one({'_id': quota}, {'$setOnInsert': {'bytes': 0}}, upsert=True)
            if not ledger.media_usage.update_one({'_id': quota, 'bytes': {'$lte': 512 * 1024**2 - size}}, {'$inc': {'bytes': size}}).matched_count:
                raise HTTPException(507, 'Guest document allowance reached. Review retained IDs before adding more.')
            ledger.guest_document_allocations.update_one({'_id': allocation_id}, {'$setOnInsert': {'size': size}}, upsert=True)
        try:
            encrypted.seek(0)
            self.store.put(key, encrypted)
        except Exception:
            # The new object cannot yet be linked to a document. Reclaim it only
            # after storage acknowledges deletion, including lost-upload replies.
            self.delete({'storage_bucket': self.bucket, 'storage_key': key})
            raise
        return {'storage_provider': 'encrypted-r2-v1', 'storage_key': key, 'storage_bucket': self.bucket}

    def read(self, document):
        self.validate(document)
        encrypted = self.store.read(document['storage_key'])
        try:
            clear = io.BytesIO()
            unseal(encrypted, clear, self.encryption_key())
            return clear.getvalue()
        finally:
            encrypted.close()

    def delete(self, document):
        self.validate(document)
        self.store.delete(document['storage_key'])
        row = self.store.db.guest_document_allocations.find_one_and_delete({'_id': self.bucket + ':' + document['storage_key']})
        if row:
            self.store.db.media_usage.update_one({'_id': 'guest-document-capacity:' + self.bucket}, {'$inc': {'bytes': -row['size']}})

    def validate(self, document):
        if document.get('storage_bucket') != self.bucket or not document.get('storage_key', '').startswith('guest-documents/'):
            raise HTTPException(404, 'Document not found')
