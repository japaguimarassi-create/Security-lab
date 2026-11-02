from fastapi.testclient import TestClient

from index import app
from klod.mesh import api as mesh_api
from klod.mesh.api import JobStore
from klod.mesh.auth import AuthStore
from klod.mesh.quotas import QuotaLedger
from klod.mesh.registry import ResourceRegistry
from klod.mesh.runtime import TaskStore


def test_vercel_entrypoint_serves_dashboard_and_mesh_health(tmp_path, monkeypatch):
    database = str(tmp_path / "vercel.sqlite3")
    monkeypatch.setattr(mesh_api, "auth_store", AuthStore(database))
    monkeypatch.setattr(mesh_api, "registry", ResourceRegistry(database))
    monkeypatch.setattr(mesh_api, "quota_ledger", QuotaLedger(database))
    monkeypatch.setattr(mesh_api, "task_store", TaskStore(database))
    monkeypatch.setattr(mesh_api, "job_store", JobStore(database))

    with TestClient(app) as client:
        home = client.get("/")
        assert home.status_code == 200
        assert "GPU MESH" in home.text
        assert client.get("/mesh").status_code == 200
        health = client.get("/healthz")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"
        assert health.headers["x-content-type-options"] == "nosniff"
