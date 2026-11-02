from threading import Event

import pytest

from klod.mesh.workloads import (
    WorkloadError,
    execute_workload,
    required_vram_gib,
    validate_workload,
)


def test_cpu_sha256_is_deterministic_and_bounded():
    payload = validate_workload("cpu-sha256", {"text": "mesh", "iterations": 32})
    first = execute_workload("cpu-sha256", payload)
    second = execute_workload("cpu-sha256", payload)
    assert first["sha256"] == second["sha256"]
    assert first["iterations"] == 32
    assert first["execution_device"] == "cpu"


def test_cpu_sha256_rejects_oversized_or_empty_input():
    with pytest.raises(WorkloadError):
        validate_workload("cpu-sha256", {"text": "", "iterations": 1})
    with pytest.raises(WorkloadError):
        validate_workload("cpu-sha256", {"text": "x", "iterations": 250001})


def test_gpu_workloads_have_per_device_memory_estimates():
    matmul = {"matrix_size": 512, "seed": 7}
    fractal = {"width": 512, "height": 512, "max_iterations": 64}
    assert required_vram_gib("gpu-matmul", matmul) >= 1.0
    assert required_vram_gib("gpu-mandelbrot", fractal) >= 1.0


def test_gpu_workload_rejects_unbounded_dimensions():
    with pytest.raises(WorkloadError):
        validate_workload("gpu-matmul", {"matrix_size": 100000})
    with pytest.raises(WorkloadError):
        validate_workload("gpu-mandelbrot", {"width": 99999, "height": 256})


def test_cpu_workload_honors_cancellation():
    cancel = Event()
    cancel.set()
    with pytest.raises(WorkloadError, match="cancellation"):
        execute_workload("cpu-sha256", {"text": "x", "iterations": 5000}, cancel_event=cancel)
