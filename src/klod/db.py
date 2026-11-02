from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any


POSTGRES_LOCK_KEY = 731940281


def is_postgres(database_path: str) -> bool:
    value = str(database_path).strip().lower()
    return value.startswith(("postgres://", "postgresql://", "postgresql+psycopg://"))


def prepare_database_path(database_path: str) -> None:
    if not is_postgres(database_path) and database_path != ":memory:":
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)


def _postgres_sql(query: str) -> str:
    sql = re.sub(r"\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b", "BIGSERIAL PRIMARY KEY", query, flags=re.I)
    sql = re.sub(r"\bINTEGER\b", "BIGINT", sql, flags=re.I)
    sql = re.sub(r"\bREAL\b", "DOUBLE PRECISION", sql, flags=re.I)
    sql = re.sub(r"\bBLOB\b", "BYTEA", sql, flags=re.I)
    return sql.replace("?", "%s")


class _EmptyCursor:
    rowcount = 0
    lastrowid = None

    @staticmethod
    def fetchone():
        return None

    @staticmethod
    def fetchall():
        return []


class PostgresConnection:
    def __init__(self, database_url: str, timeout: float = 20, **_: Any):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("PostgreSQL support requires psycopg[binary]") from exc

        url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        self.raw = psycopg.connect(
            url,
            connect_timeout=max(1, int(timeout)),
            autocommit=True,
            row_factory=dict_row,
        )
        self._active = False
        self._closed = False
        self._row_factory = None

    @property
    def row_factory(self):
        return self._row_factory

    @row_factory.setter
    def row_factory(self, value):
        self._row_factory = value

    def _begin(self):
        if self._closed:
            raise RuntimeError("Database connection is closed")
        if not self._active:
            self.raw.execute("BEGIN")
            self._active = True

    def execute(self, query: str, parameters=()):
        statement = query.strip()
        upper = statement.upper()

        if upper.startswith("PRAGMA "):
            return _EmptyCursor()

        if upper.startswith("BEGIN IMMEDIATE"):
            self._begin()
            self.raw.execute("SELECT pg_advisory_xact_lock(%s)", (POSTGRES_LOCK_KEY,))
            return _EmptyCursor()

        if upper.startswith("CREATE VIRTUAL TABLE"):
            raise sqlite3.OperationalError("SQLite FTS is not available on PostgreSQL")

        self._begin()
        try:
            return self.raw.execute(_postgres_sql(query), parameters or ())
        except Exception as exc:
            try:
                from psycopg.errors import UniqueViolation
            except ImportError:
                raise
            if isinstance(exc, UniqueViolation):
                raise sqlite3.IntegrityError(str(exc)) from exc
            raise

    def executemany(self, query: str, parameter_rows):
        self._begin()
        return self.raw.cursor().executemany(_postgres_sql(query), parameter_rows)

    def commit(self):
        if self._active:
            self.raw.commit()
            self._active = False

    def rollback(self):
        if self._active:
            self.raw.rollback()
            self._active = False

    def close(self):
        if not self._closed:
            if self._active:
                self.rollback()
            self.raw.close()
            self._closed = True

    def __enter__(self):
        self._begin()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            if exc_type is None:
                self.commit()
            else:
                self.rollback()
        finally:
            self.close()
        return False


def connect(database_path: str, timeout: float = 20, **kwargs):
    if is_postgres(database_path):
        return PostgresConnection(database_path, timeout=timeout, **kwargs)
    return sqlite3.connect(database_path, timeout=timeout, **kwargs)
