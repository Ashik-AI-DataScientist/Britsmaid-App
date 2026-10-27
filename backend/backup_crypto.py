"""Authenticated streaming backup format; truncation and reordering fail closed."""
import os
import struct
import hashlib
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"BMBACKUP1"
CHUNK = 1024 * 1024


def cipher(key, salt):
    if len(key) < 32:
        raise ValueError("Use a generated backup encryption secret of at least 32 characters")
    raw = hashlib.sha256(key.encode()).digest()
    return AESGCM(HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=MAGIC).derive(raw))


def seal(source, target, key):
    salt = os.urandom(32)
    box = cipher(key, salt)
    target.write(MAGIC + salt)
    index = 0
    while True:
        block = source.read(CHUNK)
        nonce = index.to_bytes(12, "big")
        encrypted = box.encrypt(nonce, block, MAGIC + salt + nonce)
        target.write(struct.pack(">I", len(encrypted)))
        target.write(encrypted)
        if not block:
            break
        index += 1


def unseal(source, target, key):
    if source.read(len(MAGIC)) != MAGIC:
        raise ValueError("Not a Britsmaid encrypted backup")
    salt = source.read(32)
    if len(salt) != 32:
        raise ValueError("Backup header is truncated")
    box = cipher(key, salt)
    index = 0
    while True:
        raw = source.read(4)
        if len(raw) != 4:
            raise ValueError("Backup is incomplete")
        size = struct.unpack(">I", raw)[0]
        if not 16 <= size <= CHUNK + 16:
            raise ValueError("Invalid encrypted backup block")
        block = source.read(size)
        if len(block) != size:
            raise ValueError("Backup is truncated")
        nonce = index.to_bytes(12, "big")
        decrypted = box.decrypt(nonce, block, MAGIC + salt + nonce)
        if not decrypted:
            if source.read(1):
                raise ValueError("Unexpected trailing backup content")
            return
        target.write(decrypted)
        index += 1
