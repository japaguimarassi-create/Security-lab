from __future__ import annotations

import hashlib
import json
import math
import time
from threading import Event
from typing import Any


class WorkloadError(ValueError):
    pass


def _bounded_int(value: Any, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise WorkloadError(f"{name} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise WorkloadError(f"{name} must be an integer") from exc
    if result != value or not minimum <= result <= maximum:
        raise WorkloadError(f"{name} must be between {minimum} and {maximum}")
    return result


def validate_workload(workload: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise WorkloadError("payload must be a JSON object")
    try:
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise WorkloadError("payload must contain finite JSON values only") from exc
    if len(encoded) > 16384:
        raise WorkloadError("payload exceeds 16 KiB")
    if workload == "cpu-sha256":
        text = payload.get("text")
        if not isinstance(text, str) or not text or len(text.encode("utf-8")) > 65536:
            raise WorkloadError("cpu-sha256 requires text between 1 byte and 64 KiB")
        iterations = _bounded_int(payload.get("iterations", 10000), "iterations", 1, 250000)
        return {"text": text, "iterations": iterations}
    if workload == "gpu-matmul":
        size = _bounded_int(payload.get("matrix_size", 512), "matrix_size", 64, 4096)
        seed = _bounded_int(payload.get("seed", 42), "seed", 0, 2_147_483_647)
        return {"matrix_size": size, "seed": seed}
    if workload == "gpu-mandelbrot":
        width = _bounded_int(payload.get("width", 1024), "width", 128, 2048)
        height = _bounded_int(payload.get("height", 1024), "height", 128, 2048)
        iterations = _bounded_int(payload.get("max_iterations", 128), "max_iterations", 16, 256)
        return {"width": width, "height": height, "max_iterations": iterations}
    raise WorkloadError("Unsupported executable workload")


def required_vram_gib(workload: str, payload: dict[str, Any]) -> float:
    spec = validate_workload(workload, payload)
    if workload == "gpu-matmul":
        size = spec["matrix_size"]
        estimated = (4 * size * size * 4) / (1024 ** 3) + 0.5
        return round(max(1.0, estimated), 3)
    if workload == "gpu-mandelbrot":
        pixels = spec["width"] * spec["height"]
        estimated = (pixels * 8 * 4) / (1024 ** 3) + 0.5
        return round(max(1.0, estimated), 3)
    return 0.0


def execute_workload(workload: str, payload: dict[str, Any],
                     device_index: int | None = None,
                     cancel_event: Event | None = None) -> dict[str, Any]:
    started = time.monotonic()
    spec = validate_workload(workload, payload)
    cancelled = cancel_event or Event()

    if workload == "cpu-sha256":
        seed = spec["text"].encode("utf-8")
        digest = hashlib.sha256(seed).digest()
        for index in range(spec["iterations"]):
            if index % 2048 == 0 and cancelled.is_set():
                raise WorkloadError("Task cancellation requested")
            digest = hashlib.sha256(digest + index.to_bytes(8, "big") + seed).digest()
        return {
            "workload": workload,
            "sha256": digest.hex(),
            "iterations": spec["iterations"],
            "elapsed_seconds": round(time.monotonic() - started, 6),
            "execution_device": "cpu",
            "result_validation": "deterministic-input-output",
        }

    try:
        import torch
    except ImportError as exc:
        raise WorkloadError("PyTorch is required for GPU workloads; install klod-ai[worker]") from exc
    if not torch.cuda.is_available():
        raise WorkloadError("This task requires a CUDA-compatible GPU")
    count = torch.cuda.device_count()
    index = 0 if device_index is None else _bounded_int(device_index, "device_index", 0, max(0, count - 1))
    if index >= count:
        raise WorkloadError("Assigned CUDA device is not available on this worker")
    torch.cuda.set_device(index)
    device = torch.device(f"cuda:{index}")
    free_bytes, total_bytes = torch.cuda.mem_get_info(index)

    if workload == "gpu-matmul":
        size = spec["matrix_size"]
        required = int(required_vram_gib(workload, spec) * (1024 ** 3))
        if free_bytes < required:
            raise WorkloadError("Current free VRAM is below the task's validated requirement")
        generator = torch.Generator(device=device)
        generator.manual_seed(spec["seed"])
        a = torch.rand((size, size), device=device, dtype=torch.float32, generator=generator)
        b = torch.rand((size, size), device=device, dtype=torch.float32, generator=generator)
        if cancelled.is_set():
            raise WorkloadError("Task cancellation requested")
        result = torch.matmul(a, b)
        torch.cuda.synchronize(index)
        if cancelled.is_set():
            raise WorkloadError("Task cancellation requested")
        raw = result.detach().contiguous().cpu().numpy().tobytes()
        digest = hashlib.sha256(raw).hexdigest()
        peak = torch.cuda.max_memory_allocated(index) / (1024 ** 3)
        del a, b, result
        torch.cuda.empty_cache()
        return {
            "workload": workload,
            "sha256": digest,
            "matrix_size": size,
            "device_index": index,
            "device_name": torch.cuda.get_device_name(index),
            "free_vram_before_gib": round(free_bytes / (1024 ** 3), 3),
            "total_vram_gib": round(total_bytes / (1024 ** 3), 3),
            "peak_allocated_vram_gib": round(peak, 3),
            "elapsed_seconds": round(time.monotonic() - started, 6),
            "execution_device": "cuda",
            "result_validation": "worker-reported-digest",
        }

    width = spec["width"]
    height = spec["height"]
    max_iterations = spec["max_iterations"]
    required = int(required_vram_gib(workload, spec) * (1024 ** 3))
    if free_bytes < required:
        raise WorkloadError("Current free VRAM is below the task's validated requirement")
    x = torch.linspace(-2.0, 1.0, width, device=device, dtype=torch.float32)
    y = torch.linspace(-1.5, 1.5, height, device=device, dtype=torch.float32)
    real, imag = torch.meshgrid(x, y, indexing="xy")
    z_real = torch.zeros_like(real)
    z_imag = torch.zeros_like(imag)
    escaped = torch.zeros(real.shape, dtype=torch.int32, device=device)
    active = torch.ones(real.shape, dtype=torch.bool, device=device)
    for step in range(1, max_iterations + 1):
        if step % 8 == 0 and cancelled.is_set():
            raise WorkloadError("Task cancellation requested")
        next_real = z_real * z_real - z_imag * z_imag + real
        next_imag = 2.0 * z_real * z_imag + imag
        z_real, z_imag = next_real, next_imag
        magnitude = z_real * z_real + z_imag * z_imag
        newly_escaped = active & (magnitude > 4.0)
        escaped[newly_escaped] = step
        active = active & ~newly_escaped
        if not bool(active.any()):
            break
    torch.cuda.synchronize(index)
    raw = escaped.contiguous().cpu().numpy().tobytes()
    digest = hashlib.sha256(raw).hexdigest()
    return {
        "workload": workload,
        "sha256": digest,
        "width": width,
        "height": height,
        "max_iterations": max_iterations,
        "device_index": index,
        "device_name": torch.cuda.get_device_name(index),
        "free_vram_before_gib": round(free_bytes / (1024 ** 3), 3),
        "total_vram_gib": round(total_bytes / (1024 ** 3), 3),
        "elapsed_seconds": round(time.monotonic() - started, 6),
        "execution_device": "cuda",
        "result_validation": "worker-reported-digest",
    }
