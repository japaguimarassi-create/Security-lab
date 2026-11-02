import sys
from types import SimpleNamespace

import pytest

from klod.mesh.huggingface_worker import (
    HuggingFaceWorkerError,
    _profile,
    _quota_remaining_seconds,
)


def test_zero_gpu_profile_advertises_provider_specific_vram_and_duration(monkeypatch):
    monkeypatch.setenv("GPU_MESH_HF_ZEROGPU_SIZE", "large")
    monkeypatch.setenv("GPU_MESH_HF_MAX_TASK_SECONDS", "120")
    large = _profile()
    assert large["gpus"][0]["total_vram_gib"] == 48
    assert large["gpus"][0]["max_task_seconds"] == 120

    monkeypatch.setenv("GPU_MESH_HF_ZEROGPU_SIZE", "xlarge")
    xlarge = _profile()
    assert xlarge["gpus"][0]["total_vram_gib"] == 96


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
