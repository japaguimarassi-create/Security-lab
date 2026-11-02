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
            db.execute("""
                CREATE TABLE IF NOT EXISTS mesh_resource_reservations (
                    task_id TEXT PRIMARY KEY,
                    node_id TEXT NOT NULL,
                    gpu_index INTEGER,
                    cpu_cores REAL NOT NULL,
                    ram_gib REAL NOT NULL,
                    vram_gib REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    created_at REAL NOT NULL
                )
            """)
            db.execute("CREATE INDEX IF NOT EXISTS idx_mesh_reservations_node ON mesh_resource_reservations(node_id,expires_at)")

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
            raw_max_task_seconds = item.get("max_task_seconds", 86400)
            if isinstance(raw_max_task_seconds, bool):
                raise ValueError("max_task_seconds must be an integer")
            try:
                max_task_seconds = int(raw_max_task_seconds)
            except (TypeError, ValueError) as exc:
                raise ValueError("max_task_seconds must be an integer") from exc
            if max_task_seconds != raw_max_task_seconds or not 1 <= max_task_seconds <= 86400:
                raise ValueError("max_task_seconds must be between 1 and 86400")
            normalized.append({
                "index": index,
                "name": name,
                "total_vram_gib": total,
                "available_vram_gib": available,
                "max_task_seconds": int(max_task_seconds),
            })
        return normalized

    def register(self, owner_id: str, provider_id: str, cpu_cores: float,
                 ram_gib: float, storage_gib: float,
                 gpus: list[dict[str, Any]] | None = None,
                 shared: bool = False,
                 ram_available_gib: float | None = None) -> dict[str, str]:
        owner = str(owner_id).strip()
        provider = str(provider_id).strip()
        if not owner or len(owner) > 128 or not provider or len(provider) > 80:
            raise ValueError("owner_id and provider_id are required and must be bounded")
        cpu = self._positive(cpu_cores, "cpu_cores")
        ram = self._positive(ram_gib, "ram_gib")
        ram_available = ram if ram_available_gib is None else self._positive(
            ram_available_gib, "ram_available_gib", True
        )
        if ram_available > ram:
            raise ValueError("ram_available_gib cannot exceed ram_gib")
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
            """, (node_id, owner, provider, cpu, cpu, ram, ram_available, storage, storage,
                  json.dumps(devices, separators=(",", ":")), token_hash,
                  int(shared), now, now))
        return {"node_id": node_id, "worker_token": token}

    def heartbeat(self, node_id: str, worker_token: str, owner_id: str | None = None,
                  cpu_available: float | None = None,
                  ram_available_gib: float | None = None,
                  storage_available_gib: float | None = None,
                  gpus: list[dict[str, Any]] | None = None) -> bool:
        if not worker_token or len(worker_token) > 512:
            return False
        token_hash = hashlib.sha256(worker_token.encode("utf-8")).hexdigest()
        with self._connect() as db:
            if owner_id is None:
                row = db.execute(
                    "SELECT * FROM mesh_workers WHERE node_id=? AND enabled=1",
                    (node_id,)
                ).fetchone()
            else:
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
            previous_devices = json.loads(row["gpus_json"])
            if len(gpu_devices) != len(previous_devices):
                raise ValueError("Heartbeat GPU count cannot change after registration")
            active_reservations = db.execute("""
                SELECT COALESCE(SUM(cpu_cores),0) AS cpu,
                       COALESCE(SUM(ram_gib),0) AS ram
                FROM mesh_resource_reservations
                WHERE node_id=? AND expires_at>?
            """, (node_id, time.time())).fetchone()
            reserved_by_gpu = db.execute("""
                SELECT gpu_index,COALESCE(SUM(vram_gib),0) AS vram
                FROM mesh_resource_reservations
                WHERE node_id=? AND gpu_index IS NOT NULL AND expires_at>?
                GROUP BY gpu_index
            """, (node_id, time.time())).fetchall()
            reserved_vram = {int(item["gpu_index"]): float(item["vram"]) for item in reserved_by_gpu}
            if cpu_available is not None:
                cpu = min(float(row["cpu_total"]), cpu + float(active_reservations["cpu"]))
            if ram_available_gib is not None:
                ram = min(float(row["ram_total_gib"]), ram + float(active_reservations["ram"]))
            for old, new in zip(previous_devices, gpu_devices):
                if new["total_vram_gib"] > old["total_vram_gib"] + 0.001:
                    raise ValueError("Heartbeat cannot increase registered VRAM capacity")
                if new["available_vram_gib"] > old["total_vram_gib"]:
                    raise ValueError("Heartbeat VRAM availability exceeds registered capacity")
                if new["max_task_seconds"] != old.get("max_task_seconds", 86400):
                    raise ValueError("Heartbeat cannot change the registered maximum task duration")
                if gpus is not None:
                    new["available_vram_gib"] = min(
                        float(old["total_vram_gib"]),
                        float(new["available_vram_gib"]) + reserved_vram.get(int(new["index"]), 0.0),
                    )
            db.execute("""
                UPDATE mesh_workers SET cpu_available=?, ram_available_gib=?,
                    storage_available_gib=?, gpus_json=?, last_seen=?
                WHERE node_id=?
            """, (cpu, ram, storage, json.dumps(gpu_devices, separators=(",", ":")),
                  time.time(), node_id))
            return True

    def list_schedulable(self, owner_id: str, include_shared: bool = True) -> list[dict[str, Any]]:
        now = time.time()
        cutoff = now - self.heartbeat_ttl_seconds
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
            reservation_rows = db.execute("""
                SELECT node_id,gpu_index,cpu_cores,ram_gib,vram_gib
                FROM mesh_resource_reservations WHERE expires_at>?
            """, (now,)).fetchall()
        reservations: dict[str, dict[str, Any]] = {}
        for item in reservation_rows:
            record = reservations.setdefault(item["node_id"], {
                "cpu": 0.0, "ram": 0.0, "gpus": {},
            })
            record["cpu"] += float(item["cpu_cores"] or 0)
            record["ram"] += float(item["ram_gib"] or 0)
            if item["gpu_index"] is not None:
                key = int(item["gpu_index"])
                record["gpus"][key] = record["gpus"].get(key, 0.0) + float(item["vram_gib"] or 0)
        result = []
        for row in rows:
            item = self._public_row(row)
            held = reservations.get(row["node_id"], {})
            item["cpu_available"] = max(0.0, item["cpu_available"] - held.get("cpu", 0.0))
            item["ram_available_gib"] = max(0.0, item["ram_available_gib"] - held.get("ram", 0.0))
            for gpu in item["gpus"]:
                gpu["available_vram_gib"] = max(
                    0.0,
                    gpu["available_vram_gib"] - held.get("gpus", {}).get(gpu["index"], 0.0),
                )
            result.append(item)
        return result

    def authenticate_worker(self, node_id: str, worker_token: str) -> bool:
        if not worker_token or len(worker_token) > 512:
            return False
        token_hash = hashlib.sha256(worker_token.encode("utf-8")).hexdigest()
        with self._connect() as db:
            row = db.execute(
                "SELECT token_hash FROM mesh_workers WHERE node_id=? AND enabled=1",
                (node_id,),
            ).fetchone()
        return bool(row and secrets.compare_digest(row["token_hash"], token_hash))

    def reserve_capacity(self, task_id: str, node_id: str, gpu_index: int | None,
                         cpu_cores: float, ram_gib: float, vram_gib: float,
                         ttl_seconds: int = 900) -> bool:
        cpu = self._positive(cpu_cores, "reserved CPU")
        ram = self._positive(ram_gib, "reserved RAM")
        vram = self._positive(vram_gib, "reserved VRAM", True)
        if gpu_index is None and vram > 0:
            raise ValueError("A VRAM reservation requires a physical GPU index")
        if gpu_index is not None and (isinstance(gpu_index, bool) or int(gpu_index) < 0):
            raise ValueError("Invalid GPU index")
        if not 60 <= int(ttl_seconds) <= 86400:
            raise ValueError("Reservation TTL must be between 60 and 86400 seconds")
        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                worker = db.execute("""
                    SELECT * FROM mesh_workers
                    WHERE node_id=? AND enabled=1 AND last_seen>=?
                """, (node_id, now - self.heartbeat_ttl_seconds)).fetchone()
                if worker is None:
                    db.rollback()
                    return False
                prior = db.execute("""
                    SELECT COALESCE(SUM(cpu_cores),0) AS cpu,
                           COALESCE(SUM(ram_gib),0) AS ram
                    FROM mesh_resource_reservations
                    WHERE node_id=? AND expires_at>?
                """, (node_id, now)).fetchone()
                if float(worker["cpu_available"]) - float(prior["cpu"]) < cpu:
                    db.rollback()
                    return False
                if float(worker["ram_available_gib"]) - float(prior["ram"]) < ram:
                    db.rollback()
                    return False
                if gpu_index is not None:
                    devices = json.loads(worker["gpus_json"])
                    if int(gpu_index) >= len(devices):
                        db.rollback()
                        return False
                    device = devices[int(gpu_index)]
                    held = db.execute("""
                        SELECT COALESCE(SUM(vram_gib),0) AS vram
                        FROM mesh_resource_reservations
                        WHERE node_id=? AND gpu_index=? AND expires_at>?
                    """, (node_id, int(gpu_index), now)).fetchone()
                    if float(device["available_vram_gib"]) - float(held["vram"]) < vram:
                        db.rollback()
                        return False
                db.execute("""
                    INSERT INTO mesh_resource_reservations(
                        task_id,node_id,gpu_index,cpu_cores,ram_gib,vram_gib,expires_at,created_at
                    ) VALUES(?,?,?,?,?,?,?,?)
                """, (task_id, node_id, gpu_index, cpu, ram, vram, now + ttl_seconds, now))
                db.commit()
                return True
            except sqlite3.IntegrityError:
                db.rollback()
                return False
            except Exception:
                db.rollback()
                raise

    def renew_capacity(self, task_id: str, ttl_seconds: int = 900) -> bool:
        if not 60 <= int(ttl_seconds) <= 86400:
            raise ValueError("Reservation TTL must be between 60 and 86400 seconds")
        now = time.time()
        with self._connect() as db:
            result = db.execute(
                """UPDATE mesh_resource_reservations
                   SET expires_at=?
                   WHERE task_id=? AND EXISTS (
                       SELECT 1 FROM mesh_workers
                       WHERE mesh_workers.node_id=mesh_resource_reservations.node_id
                         AND mesh_workers.enabled=1
                   )""",
                (now + int(ttl_seconds), task_id),
            )
        return result.rowcount == 1

    def release_capacity(self, task_id: str) -> bool:
        with self._connect() as db:
            result = db.execute(
                "DELETE FROM mesh_resource_reservations WHERE task_id=?",
                (task_id,),
            )
        return result.rowcount == 1

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
