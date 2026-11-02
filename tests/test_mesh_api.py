from fastapi.testclient import TestClient

from klod import api as core_api
from klod.mesh import api as mesh_api
from klod.mesh.auth import AuthStore
from klod.mesh.quotas import QuotaLedger
from klod.mesh.registry import ResourceRegistry
from klod.mesh.api import JobStore
from klod.mesh.runtime import TaskStore
from klod.mesh.workloads import execute_workload


PASSWORD = "GPU-Mesh-Passphrase-2026"


def configure_mesh(tmp_path, monkeypatch):
    database = str(tmp_path / "mesh.sqlite3")
    monkeypatch.setattr(mesh_api, "auth_store", AuthStore(database))
    monkeypatch.setattr(mesh_api, "registry", ResourceRegistry(database))
    monkeypatch.setattr(mesh_api, "quota_ledger", QuotaLedger(database))
    monkeypatch.setattr(mesh_api, "job_store", JobStore(database))
    monkeypatch.setattr(mesh_api, "task_store", TaskStore(database))
    return TestClient(core_api.app)


def create_account(client):
    created = client.post("/v1/mesh/auth/register", json={
        "email": "mesh@example.com",
        "password": PASSWORD,
    })
    assert created.status_code == 201
    login = client.post("/v1/mesh/auth/login", json={
        "email": "mesh@example.com",
        "password": PASSWORD,
    })
    assert login.status_code == 200
    return login.json()["access_token"]


def test_mesh_auth_and_resources_are_session_protected(tmp_path, monkeypatch):
    client = configure_mesh(tmp_path, monkeypatch)
    assert client.get("/v1/mesh/resources").status_code == 401
    assert client.get("/v1/mesh/providers").status_code == 200
    token = create_account(client)
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/v1/mesh/account", headers=headers).status_code == 200
    assert client.get("/v1/mesh/resources", headers=headers).status_code == 200


def test_worker_heartbeat_uses_node_token_without_account_session(tmp_path, monkeypatch):
    client = configure_mesh(tmp_path, monkeypatch)
    token = create_account(client)
    headers = {"Authorization": f"Bearer {token}"}
    registered = client.post("/v1/mesh/workers", headers=headers, json={
        "provider_id": "volunteer-worker",
        "cpu_cores": 4,
        "ram_gib": 8,
        "storage_gib": 0,
        "gpus": [{
            "name": "Test GPU",
            "total_vram_gib": 8,
            "available_vram_gib": 7,
        }],
        "shared": False,
    })
    assert registered.status_code == 201
    node = registered.json()
    heartbeat = client.post(
        f"/v1/mesh/workers/{node['node_id']}/heartbeat",
        headers={"X-Worker-Token": node["worker_token"]},
        json={
            "cpu_available": 3,
            "ram_available_gib": 6,
            "storage_available_gib": 0,
            "gpus": [{
                "name": "Test GPU",
                "total_vram_gib": 8,
                "available_vram_gib": 6,
            }],
        },
    )
    assert heartbeat.status_code == 200
    assert heartbeat.json()["accepted"] is True


def test_job_dispatch_reserves_weekly_capacity_and_cancels_pending_tasks(tmp_path, monkeypatch):
    client = configure_mesh(tmp_path, monkeypatch)
    token = create_account(client)
    headers = {"Authorization": f"Bearer {token}"}
    worker = client.post("/v1/mesh/workers", headers=headers, json={
        "provider_id": "volunteer-worker",
        "cpu_cores": 4,
        "ram_gib": 8,
        "storage_gib": 0,
        "gpus": [{
            "name": "Single Device",
            "total_vram_gib": 8,
            "available_vram_gib": 8,
        }],
        "shared": True,
    })
    assert worker.status_code == 201
    planned = client.post("/v1/mesh/jobs", headers=headers, json={
        "workload": "gpu-matmul",
        "payload": {"matrix_size": 64, "seed": 7},
        "task_count": 1,
        "requires_gpu": True,
        "min_vram_gib_per_task": 1,
        "cpu_cores_per_task": 1,
        "ram_gib_per_task": 2,
        "max_runtime_seconds_per_task": 60,
    })
    assert planned.status_code == 201
    result = planned.json()
    assert result["status"] == "dispatched"
    assert result["scheduled_tasks"] == 1
    assert result["execution_started"] is False
    assert result["execution_status"] == "dispatched"
    assert len(result["task_ids"]) == 1
    assert client.get("/v1/mesh/jobs", headers=headers).json()["jobs"]
    cancelled = client.delete(f"/v1/mesh/jobs/{result['job_id']}", headers=headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["pending_tasks_cancelled"] == 1
    assert cancelled.json()["quota_released"] is True
    refreshed = client.get("/v1/mesh/jobs/" + result["job_id"], headers=headers).json()
    assert refreshed["execution_status"] == "cancelled"
    quota = client.get("/v1/mesh/quota", headers=headers).json()
    assert quota["resources"]["gpu_seconds"]["used"] == 0


def test_dashboard_is_served_with_security_headers(tmp_path, monkeypatch):
    client = configure_mesh(tmp_path, monkeypatch)
    response = client.get("/mesh")
    assert response.status_code == 200
    assert "GPU MESH" in response.text
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]



def test_worker_claims_executes_and_completes_server_verified_cpu_task(tmp_path, monkeypatch):
    client = configure_mesh(tmp_path, monkeypatch)
    account_token = create_account(client)
    account_headers = {"Authorization": f"Bearer {account_token}"}
    registered = client.post("/v1/mesh/workers", headers=account_headers, json={
        "provider_id": "volunteer-worker",
        "cpu_cores": 2,
        "ram_gib": 4,
        "storage_gib": 0,
        "gpus": [],
        "shared": True,
    })
    assert registered.status_code == 201
    worker = registered.json()
    worker_headers = {"X-Worker-Token": worker["worker_token"]}
    heartbeat = client.post(
        f"/v1/mesh/workers/{worker['node_id']}/heartbeat",
        headers=worker_headers,
        json={
            "cpu_available": 2,
            "ram_available_gib": 4,
            "storage_available_gib": 0,
            "gpus": [],
        },
    )
    assert heartbeat.status_code == 200

    created = client.post("/v1/mesh/jobs", headers=account_headers, json={
        "workload": "cpu-sha256",
        "payload": {"text": "end-to-end", "iterations": 32},
        "task_count": 1,
        "requires_gpu": False,
        "min_vram_gib_per_task": 0,
        "cpu_cores_per_task": 1,
        "ram_gib_per_task": 1,
        "max_runtime_seconds_per_task": 60,
    })
    assert created.status_code == 201
    job = created.json()
    claimed = client.post(
        f"/v1/mesh/workers/{worker['node_id']}/tasks/claim",
        headers=worker_headers,
    )
    assert claimed.status_code == 200
    task = claimed.json()["task"]
    assert task["manifest"]["job_id"] == job["job_id"]
    assert task["manifest"]["node_id"] == worker["node_id"]

    started = client.post(
        f"/v1/mesh/workers/{worker['node_id']}/tasks/{task['manifest']['task_id']}/start",
        headers={**worker_headers, "X-Task-Lease": task["lease_token"]},
    )
    assert started.status_code == 200
    result = execute_workload("cpu-sha256", task["manifest"]["payload"])
    completed = client.post(
        f"/v1/mesh/workers/{worker['node_id']}/tasks/{task['manifest']['task_id']}/complete",
        headers={**worker_headers, "X-Task-Lease": task["lease_token"]},
        json={"result": result},
    )
    assert completed.status_code == 200
    assert completed.json()["completed"] is True

    results = client.get(f"/v1/mesh/jobs/{job['job_id']}/results", headers=account_headers)
    assert results.status_code == 200
    assert results.json()["summary"]["execution_status"] == "completed"
    assert results.json()["tasks"][0]["result"]["result_validation"] == "server-verified"


def test_worker_cannot_claim_another_workers_tasks_with_wrong_token(tmp_path, monkeypatch):
    client = configure_mesh(tmp_path, monkeypatch)
    token = create_account(client)
    headers = {"Authorization": f"Bearer {token}"}
    registered = client.post("/v1/mesh/workers", headers=headers, json={
        "provider_id": "volunteer-worker",
        "cpu_cores": 2,
        "ram_gib": 4,
        "storage_gib": 0,
        "gpus": [],
        "shared": False,
    })
    node_id = registered.json()["node_id"]
    rejected = client.post(
        f"/v1/mesh/workers/{node_id}/tasks/claim",
        headers={"X-Worker-Token": "invalid-token"},
    )
    assert rejected.status_code == 401


def test_job_rejects_gpu_requirement_mismatch_and_unknown_code_payload(tmp_path, monkeypatch):
    client = configure_mesh(tmp_path, monkeypatch)
    token = create_account(client)
    headers = {"Authorization": f"Bearer {token}"}
    mismatch = client.post("/v1/mesh/jobs", headers=headers, json={
        "workload": "cpu-sha256",
        "payload": {"text": "x", "iterations": 1},
        "task_count": 1,
        "requires_gpu": True,
    })
    assert mismatch.status_code == 422
    arbitrary = client.post("/v1/mesh/jobs", headers=headers, json={
        "workload": "python",
        "payload": {"code": "import os; os.system('id')"},
        "task_count": 1,
    })
    assert arbitrary.status_code == 422
