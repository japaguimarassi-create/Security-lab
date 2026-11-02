import json

import pytest

from klod.mesh.kaggle_worker import (
    KaggleKernelAdapter,
    KaggleWorkerError,
    _resource_profile,
    build_kernel_metadata,
    render_kernel_script,
)


MANIFEST = {
    "version": 1,
    "task_id": "task-abc123",
    "job_id": "job-abc123",
    "owner_id": "owner-1",
    "node_id": "node-1",
    "workload": "gpu-matmul",
    "payload": {"matrix_size": 512, "seed": 11},
    "device_index": 0,
    "requires_gpu": True,
    "cpu_cores": 4.0,
    "ram_gib": 8.0,
    "vram_gib": 1.0,
    "max_runtime_seconds": 300,
    "attempt": 1,
    "lease_expires_at": 4_000_000_000,
}


def test_kernel_metadata_is_private_and_uses_gpu_only_for_gpu_workloads():
    gpu = build_kernel_metadata("meshowner", "gpu-mesh-abc123", "gpu-matmul", "NvidiaTeslaT4")
    cpu = build_kernel_metadata("meshowner", "gpu-mesh-def456", "cpu-sha256", "NvidiaTeslaT4")
    assert gpu["is_private"] is True
    assert gpu["enable_gpu"] is True
    assert gpu["enable_internet"] is False
    assert cpu["enable_gpu"] is False


def test_kernel_script_bundles_only_allowlisted_workload_code_and_manifest():
    script = render_kernel_script(MANIFEST)
    assert "def execute_workload" in script
    assert "_MESH_MANIFEST" in script
    assert "gpu_mesh_result.json" in script
    assert "task-abc123" in script
    assert "worker_token" not in script
    assert "lease_token" not in script


def test_kernel_metadata_rejects_invalid_remote_identifiers():
    with pytest.raises(KaggleWorkerError):
        build_kernel_metadata("bad/user", "gpu-mesh-abc123", "gpu-matmul", "NvidiaTeslaT4")
    with pytest.raises(KaggleWorkerError):
        build_kernel_metadata("meshowner", "../bad", "gpu-matmul", "NvidiaTeslaT4")


def test_kaggle_resource_profile_is_explicit_and_bounded(monkeypatch):
    monkeypatch.setenv("GPU_MESH_KAGGLE_CPU_CORES", "6")
    monkeypatch.setenv("GPU_MESH_KAGGLE_RAM_GIB", "24")
    monkeypatch.setenv("GPU_MESH_KAGGLE_GPU_COUNT", "2")
    monkeypatch.setenv("GPU_MESH_KAGGLE_GPU_VRAM_GIB", "16")
    monkeypatch.setenv("GPU_MESH_KAGGLE_ACCELERATOR", "NvidiaTeslaT4")
    profile = _resource_profile()
    assert profile["cpu_cores"] == 6
    assert profile["ram_gib"] == 24
    assert len(profile["gpus"]) == 2
    assert profile["gpus"][1]["total_vram_gib"] == 16

    monkeypatch.setenv("GPU_MESH_KAGGLE_GPU_COUNT", "99")
    with pytest.raises(KaggleWorkerError):
        _resource_profile()


def test_kaggle_status_parser_recognizes_official_cli_states(monkeypatch):
    monkeypatch.setenv("KAGGLE_API_TOKEN", "test-token")
    monkeypatch.setattr("klod.mesh.kaggle_worker.shutil.which", lambda _: "/usr/bin/kaggle")
    adapter = KaggleKernelAdapter(
        "https://mesh.example",
        "node-1",
        "worker-token",
        "meshowner",
        "NvidiaTeslaT4",
    )
    monkeypatch.setattr(adapter, "_cli", lambda *args, **kwargs: "owner/kernel has status KernelWorkerStatus.COMPLETE")
    assert adapter._status("meshowner/kernel") == "COMPLETE"
    monkeypatch.setattr(adapter, "_cli", lambda *args, **kwargs: "owner/kernel has status KernelWorkerStatus.RUNNING")
    assert adapter._status("meshowner/kernel") == "RUNNING"


def test_kernel_source_contains_fixed_task_dispatch_not_arbitrary_python():
    script = render_kernel_script(MANIFEST)
    assert "exec(" not in script
    assert "eval(" not in script
    assert "os.system" not in script
