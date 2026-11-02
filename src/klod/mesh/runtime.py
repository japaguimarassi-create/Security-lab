from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any


MAX_RESULT_BYTES = 65536
MAX_TASK_ATTEMPTS = 3


def _json_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _matches_integer(value: Any, expected: int) -> bool:
    if isinstance(value, bool):
        return False
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return False
    return parsed == value and parsed == int(expected)


class TaskError(ValueError):
    pass


class TaskStore:
    def __init__(self, database_path: str):
        self.database_path = str(database_path)
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS mesh_tasks (
                    task_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    workload TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    gpu_index INTEGER,
                    requires_gpu INTEGER NOT NULL,
                    cpu_cores REAL NOT NULL,
                    ram_gib REAL NOT NULL,
                    vram_gib REAL NOT NULL,
                    max_runtime_seconds INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    lease_hash TEXT,
                    lease_expires_at REAL,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    result_json TEXT,
                    error_code TEXT,
                    created_at REAL NOT NULL,
                    started_at REAL,
                    finished_at REAL
                )
            """)
            db.execute("CREATE INDEX IF NOT EXISTS idx_mesh_tasks_worker ON mesh_tasks(node_id,state,lease_expires_at,created_at)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_mesh_tasks_job ON mesh_tasks(job_id,owner_id,state)")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database_path, timeout=20, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def create_from_plan(self, plan: dict[str, Any], payload: dict[str, Any]) -> list[dict[str, Any]]:
        created = []
        now = time.time()
        task_index = 0
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                for assignment in plan.get("assignments", []):
                    node_id = assignment["node_id"]
                    gpu_devices = assignment.get("gpu_devices", [])
                    for offset in range(int(assignment["task_count"])):
                        gpu_index = int(gpu_devices[offset]["index"]) if plan["requires_gpu"] else None
                        task_payload = dict(payload)
                        if "seed" in task_payload:
                            task_payload["seed"] = int(task_payload["seed"]) + task_index
                        if "text" in task_payload and plan["workload"] == "cpu-sha256":
                            task_payload["text"] = f"{task_payload['text']}|task:{task_index}"
                        task_id = secrets.token_hex(16)
                        db.execute("""
                            INSERT INTO mesh_tasks(
                                task_id,job_id,owner_id,node_id,workload,payload_json,
                                gpu_index,requires_gpu,cpu_cores,ram_gib,vram_gib,
                                max_runtime_seconds,state,created_at
                            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """, (
                            task_id, plan["job_id"], plan["owner_id"], node_id,
                            plan["workload"], _json_bytes(task_payload).decode("utf-8"),
                            gpu_index, int(plan["requires_gpu"]),
                            float(assignment["cpu_cores_per_task"]),
                            float(assignment["ram_gib_per_task"]),
                            float(plan["min_vram_gib_per_task"]) if plan["requires_gpu"] else 0.0,
                            int(plan["max_runtime_seconds_per_task"]), "queued", now,
                        ))
                        created.append({
                            "task_id": task_id,
                            "node_id": node_id,
                            "gpu_index": gpu_index,
                            "task_index": task_index,
                            "cpu_cores": float(assignment["cpu_cores_per_task"]),
                            "ram_gib": float(assignment["ram_gib_per_task"]),
                            "vram_gib": float(plan["min_vram_gib_per_task"]) if plan["requires_gpu"] else 0.0,
                            "max_runtime_seconds": int(plan["max_runtime_seconds_per_task"]),
                        })
                        task_index += 1
                db.commit()
            except Exception:
                db.rollback()
                raise
        return created

    def create_pending_from_plan(self, plan: dict[str, Any], payload: dict[str, Any]) -> list[str]:
        pending_count = int(plan.get("queued_tasks", 0))
        if pending_count <= 0:
            return []
        start_index = int(plan.get("scheduled_tasks", 0))
        now = time.time()
        created = []
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                for offset in range(pending_count):
                    task_index = start_index + offset
                    task_payload = dict(payload)
                    if "seed" in task_payload:
                        task_payload["seed"] = int(task_payload["seed"]) + task_index
                    if "text" in task_payload and plan["workload"] == "cpu-sha256":
                        task_payload["text"] = f"{task_payload['text']}|task:{task_index}"
                    task_id = secrets.token_hex(16)
                    db.execute("""
                        INSERT INTO mesh_tasks(
                            task_id,job_id,owner_id,node_id,workload,payload_json,
                            gpu_index,requires_gpu,cpu_cores,ram_gib,vram_gib,
                            max_runtime_seconds,state,created_at
                        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        task_id, plan["job_id"], plan["owner_id"], "",
                        plan["workload"], _json_bytes(task_payload).decode("utf-8"),
                        None, int(plan["requires_gpu"]),
                        float(plan["cpu_cores_per_task"]),
                        float(plan["ram_gib_per_task"]),
                        float(plan["min_vram_gib_per_task"]) if plan["requires_gpu"] else 0.0,
                        int(plan["max_runtime_seconds_per_task"]), "queued", now,
                    ))
                    created.append(task_id)
                db.commit()
            except Exception:
                db.rollback()
                raise
        return created

    def recover_orphaned_tasks(self, job_id: str, owner_id: str,
                               active_node_ids: set[str] | list[str],
                               at: float | None = None) -> dict[str, list[str]]:
        now = time.time() if at is None else float(at)
        active = {str(node_id) for node_id in active_node_ids}
        requeued: list[str] = []
        cancelled: list[str] = []
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                rows = db.execute("""
                    SELECT task_id,node_id,state,lease_expires_at,cancel_requested
                    FROM mesh_tasks
                    WHERE job_id=? AND owner_id=? AND node_id<>''
                      AND state IN ('queued','leased','running')
                """, (job_id, owner_id)).fetchall()
                for row in rows:
                    node_is_active = row["node_id"] in active
                    lease_expired = (
                        row["lease_expires_at"] is None
                        or float(row["lease_expires_at"]) <= now
                    )
                    should_requeue = (
                        row["state"] == "queued" and not node_is_active
                    ) or (
                        row["state"] in ("leased", "running")
                        and not node_is_active and lease_expired
                    )
                    if should_requeue and row["cancel_requested"]:
                        db.execute("""
                            UPDATE mesh_tasks SET state='cancelled',lease_hash=NULL,
                                lease_expires_at=NULL,finished_at=?,error_code='cancelled_worker_offline'
                            WHERE task_id=?
                        """, (now, row["task_id"]))
                        cancelled.append(row["task_id"])
                    elif should_requeue:
                        db.execute("""
                            UPDATE mesh_tasks SET state='queued',node_id='',gpu_index=NULL,
                                lease_hash=NULL,lease_expires_at=NULL,error_code='worker_offline'
                            WHERE task_id=?
                        """, (row["task_id"],))
                        requeued.append(row["task_id"])
                db.commit()
            except Exception:
                db.rollback()
                raise
        return {"requeued": requeued, "cancelled": cancelled}

    def pending_for_job(self, job_id: str, owner_id: str,
                        limit: int = 1000) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("""
                SELECT task_id,workload,requires_gpu,cpu_cores,ram_gib,vram_gib,
                       max_runtime_seconds,attempts
                FROM mesh_tasks
                WHERE job_id=? AND owner_id=? AND node_id='' AND state='queued'
                ORDER BY created_at,task_id LIMIT ?
            """, (job_id, owner_id, limit)).fetchall()
        return [dict(row) for row in rows]

    def assign_pending(self, task_id: str, node_id: str,
                       gpu_index: int | None) -> bool:
        if not node_id or len(node_id) > 128:
            raise TaskError("Invalid target worker")
        if gpu_index is not None and (isinstance(gpu_index, bool) or int(gpu_index) < 0):
            raise TaskError("Invalid physical GPU index")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                result = db.execute("""
                    UPDATE mesh_tasks SET node_id=?,gpu_index=?
                    WHERE task_id=? AND node_id='' AND state='queued' AND cancel_requested=0
                """, (node_id, gpu_index, task_id))
                db.commit()
                return result.rowcount == 1
            except Exception:
                db.rollback()
                raise

    def claim(self, node_id: str, worker_token: str) -> dict[str, Any] | None:
        if not worker_token or len(worker_token) > 512:
            raise TaskError("Invalid worker token")
        now = time.time()
        lease_seconds = 360
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                db.execute("""
                    UPDATE mesh_tasks SET state='failed',error_code='lease_exhausted',
                        lease_hash=NULL,lease_expires_at=NULL,finished_at=?
                    WHERE node_id=? AND cancel_requested=0 AND attempts>=?
                      AND state IN ('leased','running') AND lease_expires_at<?
                """, (now, node_id, MAX_TASK_ATTEMPTS, now))
                row = db.execute("""
                    SELECT * FROM mesh_tasks
                    WHERE node_id=? AND cancel_requested=0 AND attempts<?
                    AND (
                        state='queued'
                        OR (state IN ('leased','running') AND lease_expires_at<?)
                    )
                    ORDER BY created_at,task_id
                    LIMIT 1
                """, (node_id, MAX_TASK_ATTEMPTS, now)).fetchone()
                if row is None:
                    db.commit()
                    return None
                attempt = int(row["attempts"]) + 1
                lease_token = secrets.token_urlsafe(32)
                lease_expires = now + max(lease_seconds, int(row["max_runtime_seconds"]) + 60)
                manifest = {
                    "version": 1,
                    "task_id": row["task_id"],
                    "job_id": row["job_id"],
                    "owner_id": row["owner_id"],
                    "node_id": node_id,
                    "workload": row["workload"],
                    "payload": json.loads(row["payload_json"]),
                    "device_index": row["gpu_index"],
                    "requires_gpu": bool(row["requires_gpu"]),
                    "cpu_cores": float(row["cpu_cores"]),
                    "ram_gib": float(row["ram_gib"]),
                    "vram_gib": float(row["vram_gib"]),
                    "max_runtime_seconds": int(row["max_runtime_seconds"]),
                    "attempt": attempt,
                    "lease_expires_at": int(lease_expires),
                }
                signature = hmac.new(worker_token.encode("utf-8"), _json_bytes(manifest), hashlib.sha256).hexdigest()
                db.execute("""
                    UPDATE mesh_tasks SET state='leased',attempts=?,lease_hash=?,
                        lease_expires_at=?,error_code=NULL
                    WHERE task_id=?
                """, (attempt, _token_hash(lease_token), lease_expires, row["task_id"]))
                db.commit()
                return {
                    "manifest": manifest,
                    "manifest_signature": signature,
                    "lease_token": lease_token,
                }
            except Exception:
                db.rollback()
                raise

    def _authorized_task(self, db: sqlite3.Connection, task_id: str,
                         node_id: str, lease_token: str,
                         allow_expired: bool = False) -> sqlite3.Row:
        if not lease_token or len(lease_token) > 512:
            raise TaskError("Invalid task lease")
        row = db.execute(
            "SELECT * FROM mesh_tasks WHERE task_id=? AND node_id=?",
            (task_id, node_id),
        ).fetchone()
        if row is None or not row["lease_hash"]:
            raise TaskError("Task lease not found")
        if not hmac.compare_digest(row["lease_hash"], _token_hash(lease_token)):
            raise TaskError("Task lease rejected")
        if not allow_expired and (
            row["lease_expires_at"] is None or float(row["lease_expires_at"]) < time.time()
        ):
            raise TaskError("Task lease expired")
        return row

    def start(self, task_id: str, node_id: str, lease_token: str) -> dict[str, Any]:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = self._authorized_task(db, task_id, node_id, lease_token)
                if row["state"] != "leased":
                    raise TaskError("Task is not in the leased state")
                if row["cancel_requested"]:
                    db.execute("UPDATE mesh_tasks SET state='cancelled',finished_at=? WHERE task_id=?",
                               (time.time(), task_id))
                    db.commit()
                    return {"started": False, "cancelled": True}
                now = time.time()
                db.execute("UPDATE mesh_tasks SET state='running',started_at=? WHERE task_id=?",
                           (now, task_id))
                db.commit()
                return {"started": True, "max_runtime_seconds": int(row["max_runtime_seconds"])}
            except Exception:
                db.rollback()
                raise

    def renew(self, task_id: str, node_id: str, lease_token: str) -> dict[str, Any]:
        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = self._authorized_task(
                    db, task_id, node_id, lease_token, allow_expired=True
                )
                if row["state"] not in ("leased", "running"):
                    raise TaskError("Task is no longer active")
                if row["cancel_requested"]:
                    db.commit()
                    return {"renewed": False, "cancel_requested": True}
                expires = now + max(360, int(row["max_runtime_seconds"]) + 60)
                db.execute("UPDATE mesh_tasks SET lease_expires_at=? WHERE task_id=?",
                           (expires, task_id))
                db.commit()
                return {"renewed": True, "cancel_requested": False, "lease_expires_at": int(expires)}
            except Exception:
                db.rollback()
                raise

    def complete(self, task_id: str, node_id: str, lease_token: str,
                 result: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(result, dict):
            raise TaskError("Task result must be a JSON object")
        try:
            encoded = _json_bytes(result)
        except (TypeError, ValueError) as exc:
            raise TaskError("Task result must contain finite JSON values") from exc
        if len(encoded) > MAX_RESULT_BYTES:
            raise TaskError("Task result exceeds 64 KiB")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = self._authorized_task(db, task_id, node_id, lease_token)
                if row["state"] != "running":
                    raise TaskError("Task is not running")
                if result.get("workload") != row["workload"]:
                    raise TaskError("Result workload does not match the task manifest")
                if str(row["workload"]) == "cpu-sha256":
                    payload = json.loads(row["payload_json"])
                    digest = hashlib.sha256(payload["text"].encode("utf-8")).digest()
                    for index in range(int(payload["iterations"])):
                        digest = hashlib.sha256(
                            digest + index.to_bytes(8, "big") + payload["text"].encode("utf-8")
                        ).digest()
                    if not hmac.compare_digest(digest.hex(), str(result.get("sha256", ""))):
                        raise TaskError("CPU result does not match deterministic verification")
                    if not _matches_integer(result.get("iterations"), int(payload["iterations"])):
                        raise TaskError("CPU result iteration count does not match the task manifest")
                    result["result_validation"] = "server-verified"
                    encoded = _json_bytes(result)
                    if len(encoded) > MAX_RESULT_BYTES:
                        raise TaskError("Task result exceeds 64 KiB after server verification")
                elif str(row["workload"]) in ("gpu-matmul", "gpu-mandelbrot"):
                    payload = json.loads(row["payload_json"])
                    digest = result.get("sha256")
                    if not isinstance(digest, str) or len(digest) != 64 or any(
                        char not in "0123456789abcdef" for char in digest.lower()
                    ):
                        raise TaskError("GPU result must include a hexadecimal SHA-256 digest")
                    if result.get("execution_device") != "cuda":
                        raise TaskError("GPU result must identify CUDA execution")
                    if result.get("result_validation") != "worker-reported-digest":
                        raise TaskError("GPU result must retain its worker-reported validation status")
                    if not _matches_integer(result.get("device_index"), int(row["gpu_index"])):
                        raise TaskError("GPU result device index does not match the task assignment")
                    if str(row["workload"]) == "gpu-matmul":
                        if not _matches_integer(result.get("matrix_size"), int(payload["matrix_size"])):
                            raise TaskError("GPU matrix result size does not match the task payload")
                    else:
                        for field in ("width", "height", "max_iterations"):
                            if not _matches_integer(result.get(field), int(payload[field])):
                                raise TaskError(f"GPU fractal result {field} does not match the task payload")
                    result["result_validation"] = "worker-reported"
                    encoded = _json_bytes(result)
                    if len(encoded) > MAX_RESULT_BYTES:
                        raise TaskError("GPU result exceeds 64 KiB")
                else:
                    raise TaskError("Unsupported task workload in result validation")
                now = time.time()
                if row["cancel_requested"]:
                    db.execute("""
                        UPDATE mesh_tasks SET state='cancelled',lease_hash=NULL,
                            lease_expires_at=NULL,finished_at=? WHERE task_id=?
                    """, (now, task_id))
                    db.commit()
                    return {
                        "completed": False, "cancelled": True,
                        "job_id": row["job_id"], "owner_id": row["owner_id"],
                    }
                db.execute("""
                    UPDATE mesh_tasks SET state='completed',result_json=?,
                        lease_hash=NULL,lease_expires_at=NULL,finished_at=?
                    WHERE task_id=?
                """, (encoded.decode("utf-8"), now, task_id))
                db.commit()
                return {
                    "completed": True, "cancelled": False,
                    "job_id": row["job_id"], "owner_id": row["owner_id"],
                }
            except Exception:
                db.rollback()
                raise

    def fail(self, task_id: str, node_id: str, lease_token: str,
             error_code: str) -> dict[str, Any]:
        safe_code = str(error_code)[:80] or "worker_error"
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = self._authorized_task(db, task_id, node_id, lease_token)
                if row["state"] not in ("leased", "running"):
                    raise TaskError("Task is not active")
                now = time.time()
                if row["cancel_requested"]:
                    state = "cancelled"
                elif int(row["attempts"]) >= MAX_TASK_ATTEMPTS:
                    state = "failed"
                else:
                    state = "queued"
                db.execute("""
                    UPDATE mesh_tasks SET state=?,error_code=?,lease_hash=NULL,
                        lease_expires_at=NULL,finished_at=?
                    WHERE task_id=?
                """, (state, safe_code, now if state in ("failed", "cancelled") else None, task_id))
                db.commit()
                return {
                    "failed": state == "failed",
                    "retrying": state == "queued",
                    "state": state,
                    "job_id": row["job_id"],
                    "owner_id": row["owner_id"],
                }
            except Exception:
                db.rollback()
                raise

    def cancel_job(self, job_id: str, owner_id: str) -> dict[str, Any]:
        now = time.time()
        releasable = []
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                rows = db.execute("""
                    SELECT task_id,node_id,state FROM mesh_tasks
                    WHERE job_id=? AND owner_id=? AND state IN ('queued','leased','running')
                """, (job_id, owner_id)).fetchall()
                for row in rows:
                    if row["state"] == "running":
                        db.execute("UPDATE mesh_tasks SET cancel_requested=1 WHERE task_id=?",
                                   (row["task_id"],))
                    else:
                        db.execute("""
                            UPDATE mesh_tasks SET state='cancelled',lease_hash=NULL,
                                lease_expires_at=NULL,finished_at=? WHERE task_id=?
                        """, (now, row["task_id"]))
                        releasable.append(row["task_id"])
                db.commit()
            except Exception:
                db.rollback()
                raise
        return {"cancelled": len(rows), "releasable_task_ids": releasable}

    def delete_job(self, job_id: str, owner_id: str) -> int:
        with self._connect() as db:
            result = db.execute(
                "DELETE FROM mesh_tasks WHERE job_id=? AND owner_id=?",
                (job_id, owner_id),
            )
        return result.rowcount

    def summary(self, job_id: str, owner_id: str) -> dict[str, Any]:
        with self._connect() as db:
            rows = db.execute("""
                SELECT state,COUNT(*) AS count,MAX(started_at) AS started,
                       SUM(cancel_requested) AS cancelling,
                       SUM(CASE WHEN node_id='' AND state='queued' THEN 1 ELSE 0 END) AS unassigned
                FROM mesh_tasks WHERE job_id=? AND owner_id=? GROUP BY state
            """, (job_id, owner_id)).fetchall()
        counts = {row["state"]: int(row["count"]) for row in rows}
        total = sum(counts.values())
        started = any(row["started"] is not None for row in rows)
        cancelling = any(int(row["cancelling"] or 0) > 0 for row in rows)
        unassigned = sum(int(row["unassigned"] or 0) for row in rows)
        assigned_queued = max(0, counts.get("queued", 0) - unassigned)
        completed = counts.get("completed", 0)
        failed = counts.get("failed", 0)
        running = counts.get("running", 0)
        leased = counts.get("leased", 0)
        cancelled = counts.get("cancelled", 0)

        if total and completed == total:
            state = "completed"
        elif running:
            state = "cancelling" if cancelling else "running"
        elif assigned_queued or leased:
            state = "dispatched"
        elif unassigned and completed:
            state = "partially_completed"
        elif unassigned and failed:
            state = "partially_failed"
        elif unassigned:
            state = "queued"
        elif failed:
            state = "failed" if failed == total else "partially_failed"
        elif cancelled:
            state = "cancelled" if cancelled == total else "partially_cancelled"
        else:
            state = "planning_only"
        return {
            "total_tasks": total,
            "completed": completed,
            "running": running,
            "leased": leased,
            "queued": assigned_queued,
            "unassigned": unassigned,
            "failed": failed,
            "cancelled": cancelled,
            "execution_started": started,
            "execution_status": state,
        }

    def list_results(self, job_id: str, owner_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("""
                SELECT task_id,node_id,workload,state,attempts,gpu_index,
                       result_json,error_code,created_at,started_at,finished_at
                FROM mesh_tasks WHERE job_id=? AND owner_id=?
                ORDER BY created_at,task_id
            """, (job_id, owner_id)).fetchall()
        return [{
            "task_id": row["task_id"],
            "node_id": row["node_id"],
            "workload": row["workload"],
            "state": row["state"],
            "attempts": row["attempts"],
            "gpu_index": row["gpu_index"],
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
            "error_code": row["error_code"],
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
        } for row in rows]
