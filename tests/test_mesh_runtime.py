import hashlib
import hmac
import json
import time

import pytest

from klod.mesh.runtime import TaskError, TaskStore
from klod.mesh.workloads import execute_workload


def cpu_plan():
    return {
        "job_id": "job-runtime-test",
        "owner_id": "owner-1",
        "workload": "cpu-sha256",
        "requires_gpu": False,
        "min_vram_gib_per_task": 0.0,
        "max_runtime_seconds_per_task": 60,
        "assignments": [{
            "node_id": "node-1",
            "provider_id": "volunteer-worker",
            "task_count": 1,
            "gpu_devices": [],
            "cpu_cores_per_task": 1.0,
            "ram_gib_per_task": 1.0,
        }],
    }


def test_task_manifest_is_signed_and_lease_is_required(tmp_path):
    store = TaskStore(str(tmp_path / "tasks.sqlite"))
    created = store.create_from_plan(cpu_plan(), {"text": "secure", "iterations": 10})
    assert len(created) == 1
    worker_token = "worker-token-with-enough-entropy"
    claim = store.claim("node-1", worker_token)
    assert claim["manifest"]["task_id"] == created[0]["task_id"]
    expected = hmac.new(
        worker_token.encode(),
        json.dumps(claim["manifest"], ensure_ascii=False, sort_keys=True,
                   separators=(",", ":"), allow_nan=False).encode(),
        hashlib.sha256,
    ).hexdigest()
    assert hmac.compare_digest(expected, claim["manifest_signature"])
    with pytest.raises(TaskError):
        store.start(created[0]["task_id"], "node-1", "wrong-lease")
    assert store.start(created[0]["task_id"], "node-1", claim["lease_token"])["started"] is True


def test_cpu_task_result_is_recomputed_before_acceptance(tmp_path):
    store = TaskStore(str(tmp_path / "tasks.sqlite"))
    created = store.create_from_plan(cpu_plan(), {"text": "verified", "iterations": 32})
    claim = store.claim("node-1", "worker-token")
    store.start(created[0]["task_id"], "node-1", claim["lease_token"])
    expected = execute_workload("cpu-sha256", claim["manifest"]["payload"])
    done = store.complete(created[0]["task_id"], "node-1", claim["lease_token"], expected)
    assert done["completed"] is True
    task = store.list_results("job-runtime-test", "owner-1")[0]
    assert task["state"] == "completed"
    assert task["result"]["result_validation"] == "server-verified"


def test_cpu_task_rejects_forged_digest(tmp_path):
    store = TaskStore(str(tmp_path / "tasks.sqlite"))
    created = store.create_from_plan(cpu_plan(), {"text": "verify", "iterations": 4})
    claim = store.claim("node-1", "worker-token")
    store.start(created[0]["task_id"], "node-1", claim["lease_token"])
    with pytest.raises(TaskError, match="deterministic verification"):
        store.complete(
            created[0]["task_id"], "node-1", claim["lease_token"],
            {"workload": "cpu-sha256", "sha256": "0" * 64, "iterations": 4},
        )


def test_failed_task_is_requeued_and_attempt_count_increases(tmp_path):
    store = TaskStore(str(tmp_path / "tasks.sqlite"))
    created = store.create_from_plan(cpu_plan(), {"text": "retry", "iterations": 2})
    first = store.claim("node-1", "worker-token")
    store.start(created[0]["task_id"], "node-1", first["lease_token"])
    failed = store.fail(created[0]["task_id"], "node-1", first["lease_token"], "temporary_error")
    assert failed["retrying"] is True
    second = store.claim("node-1", "worker-token")
    assert second["manifest"]["attempt"] == 2
    assert second["manifest"]["task_id"] == created[0]["task_id"]


def test_running_task_cancel_is_cooperative_and_lease_renewal_reports_it(tmp_path):
    store = TaskStore(str(tmp_path / "tasks.sqlite"))
    created = store.create_from_plan(cpu_plan(), {"text": "cancel", "iterations": 2})
    claim = store.claim("node-1", "worker-token")
    store.start(created[0]["task_id"], "node-1", claim["lease_token"])
    cancelled = store.cancel_job("job-runtime-test", "owner-1")
    assert cancelled["cancelled"] == 1
    renewed = store.renew(created[0]["task_id"], "node-1", claim["lease_token"])
    assert renewed["cancel_requested"] is True
    result = execute_workload("cpu-sha256", claim["manifest"]["payload"])
    completed = store.complete(
        created[0]["task_id"], "node-1", claim["lease_token"], result,
    )
    assert completed["cancelled"] is True


def test_queued_task_cancellation_returns_reservation_identifier(tmp_path):
    store = TaskStore(str(tmp_path / "tasks.sqlite"))
    created = store.create_from_plan(cpu_plan(), {"text": "queued", "iterations": 2})
    cancelled = store.cancel_job("job-runtime-test", "owner-1")
    assert cancelled["releasable_task_ids"] == [created[0]["task_id"]]
    assert store.summary("job-runtime-test", "owner-1")["cancelled"] == 1
