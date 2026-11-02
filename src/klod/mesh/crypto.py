from __future__ import annotations

import hmac
import secrets

from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .relativity import canonical_relativity_bytes, relativity_digest

MAGIC = b"GRMESH01"
SALT_BYTES = 16
NONCE_BYTES = 12
KEY_BYTES = 32
HEADER_BYTES = len(MAGIC) + SALT_BYTES + NONCE_BYTES + 32
ARGON2_TIME_COST = 3
ARGON2_MEMORY_KIB = 65536
ARGON2_PARALLELISM = 2


class VaultError(ValueError):
    pass


class VaultAuthenticationError(VaultError):
    pass


class RelativityCorpusMismatch(VaultError):
    pass


def _secret_bytes(master_secret: str | bytes) -> bytes:
    if isinstance(master_secret, str):
        value = master_secret.encode("utf-8")
    elif isinstance(master_secret, bytes):
        value = master_secret
    else:
        raise TypeError("master_secret must be str or bytes")
    if len(value) < 32:
        raise VaultError("GPU_MESH_MASTER_SECRET must contain at least 32 UTF-8 bytes")
    if len(value) > 4096:
        raise VaultError("GPU_MESH_MASTER_SECRET exceeds the maximum supported length")
    return value


def derive_key(master_secret: str | bytes, salt: bytes) -> bytes:
    if len(salt) != SALT_BYTES:
        raise VaultError("Invalid Argon2id salt length")
    theory = canonical_relativity_bytes()
    secret = b"GPU-MESH-GR-VAULT\\x00v1\\x00" + theory + b"\\x00" + _secret_bytes(master_secret)
    return hash_secret_raw(
        secret=secret,
        salt=salt,
        time_cost=ARGON2_TIME_COST,
        memory_cost=ARGON2_MEMORY_KIB,
        parallelism=ARGON2_PARALLELISM,
        hash_len=KEY_BYTES,
        type=Type.ID,
        version=19,
    )


def encrypt_bytes(plaintext: bytes, master_secret: str | bytes) -> bytes:
    if not isinstance(plaintext, bytes):
        raise TypeError("plaintext must be bytes")
    salt = secrets.token_bytes(SALT_BYTES)
    nonce = secrets.token_bytes(NONCE_BYTES)
    digest = relativity_digest()
    header = MAGIC + salt + nonce + digest
    key = derive_key(master_secret, salt)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, header)
    return header + ciphertext


def decrypt_bytes(payload: bytes, master_secret: str | bytes) -> bytes:
    if not isinstance(payload, bytes) or len(payload) < HEADER_BYTES + 16:
        raise VaultError("Encrypted payload is truncated")
    if not hmac.compare_digest(payload[:len(MAGIC)], MAGIC):
        raise VaultError("Unknown or unsupported encrypted payload format")
    offset = len(MAGIC)
    salt = payload[offset:offset + SALT_BYTES]
    offset += SALT_BYTES
    nonce = payload[offset:offset + NONCE_BYTES]
    offset += NONCE_BYTES
    stored_digest = payload[offset:offset + 32]
    offset += 32
    current_digest = relativity_digest()
    if not hmac.compare_digest(stored_digest, current_digest):
        raise RelativityCorpusMismatch("The canonical general-relativity corpus does not match this encrypted bundle")
    header = payload[:HEADER_BYTES]
    key = derive_key(master_secret, salt)
    try:
        return AESGCM(key).decrypt(nonce, payload[offset:], header)
    except InvalidTag as exc:
        raise VaultAuthenticationError("Decryption failed: wrong master secret or modified ciphertext") from exc
