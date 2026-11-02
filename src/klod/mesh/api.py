from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field

from klod.mesh.auth import AccountExists, AuthStore, AuthenticationError
from klod.mesh.providers import list_providers
from klod.mesh.quotas import QuotaExceeded, QuotaLedger
from klod.mesh.registry import ResourceRegistry
from klod.mesh.scheduler import SchedulingError, TaskScheduler

DATABASE = os.getenv("GPU_MESH_DATABASE_PATH", "./data/gpu_mesh.sqlite3")
SESSION_TTL = int(os.getenv("GPU_MESH_SESSION_TTL_SECONDS", "86400"))
HEARTBEAT_TTL = int(os.getenv("GPU_MESH_HEARTBEAT_TTL_SECONDS", "120"))

auth_store = AuthStore(DATABASE, SESSION_TTL)
registry = ResourceRegistry(DATABASE, HEARTBEAT_TTL)
quota_ledger = QuotaLedger(DATABASE)
scheduler = TaskScheduler()


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
    "independent-render-frames",
    "batch-inference",
    "dataset-transform",
    "evaluation",
}


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=1024)


class LoginRequest(BaseModel):
    email: EmailStr
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
    requires_gpu: bool = True
    min_vram_gib_per_task: float = Field(default=1.0, ge=0, le=512)
    cpu_cores_per_task: float = Field(default=1.0, gt=0, le=256)
    ram_gib_per_task: float = Field(default=1.0, gt=0, le=4096)
    max_runtime_seconds_per_task: int = Field(default=300, ge=1, le=3600)


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


@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register_account(request: RegisterRequest):
    try:
        result = auth_store.register(str(request.email), request.password)
    except AccountExists as exc:
        raise HTTPException(status_code=409, detail="Account already exists") from exc
    except AuthenticationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"created": True, **result}


@router.post("/auth/login")
def login(request: LoginRequest):
    try:
        return auth_store.login(str(request.email), request.password)
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
                     worker_token: str | None = Header(default=None, alias="X-Worker-Token"),
                     user: dict[str, str] = Depends(require_user)):
    try:
        accepted = registry.heartbeat(
            node_id=node_id,
            worker_token=worker_token or "",
            owner_id=user["user_id"],
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


@router.post("/jobs", status_code=status.HTTP_201_CREATED)
def create_job(request: JobRequest, user: dict[str, str] = Depends(require_user)):
    if request.workload not in WORKLOADS:
        raise HTTPException(status_code=422, detail="Unsupported workload type")
    if request.requires_gpu and request.min_vram_gib_per_task <= 0:
        raise HTTPException(status_code=422, detail="GPU jobs require positive VRAM per device")
    nodes = registry.list_schedulable(user["user_id"], include_shared=True)
    try:
        plan = scheduler.plan(
            owner_id=user["user_id"],
            workload=request.workload,
            task_count=request.task_count,
            nodes=nodes,
            requires_gpu=request.requires_gpu,
            min_vram_gib_per_task=request.min_vram_gib_per_task,
            cpu_cores_per_task=request.cpu_cores_per_task,
            ram_gib_per_task=request.ram_gib_per_task,
            max_runtime_seconds_per_task=request.max_runtime_seconds_per_task,
        )
    except SchedulingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    scheduled = int(plan["scheduled_tasks"])
    quota_reservation = None
    if scheduled:
        duration = scheduled * request.max_runtime_seconds_per_task
        amounts = {
            "cpu_core_seconds": duration * request.cpu_cores_per_task,
            "ram_gib_seconds": duration * request.ram_gib_per_task,
        }
        if request.requires_gpu:
            amounts["gpu_seconds"] = duration
            amounts["vram_gib_seconds"] = duration * request.min_vram_gib_per_task
        try:
            quota_reservation = quota_ledger.reserve(user["user_id"], amounts)
        except QuotaExceeded as exc:
            raise HTTPException(status_code=429, detail={
                "error": "weekly_quota_exceeded",
                "metric": exc.metric,
                "used": exc.used,
                "requested": exc.requested,
                "limit": exc.limit,
            }) from exc

    plan["quota_reservation"] = quota_reservation
    plan["execution_started"] = False
    plan["execution_status"] = "planning_only"
    plan["execution_note"] = (
        "The scheduler generated a resource plan. No remote process was started. "
        "A sandboxed, attested worker execution protocol is a separate deployment stage."
    )
    job_store.save(plan)
    return plan


@router.get("/jobs")
def jobs(limit: int = 50, user: dict[str, str] = Depends(require_user)):
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 100")
    return {"jobs": job_store.list(user["user_id"], limit)}


@router.get("/jobs/{job_id}")
def job(job_id: str, user: dict[str, str] = Depends(require_user)):
    result = job_store.get(job_id, user["user_id"])
    if result is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return result
