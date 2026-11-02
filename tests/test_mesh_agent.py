import hashlib
import hmac
import json
from threading import Event

from klod.mesh.agent import _run_bounded_task, verify_manifest


def manifest_for(node_id="node-1"):
    return {
        "version": 1,
        "task_id": "task-1",
        "job_id": "job-1",
        "owner_id": "owner-1",
        "node_id": node_id,
        "workload": "cpu-sha256",
        "payload": {"text": "agent-process", "iterations": 64},
        "device_index": None,
        "requires_gpu": False,
        "cpu_cores": 1.0,
        "ram_gib": 1.0,
        "vram_gib": 0.0,
        "max_runtime_seconds": 30,
        "attempt": 1,
        "lease_expires_at": 4_000_000_000,
    }


def signature(manifest, token):
    raw = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hmac.new(token.encode("utf-8"), raw, hashlib.sha256).hexdigest()


def test_worker_verifies_manifest_signature_and_node_binding():
    manifest = manifest_for()
    token = "worker-token"
    signed = signature(manifest, token)
    assert verify_manifest(manifest, signed, token, "node-1")
    assert not verify_manifest(manifest, "0" * 64, token, "node-1")
    assert not verify_manifest(manifest, signed, token, "node-2")
    modified = dict(manifest)
    modified["payload"] = {"text": "changed", "iterations": 64}
    assert not verify_manifest(modified, signed, token, "node-1")


def test_worker_executes_allowlisted_workload_in_bounded_child_process():
    manifest = manifest_for()
    result = _run_bounded_task(manifest, Event())
    assert result["workload"] == "cpu-sha256"
    assert len(result["sha256"]) == 64
    assert result["execution_device"] == "cpu"



def test_local_worker_advertises_configured_gpu_task_duration(monkeypatch):
    import sys
    from types import SimpleNamespace

    from klod.mesh.agent import detect_resources

    gib = 1024 ** 3
    fake_psutil = SimpleNamespace(
        virtual_memory=lambda: SimpleNamespace(total=8 * gib, available=4 * gib)
    )
    fake_cuda = SimpleNamespace(
        is_available=lambda: True,
        device_count=lambda: 1,
        get_device_properties=lambda index: SimpleNamespace(
            name="Test CUDA GPU",
            total_memory=8 * gib,
        ),
        mem_get_info=lambda index: (6 * gib, 8 * gib),
    )
    fake_torch = SimpleNamespace(cuda=fake_cuda)
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setenv("GPU_MESH_MAX_TASK_SECONDS", "1800")
    profile = detect_resources()
    assert profile["gpus"][0]["max_task_seconds"] == 1800
    assert profile["gpus"][0]["available_vram_gib"] == 6
    assert profile["ram_gib"] == 4
    assert profile["ram_available_gib"] == 2


def test_local_worker_rejects_invalid_gpu_task_duration(monkeypatch):
    import sys
    from types import SimpleNamespace

    import pytest

    from klod.mesh.agent import detect_resources

    monkeypatch.setitem(
        sys.modules,
        "psutil",
        SimpleNamespace(virtual_memory=lambda: SimpleNamespace(
            total=8 * 1024 ** 3, available=4 * 1024 ** 3,
        )),
    )
    monkeypatch.setenv("GPU_MESH_MAX_TASK_SECONDS", "not-a-number")
    with pytest.raises(RuntimeError, match="GPU_MESH_MAX_TASK_SECONDS"):
        detect_resources()
