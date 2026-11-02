from __future__ import annotations

import hashlib
import math
import re
import secrets
import sqlite3
import time
import uuid
from pathlib import Path

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError


class AuthenticationError(ValueError):
    pass


class AccountExists(AuthenticationError):
    pass


class AuthStore:
    def __init__(self, database_path: str, session_ttl_seconds: int = 86400):
        self.database_path = str(database_path)
        self.session_ttl_seconds = session_ttl_seconds
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self.password_hasher = PasswordHasher(
            time_cost=3,
            memory_cost=65536,
            parallelism=2,
            hash_len=32,
            salt_len=16,
            type=Type.ID,
        )
        self._dummy_hash = self.password_hasher.hash(secrets.token_urlsafe(48))
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS mesh_users (
                    user_id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    disabled INTEGER NOT NULL DEFAULT 0
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS mesh_sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES mesh_users(user_id),
                    expires_at REAL NOT NULL,
                    created_at REAL NOT NULL
                )
            """)
            db.execute("CREATE INDEX IF NOT EXISTS idx_mesh_sessions_expiry ON mesh_sessions(expires_at)")
            db.execute("""
                CREATE TABLE IF NOT EXISTS mesh_auth_rate_limits (
                    bucket TEXT PRIMARY KEY,
                    window_started REAL NOT NULL,
                    attempts INTEGER NOT NULL
                )
            """)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database_path, timeout=20)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        return db

    def consume_rate_limit(self, bucket: str, limit: int, window_seconds: int) -> int:
        if not bucket or len(bucket) > 256 or limit < 1 or window_seconds < 1:
            raise ValueError("Invalid rate-limit parameters")
        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT window_started,attempts FROM mesh_auth_rate_limits WHERE bucket=?",
                (bucket,),
            ).fetchone()
            if row is None or now - float(row["window_started"]) >= window_seconds:
                db.execute("""
                    INSERT INTO mesh_auth_rate_limits(bucket,window_started,attempts)
                    VALUES(?,?,1)
                    ON CONFLICT(bucket) DO UPDATE SET
                    window_started=excluded.window_started,attempts=1
                """, (bucket, now))
                retry_after = 0
            elif int(row["attempts"]) >= limit:
                retry_after = max(1, math.ceil(window_seconds - (now - float(row["window_started"]))))
            else:
                db.execute(
                    "UPDATE mesh_auth_rate_limits SET attempts=attempts+1 WHERE bucket=?",
                    (bucket,),
                )
                retry_after = 0
            if retry_after:
                db.rollback()
                return retry_after
            db.commit()
        return 0

    @staticmethod
    def normalize_email(email: str) -> str:
        value = str(email).strip().lower()
        if len(value) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise AuthenticationError("Invalid email address")
        return value

    @staticmethod
    def validate_password(password: str) -> str:
        if not isinstance(password, str) or len(password.encode("utf-8")) < 12:
            raise AuthenticationError("Password must contain at least 12 UTF-8 bytes")
        if len(password.encode("utf-8")) > 1024:
            raise AuthenticationError("Password exceeds the maximum supported length")
        return password

    def register(self, email: str, password: str) -> dict[str, str]:
        normalized = self.normalize_email(email)
        checked = self.validate_password(password)
        password_hash = self.password_hasher.hash(checked)
        user_id = str(uuid.uuid4())
        with self._connect() as db:
            try:
                db.execute(
                    "INSERT INTO mesh_users(user_id,email,password_hash,created_at) VALUES(?,?,?,?)",
                    (user_id, normalized, password_hash, time.time()),
                )
            except sqlite3.IntegrityError as exc:
                raise AccountExists("An account with this email already exists") from exc
        return {"user_id": user_id, "email": normalized}

    def login(self, email: str, password: str) -> dict[str, str | int]:
        normalized = self.normalize_email(email)
        if not isinstance(password, str) or len(password.encode("utf-8")) > 1024:
            raise AuthenticationError("Invalid email or password")
        with self._connect() as db:
            row = db.execute(
                "SELECT user_id,password_hash,disabled FROM mesh_users WHERE email=?",
                (normalized,),
            ).fetchone()
        encoded_hash = row["password_hash"] if row else self._dummy_hash
        try:
            valid = self.password_hasher.verify(encoded_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            valid = False
        if row is None or not valid or row["disabled"]:
            raise AuthenticationError("Invalid email or password")
        token = secrets.token_urlsafe(48)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        now = time.time()
        expires = now + self.session_ttl_seconds
        with self._connect() as db:
            db.execute(
                "INSERT INTO mesh_sessions(token_hash,user_id,expires_at,created_at) VALUES(?,?,?,?)",
                (token_hash, row["user_id"], expires, now),
            )
            db.execute("DELETE FROM mesh_sessions WHERE expires_at < ?", (now,))
        return {"access_token": token, "token_type": "bearer",
                "expires_at": int(expires), "user_id": row["user_id"]}

    def resolve_session(self, token: str) -> dict[str, str] | None:
        if not token or len(token) > 512:
            return None
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        now = time.time()
        with self._connect() as db:
            row = db.execute("""
                SELECT u.user_id,u.email FROM mesh_sessions s
                JOIN mesh_users u ON u.user_id=s.user_id
                WHERE s.token_hash=? AND s.expires_at>=? AND u.disabled=0
            """, (token_hash, now)).fetchone()
        return {"user_id": row["user_id"], "email": row["email"]} if row else None

    def revoke_session(self, token: str) -> bool:
        if not token or len(token) > 512:
            return False
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with self._connect() as db:
            result = db.execute("DELETE FROM mesh_sessions WHERE token_hash=?", (token_hash,))
            return result.rowcount == 1
