import os

import pytest
from fastapi.testclient import TestClient

from klod import api as core_api
from klod.mesh import api as mesh_api
from klod.mesh.api import JobStore
from klod.mesh.auth import AuthStore
from klod.mesh.quotas import QuotaLedger
from klod.mesh.registry import ResourceRegistry
from klod.mesh.runtime import TaskStore
from klod.mesh.workloads import execute_workload


def test_postgres_mesh_registration_dispatch_and_completion(monkeypatch):
    database_url = os.getenv("TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("TEST_POSTGRES_URL is not configured")

    monkeypatch.setattr(mesh_api, 'auth_store', AuthStore(database_url))
    monkeypatch.setattr(mesh_api, 'registry', ResourceRegistry(database_url))
    monkeypatch.setattr(mesh_api, 'quota_ledger', QuotaLedger(database_url))
    monkeypatch.setattr(mesh_api, 'task_store', TaskStore(database_url))
    monkeypatch.setattr(mesh_api, 'job_store', JobStore(database_url))

    with TestClient(core_api.app) as client:
        created = client.post('/v1/mesh/auth/register', json={
            'email': 'postgres-integration@example.test',
            'password': 'Postgres-Mesh-Pass-2026',
        })
        assert created.status_code == 201, created.text

        login = client.post('/v1/mesh/auth/login', json={
            'email': 'postgres-integration@example.test',
            'password': 'Postgres-Mesh-Pass-2026',
        })
        assert login.status_code == 200, login.text
        account_headers = {'Authorization': 'Bearer ' + login.json()['access_token']}

        registered = client.post('/v1/mesh/workers', headers=account_headers, json={
            'provider_id': 'volunteer-worker',
            'cpu_cores': 2,
            'ram_gib': 4,
            'storage_gib': 0,
            'gpus': [],
            'shared': False,
        })
        assert registered.status_code == 201, registered.text
        worker = registered.json()
        worker_headers = {'X-Worker-Token': worker['worker_token']}

        heartbeat = client.post(
            f"/v1/mesh/workers/{worker['node_id']}/heartbeat",
            headers=worker_headers,
            json={'cpu_available': 2, 'ram_available_gib': 4, 'storage_available_gib': 0, 'gpus': []},
        )
        assert heartbeat.status_code == 200, heartbeat.text

        created_job = client.post('/v1/mesh/jobs', headers=account_headers, json={
            'workload': 'cpu-sha256',
            'payload': {'text': 'postgres-integration', 'iterations': 16},
            'task_count': 1,
            'requires_gpu': False,
            'min_vram_gib_per_task': 0,
            'cpu_cores_per_task': 1,
            'ram_gib_per_task': 1,
            'max_runtime_seconds_per_task': 60,
        })
        assert created_job.status_code == 201, created_job.text
        job = created_job.json()

        claimed_response = client.post(
            f"/v1/mesh/workers/{worker['node_id']}/tasks/claim",
            headers=worker_headers,
        )
        assert claimed_response.status_code == 200, claimed_response.text
        claim = claimed_response.json()['task']
        task_id = claim['manifest']['task_id']
        lease_headers = {**worker_headers, 'X-Task-Lease': claim['lease_token']}

        started = client.post(
            f"/v1/mesh/workers/{worker['node_id']}/tasks/{task_id}/start",
            headers=lease_headers,
        )
        assert started.status_code == 200, started.text
        result = execute_workload('cpu-sha256', claim['manifest']['payload'])
        completed = client.post(
            f"/v1/mesh/workers/{worker['node_id']}/tasks/{task_id}/complete",
            headers=lease_headers,
            json={'result': result},
        )
        assert completed.status_code == 200, completed.text
        assert completed.json()['completed'] is True

        results = client.get(
            f"/v1/mesh/jobs/{job['job_id']}/results",
            headers=account_headers,
        )
        assert results.status_code == 200, results.text
        assert results.json()['summary']['execution_status'] == 'completed'
        assert results.json()['tasks'][0]['result']['result_validation'] == 'server-verified'
