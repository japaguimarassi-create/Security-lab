import sys
from types import SimpleNamespace

import pytest

from klod.mesh.huggingface_worker import (
    HuggingFaceWorkerError,
    _profile,
    _quota_remaining_seconds,
    required_quota_seconds,
)


def test_zero_gpu_profile_advertises_provider_specific_vram_and_duration(monkeypatch):
    monkeypatch.setenv("GPU_MESH_HF_ZEROGPU_SIZE", "large")
    monkeypatch.setenv("GPU_MESH_HF_MAX_TASK_SECONDS", "120")
    large = _profile()
    assert large["gpus"][0]["total_vram_gib"] == 48
    assert large["gpus"][0]["max_task_seconds"] == 120
    assert large["quota_multiplier"] == 1
    assert required_quota_seconds(120, large) == 120

    monkeypatch.setenv("GPU_MESH_HF_ZEROGPU_SIZE", "xlarge")
    xlarge = _profile()
    assert xlarge["gpus"][0]["total_vram_gib"] == 96
    assert xlarge["quota_multiplier"] == 2
    assert required_quota_seconds(120, xlarge) == 240


def test_zero_gpu_profile_rejects_unsupported_duration_and_size(monkeypatch):
    monkeypatch.setenv("GPU_MESH_HF_MAX_TASK_SECONDS", "121")
    with pytest.raises(HuggingFaceWorkerError):
        _profile()
    monkeypatch.setenv("GPU_MESH_HF_MAX_TASK_SECONDS", "120")
    monkeypatch.setenv("GPU_MESH_HF_ZEROGPU_SIZE", "unknown")
    with pytest.raises(HuggingFaceWorkerError):
        _profile()


def test_zero_gpu_quota_reader_extracts_remaining_seconds(monkeypatch):
    class FakeApi:
        def __init__(self, token):
            assert token == "hf-test-token"

        def get_zero_gpu_quota(self):
            return SimpleNamespace(remaining=95)

    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(HfApi=FakeApi))
    assert _quota_remaining_seconds("hf-test-token") == 95


def test_zero_gpu_quota_reader_fails_closed_when_provider_quota_is_unavailable(monkeypatch):
    class FakeApi:
        def __init__(self, token):
            pass

        def get_zero_gpu_quota(self):
            return SimpleNamespace()

    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(HfApi=FakeApi))
    with pytest.raises(HuggingFaceWorkerError, match="remaining GPU quota"):
        _quota_remaining_seconds("hf-test-token")


def test_gradio_client_receives_private_space_token(monkeypatch):
    from klod.mesh.huggingface_worker import HuggingFaceZeroGPUWorker

    captured = {}

    class FakeClient:
        def __init__(self, space_id, token, verbose):
            captured["space_id"] = space_id
            captured["token"] = token
            captured["verbose"] = verbose

    monkeypatch.setitem(sys.modules, "gradio_client", SimpleNamespace(Client=FakeClient))
    worker = HuggingFaceZeroGPUWorker(
        "https://mesh.example",
        "node-1",
        "worker-token",
        "owner/private-space",
        "hf-private-token",
        _profile(),
    )
    worker._get_client()
    assert captured == {
        "space_id": "owner/private-space",
        "token": "hf-private-token",
        "verbose": False,
    }


def test_zero_gpu_bridge_uses_async_job_and_returns_verified_shape(monkeypatch):
    from klod.mesh.huggingface_worker import HuggingFaceZeroGPUWorker
    monkeypatch.setattr("klod.mesh.huggingface_worker._quota_remaining_seconds", lambda token: 300)
    captured = {}

    class FakeJob:
        def done(self):
            return True

        def result(self):
            return {"workload": "gpu-matmul", "sha256": "a" * 64}

    class FakeClient:
        def submit(self, *args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return FakeJob()

    worker = HuggingFaceZeroGPUWorker(
        "https://mesh.example", "node-1", "worker-token",
        "owner/private-space", "hf-token", _profile(),
    )
    worker._client = FakeClient()
    result = worker._invoke_space({
        "workload": "gpu-matmul",
        "payload": {"matrix_size": 512, "seed": 4},
        "device_index": 0,
        "max_runtime_seconds": 120,
        "requires_gpu": True,
    })
    assert result["sha256"] == "a" * 64
    assert captured["kwargs"]["api_name"] == "/run_gpu_task"


def test_zero_gpu_bridge_cancels_a_job_that_is_still_queued(monkeypatch):
    from threading import Event

    from klod.mesh.huggingface_worker import HuggingFaceZeroGPUWorker

    class FakeJob:
        def done(self):
            return False

        def cancel(self):
            return True

    class FakeClient:
        def submit(self, *args, **kwargs):
            return FakeJob()

    worker = HuggingFaceZeroGPUWorker(
        "https://mesh.example", "node-1", "worker-token",
        "owner/private-space", "hf-token", _profile(),
    )
    worker._client = FakeClient()
    cancel = Event()
    cancel.set()
    with pytest.raises(HuggingFaceWorkerError, match="cancelled before execution"):
        worker._invoke_space({
            "workload": "gpu-matmul",
            "payload": {"matrix_size": 512, "seed": 4},
            "device_index": 0,
            "max_runtime_seconds": 60,
            "requires_gpu": True,
        }, cancel_event=cancel)


def test_zero_gpu_bridge_does_not_claim_running_provider_jobs_were_stopped(monkeypatch):
    from threading import Event

    from klod.mesh.huggingface_worker import HuggingFaceZeroGPUWorker

    class FakeJob:
        def done(self):
            return False

        def cancel(self):
            return False

    class FakeClient:
        def submit(self, *args, **kwargs):
            return FakeJob()

    worker = HuggingFaceZeroGPUWorker(
        "https://mesh.example", "node-1", "worker-token",
        "owner/private-space", "hf-token", _profile(),
    )
    worker._client = FakeClient()
    cancel = Event()
    cancel.set()
    with pytest.raises(HuggingFaceWorkerError, match="remote GPU call may continue"):
        worker._invoke_space({
            "workload": "gpu-matmul",
            "payload": {"matrix_size": 512, "seed": 4},
            "device_index": 0,
            "max_runtime_seconds": 60,
            "requires_gpu": True,
        }, cancel_event=cancel)


def test_zero_gpu_bridge_rejects_cpu_runtime_above_provider_limit():
    from klod.mesh.huggingface_worker import HuggingFaceZeroGPUWorker

    worker = HuggingFaceZeroGPUWorker(
        "https://mesh.example", "node-1", "worker-token",
        "owner/private-space", "hf-token", _profile(),
    )
    with pytest.raises(HuggingFaceWorkerError, match="duration limit"):
        worker._invoke_space({
            "workload": "cpu-sha256",
            "payload": {"text": "test", "iterations": 10},
            "device_index": None,
            "max_runtime_seconds": 300,
            "requires_gpu": False,
        })
