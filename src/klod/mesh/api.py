from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from klod.mesh.auth import AccountExists, AuthStore, AuthenticationError
from klod.mesh.providers import list_providers
from klod.mesh.quotas import QuotaExceeded, QuotaLedger
from klod.mesh.registry import ResourceRegistry
from klod.mesh.runtime import TaskError, TaskStore
from klod.mesh.scheduler import SchedulingError, TaskScheduler
from klod.mesh.workloads import WorkloadError, required_vram_gib, validate_workload

DATABASE = os.getenv("GPU_MESH_DATABASE_PATH", "./data/gpu_mesh.sqlite3")
SESSION_TTL = int(os.getenv("GPU_MESH_SESSION_TTL_SECONDS", "86400"))
HEARTBEAT_TTL = int(os.getenv("GPU_MESH_HEARTBEAT_TTL_SECONDS", "120"))

auth_store = AuthStore(DATABASE, SESSION_TTL)
registry = ResourceRegistry(DATABASE, HEARTBEAT_TTL)
quota_ledger = QuotaLedger(DATABASE)
scheduler = TaskScheduler()
task_store = TaskStore(DATABASE)


class JobStore:
    def __init__(self, database_path: str):
        self.database_path = database_path
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS mesh_jobs (
                    job_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
            """)
            db.execute("CREATE INDEX IF NOT EXISTS idx_mesh_jobs_owner ON mesh_jobs(owner_id, created_at DESC)")

    def _connect(self):
        db = sqlite3.connect(self.database_path, timeout=20)
        db.row_factory = sqlite3.Row
        return db

    def save(self, job: dict[str, Any]) -> None:
        with self._connect() as db:
            db.execute("""
                INSERT INTO mesh_jobs(job_id,owner_id,status,payload_json,created_at)
                VALUES(?,?,?,?,?)
            """, (job["job_id"], job["owner_id"], job["status"],
                  json.dumps(job, separators=(",", ":")), float(job["created_at"])))

    def get(self, job_id: str, owner_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT payload_json FROM mesh_jobs WHERE job_id=? AND owner_id=?",
                (job_id, owner_id),
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def update(self, job: dict[str, Any]) -> bool:
        with self._connect() as db:
            result = db.execute("""
                UPDATE mesh_jobs SET status=?,payload_json=?
                WHERE job_id=? AND owner_id=?
            """, (job["status"], json.dumps(job, separators=(",", ":")),
                  job["job_id"], job["owner_id"]))
        return result.rowcount == 1

    def list(self, owner_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("""
                SELECT payload_json FROM mesh_jobs
                WHERE owner_id=? ORDER BY created_at DESC LIMIT ?
            """, (owner_id, limit)).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]


job_store = JobStore(DATABASE)
router = APIRouter(tags=["GPU Mesh"])

WORKLOADS = {
    "cpu-sha256",
    "gpu-matmul",
    "gpu-mandelbrot",
}


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=1024)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class WorkerRegisterRequest(BaseModel):
    provider_id: str = Field(default="volunteer-worker", min_length=1, max_length=80)
    cpu_cores: float = Field(gt=0, le=4096)
    ram_gib: float = Field(gt=0, le=65536)
    storage_gib: float = Field(ge=0, le=1048576)
    gpus: list[dict[str, Any]] = Field(default_factory=list, max_length=16)
    shared: bool = False


class WorkerHeartbeatRequest(BaseModel):
    cpu_available: float = Field(ge=0, le=4096)
    ram_available_gib: float = Field(ge=0, le=65536)
    storage_available_gib: float = Field(ge=0, le=1048576)
    gpus: list[dict[str, Any]] = Field(default_factory=list, max_length=16)


class JobRequest(BaseModel):
    workload: str = Field(min_length=1, max_length=80)
    task_count: int = Field(ge=1, le=1000)
    payload: dict[str, Any] = Field(default_factory=dict)
    requires_gpu: bool | None = None
    min_vram_gib_per_task: float = Field(default=1.0, ge=0, le=512)
    cpu_cores_per_task: float = Field(default=1.0, gt=0, le=256)
    ram_gib_per_task: float = Field(default=1.0, gt=0, le=4096)
    max_runtime_seconds_per_task: int = Field(default=300, ge=1, le=3600)


class TaskResultRequest(BaseModel):
    result: dict[str, Any]


class TaskFailureRequest(BaseModel):
    error_code: str = Field(default="worker_error", min_length=1, max_length=80)



def _bearer_value(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token or len(token) > 512:
        return None
    return token.strip()


def require_user(authorization: str | None = Header(default=None)) -> dict[str, str]:
    token = _bearer_value(authorization)
    user = auth_store.resolve_session(token) if token else None
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Authentication required",
                            headers={"WWW-Authenticate": "Bearer"})
    return user


@router.get("/providers")
def providers():
    return {"providers": list_providers()}


def _enforce_auth_rate_limit(request: Request, scope: str,
                             identifier: str | None = None) -> None:
    remote = request.client.host if request.client else "unknown"
    candidates = [(f"{scope}:ip:{hashlib.sha256(remote.encode()).hexdigest()}", 8, 600)]
    if identifier:
        normalized = identifier.strip().lower()
        candidates.append((f"{scope}:id:{hashlib.sha256(normalized.encode()).hexdigest()}", 6, 600))
    for bucket, limit, window in candidates:
        retry_after = auth_store.consume_rate_limit(bucket, limit, window)
        if retry_after:
            raise HTTPException(
                status_code=429,
                detail="Too many authentication attempts. Try again later.",
                headers={"Retry-After": str(retry_after)},
            )


@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register_account(payload: RegisterRequest, http_request: Request):
    _enforce_auth_rate_limit(http_request, "register")
    try:
        result = auth_store.register(payload.email, payload.password)
    except AccountExists as exc:
        raise HTTPException(status_code=409, detail="Account already exists") from exc
    except AuthenticationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"created": True, **result}


@router.post("/auth/login")
def login(payload: LoginRequest, http_request: Request):
    _enforce_auth_rate_limit(http_request, "login", payload.email)
    try:
        return auth_store.login(payload.email, payload.password)
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail="Invalid email or password",
                            headers={"WWW-Authenticate": "Bearer"}) from exc


@router.post("/auth/logout", dependencies=[Depends(require_user)])
def logout(authorization: str | None = Header(default=None)):
    token = _bearer_value(authorization)
    revoked = auth_store.revoke_session(token or "")
    return {"revoked": revoked}


@router.get("/account")
def account(user: dict[str, str] = Depends(require_user)):
    return {"user_id": user["user_id"], "email": user["email"]}


@router.get("/quota")
def quota(user: dict[str, str] = Depends(require_user)):
    return quota_ledger.summary(user["user_id"])


@router.get("/workers")
def workers(user: dict[str, str] = Depends(require_user)):
    return {"workers": registry.list_owned(user["user_id"])}


@router.post("/workers", status_code=status.HTTP_201_CREATED)
def register_worker(request: WorkerRegisterRequest,
                    user: dict[str, str] = Depends(require_user)):
    if request.provider_id != "volunteer-worker":
        raise HTTPException(status_code=422,
                            detail="This provider requires an implemented, authorized provider adapter")
    try:
        registered = registry.register(
            owner_id=user["user_id"],
            provider_id=request.provider_id,
            cpu_cores=request.cpu_cores,
            ram_gib=request.ram_gib,
            storage_gib=request.storage_gib,
            gpus=request.gpus,
            shared=request.shared,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        **registered,
        "warning": "Save worker_token now. It is shown once and cannot be retrieved.",
        "shared": request.shared,
    }


@router.post("/workers/{node_id}/heartbeat")
def worker_heartbeat(node_id: str, request: WorkerHeartbeatRequest,
                     worker_token: str | None = Header(default=None, alias="X-Worker-Token")):
    try:
        accepted = registry.heartbeat(
            node_id=node_id,
            worker_token=worker_token or "",
            owner_id=None,
            cpu_available=request.cpu_available,
            ram_available_gib=request.ram_available_gib,
            storage_available_gib=request.storage_available_gib,
            gpus=request.gpus,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not accepted:
        raise HTTPException(status_code=401, detail="Worker token rejected")
    return {"accepted": True, "heartbeat_ttl_seconds": HEARTBEAT_TTL}


@router.delete("/workers/{node_id}")
def revoke_worker(node_id: str, user: dict[str, str] = Depends(require_user)):
    if not registry.revoke(node_id, user["user_id"]):
        raise HTTPException(status_code=404, detail="Worker not found")
    return {"revoked": True, "node_id": node_id}


@router.get("/resources")
def resources(user: dict[str, str] = Depends(require_user)):
    nodes = registry.list_schedulable(user["user_id"], include_shared=True)
    gpu_devices = []
    cpu_total = cpu_available = ram_total = ram_available = 0.0
    for node in nodes:
        cpu_total += float(node["cpu_total"])
        cpu_available += float(node["cpu_available"])
        ram_total += float(node["ram_total_gib"])
        ram_available += float(node["ram_available_gib"])
        for gpu in node["gpus"]:
            gpu_devices.append({
                "node_id": node["node_id"],
                "provider_id": node["provider_id"],
                **gpu,
            })
    return {
        "online_nodes": len(nodes),
        "cpu": {"allocatable_cores": cpu_total, "available_cores": cpu_available},
        "ram": {"allocatable_gib": ram_total, "available_gib": ram_available},
        "gpu_devices": gpu_devices,
        "gpu_vram_aggregation": "Per-device only; VRAM from different GPUs is never reported as one address space.",
    }


def _refresh_job_state(job_id: str, owner_id: str) -> dict[str, Any] | None:
    job = job_store.get(job_id, owner_id)
    if job is None:
        return None
    summary = task_store.summary(job_id, owner_id)
    job.update(summary)
    if job.get("queued_tasks", 0) and summary["execution_status"] == "completed":
        job["execution_status"] = "partially_completed"
    job["execution_started"] = bool(job.get("execution_started") or summary["execution_started"])
    job_store.update(job)
    return job


@router.post("/jobs", status_code=status.HTTP_201_CREATED)
def create_job(request: JobRequest, user: dict[str, str] = Depends(require_user)):
    if request.workload not in WORKLOADS:
        raise HTTPException(status_code=422, detail="Unsupported executable workload")
    try:
        payload = validate_workload(request.workload, request.payload)
        required_vram = required_vram_gib(request.workload, payload)
    except WorkloadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    requires_gpu = required_vram > 0
    if request.requires_gpu is not None and request.requires_gpu != requires_gpu:
        raise HTTPException(status_code=422, detail="GPU requirement is fixed by the selected workload")
    min_vram = max(required_vram, request.min_vram_gib_per_task) if requires_gpu else 0.0
    nodes = registry.list_schedulable(user["user_id"], include_shared=True)
    try:
        plan = scheduler.plan(
            owner_id=user["user_id"],
            workload=request.workload,
            task_count=request.task_count,
            nodes=nodes,
            requires_gpu=requires_gpu,
            min_vram_gib_per_task=min_vram,
            cpu_cores_per_task=request.cpu_cores_per_task,
            ram_gib_per_task=request.ram_gib_per_task,
            max_runtime_seconds_per_task=request.max_runtime_seconds_per_task,
        )
    except SchedulingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    scheduled = int(plan["scheduled_tasks"])
    quota_reservation = None
    task_records: list[dict[str, Any]] = []
    reserved_ids: list[str] = []
    if scheduled:
        duration = scheduled * request.max_runtime_seconds_per_task
        amounts = {
            "cpu_core_seconds": duration * request.cpu_cores_per_task,
            "ram_gib_seconds": duration * request.ram_gib_per_task,
        }
        if requires_gpu:
            amounts["gpu_seconds"] = duration
            amounts["vram_gib_seconds"] = duration * min_vram
        try:
            quota_reservation = quota_ledger.reserve(user["user_id"], amounts)
            task_records = task_store.create_from_plan(plan, payload)
            for record in task_records:
                accepted = registry.reserve_capacity(
                    task_id=record["task_id"],
                    node_id=record["node_id"],
                    gpu_index=record["gpu_index"],
                    cpu_cores=record["cpu_cores"],
                    ram_gib=record["ram_gib"],
                    vram_gib=record["vram_gib"],
                    ttl_seconds=min(86400, max(600, record["max_runtime_seconds"] + 300)),
                )
                if not accepted:
                    raise TaskError("Worker capacity changed during reservation; refresh resources and retry")
                reserved_ids.append(record["task_id"])
        except QuotaExceeded as exc:
            for task_id in reserved_ids:
                registry.release_capacity(task_id)
            task_store.delete_job(plan["job_id"], user["user_id"])
            raise HTTPException(status_code=429, detail={
                "error": "weekly_quota_exceeded",
                "metric": exc.metric,
                "used": exc.used,
                "requested": exc.requested,
                "limit": exc.limit,
            }) from exc
        except (TaskError, ValueError) as exc:
            for task_id in reserved_ids:
                registry.release_capacity(task_id)
            task_store.delete_job(plan["job_id"], user["user_id"])
            if quota_reservation:
                quota_ledger.release(
                    user["user_id"],
                    {metric: item["reserved"] for metric, item in quota_reservation["resources"].items()},
                )
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception:
            for task_id in reserved_ids:
                registry.release_capacity(task_id)
            task_store.delete_job(plan["job_id"], user["user_id"])
            if quota_reservation:
                quota_ledger.release(
                    user["user_id"],
                    {metric: item["reserved"] for metric, item in quota_reservation["resources"].items()},
                )
            raise

    plan["quota_reservation"] = quota_reservation
    plan["execution_started"] = False
    plan["execution_status"] = "dispatched" if scheduled else "queued"
    plan["execution_note"] = (
        "Allowlisted task manifests are assigned to authenticated workers. "
        "Workers verify the per-node HMAC, lease and fixed device before executing a built-in workload. "
        "No arbitrary user-supplied code is accepted."
    )
    plan["task_ids"] = [record["task_id"] for record in task_records]
    plan["task_summary"] = task_store.summary(plan["job_id"], user["user_id"])
    job_store.save(plan)
    return plan


def _require_worker(node_id: str, worker_token: str | None) -> None:
    if not registry.authenticate_worker(node_id, worker_token or ""):
        raise HTTPException(status_code=401, detail="Worker token rejected")


@router.post("/workers/{node_id}/tasks/claim")
def claim_worker_task(
    node_id: str,
    worker_token: str | None = Header(default=None, alias="X-Worker-Token"),
):
    _require_worker(node_id, worker_token)
    try:
        claimed = task_store.claim(node_id, worker_token or "")
    except TaskError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return {"task": claimed}


@router.post("/workers/{node_id}/tasks/{task_id}/start")
def start_worker_task(
    node_id: str,
    task_id: str,
    worker_token: str | None = Header(default=None, alias="X-Worker-Token"),
    lease_token: str | None = Header(default=None, alias="X-Task-Lease"),
):
    _require_worker(node_id, worker_token)
    try:
        return task_store.start(task_id, node_id, lease_token or "")
    except TaskError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/workers/{node_id}/tasks/{task_id}/renew")
def renew_worker_task(
    node_id: str,
    task_id: str,
    worker_token: str | None = Header(default=None, alias="X-Worker-Token"),
    lease_token: str | None = Header(default=None, alias="X-Task-Lease"),
):
    _require_worker(node_id, worker_token)
    try:
        return task_store.renew(task_id, node_id, lease_token or "")
    except TaskError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/workers/{node_id}/tasks/{task_id}/complete")
def complete_worker_task(
    node_id: str,
    task_id: str,
    request: TaskResultRequest,
    worker_token: str | None = Header(default=None, alias="X-Worker-Token"),
    lease_token: str | None = Header(default=None, alias="X-Task-Lease"),
):
    _require_worker(node_id, worker_token)
    try:
        result = task_store.complete(task_id, node_id, lease_token or "", request.result)
    except TaskError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if result.get("completed") or result.get("cancelled"):
        registry.release_capacity(task_id)
    return result


@router.post("/workers/{node_id}/tasks/{task_id}/fail")
def fail_worker_task(
    node_id: str,
    task_id: str,
    request: TaskFailureRequest,
    worker_token: str | None = Header(default=None, alias="X-Worker-Token"),
    lease_token: str | None = Header(default=None, alias="X-Task-Lease"),
):
    _require_worker(node_id, worker_token)
    try:
        result = task_store.fail(task_id, node_id, lease_token or "", request.error_code)
    except TaskError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if result["state"] in ("failed", "cancelled"):
        registry.release_capacity(task_id)
    return result


@router.get("/jobs/{job_id}/results")
def job_results(job_id: str, user: dict[str, str] = Depends(require_user)):
    job = job_store.get(job_id, user["user_id"])
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job_id,
        "summary": task_store.summary(job_id, user["user_id"]),
        "tasks": task_store.list_results(job_id, user["user_id"]),
    }


@router.get("/jobs")
def jobs(limit: int = 50, user: dict[str, str] = Depends(require_user)):
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 100")
    items = job_store.list(user["user_id"], limit)
    for item in items:
        item.update(task_store.summary(item["job_id"], user["user_id"]))
    return {"jobs": items}


@router.get("/jobs/{job_id}")
def job(job_id: str, user: dict[str, str] = Depends(require_user)):
    result = job_store.get(job_id, user["user_id"])
    if result is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return result



@router.delete("/jobs/{job_id}")
def cancel_job(job_id: str, user: dict[str, str] = Depends(require_user)):
    result = job_store.get(job_id, user["user_id"])
    if result is None:
        raise HTTPException(status_code=404, detail="Job not found")
    before = task_store.summary(job_id, user["user_id"])
    cancelled = task_store.cancel_job(job_id, user["user_id"])
    for task_id in cancelled["releasable_task_ids"]:
        registry.release_capacity(task_id)

    releasable_count = before["queued"] + before["leased"]
    released = None
    reservation = result.get("quota_reservation")
    if reservation and releasable_count:
        scale = releasable_count / max(1, int(result.get("scheduled_tasks", 1)))
        amounts = {
            metric: float(item["reserved"]) * scale
            for metric, item in reservation.get("resources", {}).items()
            if float(item.get("reserved", 0)) > 0
        }
        if amounts:
            released = quota_ledger.release(user["user_id"], amounts)

    result["queued_cancelled"] = int(result.get("queued_tasks", 0))
    result["queued_tasks"] = 0
    result["status"] = "cancellation_requested"
    result["quota_release"] = released
    result.update(task_store.summary(job_id, user["user_id"]))
    if result["execution_status"] == "planning_only":
        result["execution_status"] = "cancelled"
    job_store.update(result)
    return {
        "cancel_requested": True,
        "tasks_cancelled": cancelled["cancelled"],
        "running_tasks_stop_requested": before["running"],
        "quota_released": bool(released),
        "job_id": job_id,
    }
