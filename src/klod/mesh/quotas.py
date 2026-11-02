from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Mapping


DEFAULT_WEEKLY_LIMITS = {
    "gpu_seconds": 1800.0,
    "vram_gib_seconds": 7200.0,
    "cpu_core_seconds": 36000.0,
    "ram_gib_seconds": 43200.0,
    "storage_gib_hours": 1680.0,
    "bandwidth_gib": 2.0,
}


class QuotaExceeded(ValueError):
    def __init__(self, metric: str, used: float, requested: float, limit: float):
        self.metric = metric
        self.used = used
        self.requested = requested
        self.limit = limit
        super().__init__(f"Weekly {metric} quota exceeded")


class QuotaLedger:
    def __init__(self, database_path: str, limits: Mapping[str, float] | None = None):
        self.database_path = str(database_path)
        self.limits = dict(DEFAULT_WEEKLY_LIMITS if limits is None else limits)
        for metric, limit in self.limits.items():
            value = float(limit)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"Invalid quota limit for {metric}")
            self.limits[metric] = value
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS mesh_quota_usage (
                    user_id TEXT NOT NULL,
                    week_start TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    used REAL NOT NULL,
                    PRIMARY KEY(user_id, week_start, metric)
                )
            """)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database_path, timeout=20, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        return db

    @staticmethod
    def week_start(at: float | None = None) -> str:
        current = datetime.fromtimestamp(at, tz=timezone.utc) if at is not None else datetime.now(timezone.utc)
        monday = (current - timedelta(days=current.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return monday.date().isoformat()

    def reserve(self, user_id: str, amounts: Mapping[str, float],
                at: float | None = None) -> dict[str, dict[str, float]]:
        if not user_id or len(user_id) > 128 or not amounts:
            raise ValueError("user_id and at least one quota amount are required")
        week = self.week_start(at)
        normalized = {}
        for metric, amount in amounts.items():
            if metric not in self.limits:
                raise ValueError(f"Unknown quota metric: {metric}")
            value = float(amount)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"Quota amount for {metric} must be finite and positive")
            normalized[metric] = value

        results = {}
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                for metric, amount in normalized.items():
                    row = db.execute("""
                        SELECT used FROM mesh_quota_usage
                        WHERE user_id=? AND week_start=? AND metric=?
                    """, (user_id, week, metric)).fetchone()
                    used = float(row["used"]) if row else 0.0
                    limit = float(self.limits[metric])
                    if used + amount > limit + 1e-9:
                        raise QuotaExceeded(metric, used, amount, limit)
                    new_used = used + amount
                    db.execute("""
                        INSERT INTO mesh_quota_usage(user_id,week_start,metric,used)
                        VALUES(?,?,?,?)
                        ON CONFLICT(user_id,week_start,metric)
                        DO UPDATE SET used=excluded.used
                    """, (user_id, week, metric, new_used))
                    results[metric] = {
                        "used": new_used,
                        "reserved": amount,
                        "limit": limit,
                        "remaining": max(0.0, limit - new_used),
                    }
                db.commit()
            except Exception:
                db.rollback()
                raise
        return {"week_start": week, "resources": results}

    def summary(self, user_id: str, at: float | None = None) -> dict:
        week = self.week_start(at)
        with self._connect() as db:
            rows = db.execute("""
                SELECT metric,used FROM mesh_quota_usage
                WHERE user_id=? AND week_start=?
            """, (user_id, week)).fetchall()
        used = {row["metric"]: float(row["used"]) for row in rows}
        resources = {}
        for metric, limit in self.limits.items():
            current = used.get(metric, 0.0)
            resources[metric] = {
                "used": current,
                "limit": float(limit),
                "remaining": max(0.0, float(limit) - current),
            }
        return {"week_start": week, "reset": "next Monday 00:00 UTC", "resources": resources}
