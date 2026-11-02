from __future__ import annotations

import hashlib
import json
import math
import secrets
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any


class ResourceRegistry:
    def __init__(self, database_path: str, heartbeat_ttl_seconds: int = 120):
        self.database_path = str(database_path)
        self.heartbeat_ttl_seconds = heartbeat_ttl_seconds
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS mesh_workers (
                    node_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    cpu_total REAL NOT NULL,
                    cpu_available REAL NOT NULL,
                    ram_total_gib REAL NOT NULL,
                    ram_available_gib REAL NOT NULL,
                    storage_total_gib REAL NOT NULL,
                    storage_available_gib REAL NOT NULL,
                    gpus_json TEXT NOT NULL,
                    token_hash TEXT NOT NULL,
                    shared INTEGER NOT NULL DEFAULT 0,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    last_seen REAL NOT NULL,
                    created_at REAL NOT NULL
                )
            """)
            db.execute("CREATE INDEX IF NOT EXISTS idx_mesh_workers_online ON mesh_workers(enabled, shared, last_seen)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_mesh_workers_owner ON mesh_workers(owner_id, enabled)")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database_path, timeout=20, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
        return db

    @staticmethod
    def _positive(value: float, name: str, allow_zero: bool = False) -> float:
        number = float(value)
        if not math.isfinite(number) or (number < 0 if allow_zero else number <= 0):
            raise ValueError(f"{name} must be a finite {'non-negative' if allow_zero else 'positive'} number")
        return number

    @classmethod
    def _normalize_gpus(cls, gpus: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not isinstance(gpus, list) or len(gpus) > 16:
            raise ValueError("gpus must be a list containing at most 16 devices")
        normalized = []
        for index, item in enumerate(gpus):
            if not isinstance(item, dict):
                raise ValueError("Each GPU entry must be an object")
            total = cls._positive(item.get("total_vram_gib", 0), "total_vram_gib")
            available = cls._positive(item.get("available_vram_gib", total), "available_vram_gib", True)
            if available > total:
                raise ValueError("available_vram_gib cannot exceed total_vram_gib")
            name = str(item.get("name", f"GPU-{index}"))[:120]
            normalized.append({
                "index": index,
                "name": name,
                "total_vram_gib": total,
                "available_vram_gib": available,
            })
        return normalized

    def register(self, owner_id: str, provider_id: str, cpu_cores: float,
                 ram_gib: float, storage_gib: float,
                 gpus: list[dict[str, Any]] | None = None,
                 shared: bool = False) -> dict[str, str]:
        owner = str(owner_id).strip()
        provider = str(provider_id).strip()
        if not owner or len(owner) > 128 or not provider or len(provider) > 80:
            raise ValueError("owner_id and provider_id are required and must be bounded")
        cpu = self._positive(cpu_cores, "cpu_cores")
        ram = self._positive(ram_gib, "ram_gib")
        storage = self._positive(storage_gib, "storage_gib", True)
        devices = self._normalize_gpus(gpus or [])
        now = time.time()
        node_id = str(uuid.uuid4())
        token = secrets.token_urlsafe(48)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with self._connect() as db:
            db.execute("""
                INSERT INTO mesh_workers(
                    node_id, owner_id, provider_id, cpu_total, cpu_available,
                    ram_total_gib, ram_available_gib, storage_total_gib,
                    storage_available_gib, gpus_json, token_hash, shared,
                    enabled, last_seen, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """, (node_id, owner, provider, cpu, cpu, ram, ram, storage, storage,
                  json.dumps(devices, separators=(",", ":")), token_hash,
                  int(shared), now, now))
        return {"node_id": node_id, "worker_token": token}

    def heartbeat(self, node_id: str, worker_token: str, owner_id: str,
                  cpu_available: float | None = None,
                  ram_available_gib: float | None = None,
                  storage_available_gib: float | None = None,
                  gpus: list[dict[str, Any]] | None = None) -> bool:
        if not worker_token or len(worker_token) > 512:
            return False
        token_hash = hashlib.sha256(worker_token.encode("utf-8")).hexdigest()
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM mesh_workers WHERE node_id=? AND owner_id=? AND enabled=1",
                (node_id, owner_id)
            ).fetchone()
            if row is None or not secrets.compare_digest(row["token_hash"], token_hash):
                return False
            cpu = row["cpu_available"] if cpu_available is None else self._positive(cpu_available, "cpu_available", True)
            ram = row["ram_available_gib"] if ram_available_gib is None else self._positive(ram_available_gib, "ram_available_gib", True)
            storage = row["storage_available_gib"] if storage_available_gib is None else self._positive(storage_available_gib, "storage_available_gib", True)
            if cpu > row["cpu_total"] or ram > row["ram_total_gib"] or storage > row["storage_total_gib"]:
                raise ValueError("Heartbeat availability cannot exceed registered capacity")
            gpu_devices = json.loads(row["gpus_json"]) if gpus is None else self._normalize_gpus(gpus)
            if len(gpu_devices) != len(json.loads(row["gpus_json"])):
                raise ValueError("Heartbeat GPU count cannot change after registration")
            for old, new in zip(json.loads(row["gpus_json"]), gpu_devices):
                if new["total_vram_gib"] > old["total_vram_gib"] + 0.001:
                    raise ValueError("Heartbeat cannot increase registered VRAM capacity")
                if new["available_vram_gib"] > old["total_vram_gib"]:
                    raise ValueError("Heartbeat VRAM availability exceeds registered capacity")
            db.execute("""
                UPDATE mesh_workers SET cpu_available=?, ram_available_gib=?,
                    storage_available_gib=?, gpus_json=?, last_seen=?
                WHERE node_id=?
            """, (cpu, ram, storage, json.dumps(gpu_devices, separators=(",", ":")),
                  time.time(), node_id))
            return True

    def list_schedulable(self, owner_id: str, include_shared: bool = True) -> list[dict[str, Any]]:
        cutoff = time.time() - self.heartbeat_ttl_seconds
        with self._connect() as db:
            if include_shared:
                rows = db.execute("""
                    SELECT * FROM mesh_workers
                    WHERE enabled=1 AND last_seen>=? AND (owner_id=? OR shared=1)
                    ORDER BY last_seen DESC
                """, (cutoff, owner_id)).fetchall()
            else:
                rows = db.execute("""
                    SELECT * FROM mesh_workers
                    WHERE enabled=1 AND last_seen>=? AND owner_id=?
                    ORDER BY last_seen DESC
                """, (cutoff, owner_id)).fetchall()
        return [self._public_row(row) for row in rows]

    def list_owned(self, owner_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM mesh_workers WHERE owner_id=? AND enabled=1 ORDER BY created_at DESC",
                (owner_id,)
            ).fetchall()
        return [self._public_row(row) for row in rows]

    def revoke(self, node_id: str, owner_id: str) -> bool:
        with self._connect() as db:
            result = db.execute(
                "UPDATE mesh_workers SET enabled=0 WHERE node_id=? AND owner_id=?",
                (node_id, owner_id)
            )
            return result.rowcount == 1

    def _public_row(self, row: sqlite3.Row) -> dict[str, Any]:
        last_seen = float(row["last_seen"])
        online = time.time() - last_seen <= self.heartbeat_ttl_seconds
        gpus = json.loads(row["gpus_json"])
        return {
            "node_id": row["node_id"],
            "owner_id": row["owner_id"],
            "provider_id": row["provider_id"],
            "cpu_total": row["cpu_total"],
            "cpu_available": row["cpu_available"],
            "ram_total_gib": row["ram_total_gib"],
            "ram_available_gib": row["ram_available_gib"],
            "storage_total_gib": row["storage_total_gib"],
            "storage_available_gib": row["storage_available_gib"],
            "gpus": gpus,
            "shared": bool(row["shared"]),
            "online": online,
            "last_seen": last_seen,
        }
