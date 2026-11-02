from fastapi.testclient import TestClient

from klod import api as core_api
from klod.mesh import api as mesh_api
from klod.mesh.auth import AuthStore
from klod.mesh.quotas import QuotaLedger
from klod.mesh.registry import ResourceRegistry
from klod.mesh.api import JobStore


PASSWORD = "GPU-Mesh-Passphrase-2026"


def configure_mesh(tmp_path, monkeypatch):
    database = str(tmp_path / "mesh.sqlite3")
    monkeypatch.setattr(mesh_api, "auth_store", AuthStore(database))
    monkeypatch.setattr(mesh_api, "registry", ResourceRegistry(database))
    monkeypatch.setattr(mesh_api, "quota_ledger", QuotaLedger(database))
    monkeypatch.setattr(mesh_api, "job_store", JobStore(database))
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


def test_job_planning_reserves_weekly_capacity_but_does_not_execute(tmp_path, monkeypatch):
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
        "workload": "independent-render-frames",
        "task_count": 1,
        "requires_gpu": True,
        "min_vram_gib_per_task": 4,
        "cpu_cores_per_task": 1,
        "ram_gib_per_task": 2,
        "max_runtime_seconds_per_task": 60,
    })
    assert planned.status_code == 201
    result = planned.json()
    assert result["status"] == "planned"
    assert result["scheduled_tasks"] == 1
    assert result["execution_started"] is False
    assert result["execution_status"] == "planning_only"
    assert client.get("/v1/mesh/jobs", headers=headers).json()["jobs"]
    cancelled = client.delete(f"/v1/mesh/jobs/{result['job_id']}", headers=headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["quota_released"] is True
    assert client.get("/v1/mesh/jobs/{result['job_id']}", headers=headers).status_code == 404
    assert client.get("/v1/mesh/jobs/" + result["job_id"], headers=headers).json()["status"] == "cancelled"
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
