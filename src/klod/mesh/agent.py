from __future__ import annotations

import json
import os
import shutil
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def _request(url: str, access_token: str, method: str = "GET",
             worker_token: str | None = None, body: dict[str, Any] | None = None) -> dict:
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if worker_token:
        headers["X-Worker-Token"] = worker_token
    request = urllib.request.Request(url, data=payload, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read(2048).decode("utf-8", errors="replace")
        raise RuntimeError(f"GPU Mesh API returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GPU Mesh API connection failed: {exc.reason}") from exc


def detect_resources() -> dict[str, Any]:
    try:
        import psutil
    except ImportError as exc:
        raise RuntimeError("Install psutil to run the resource agent") from exc
    cpu_total = max(1, os.cpu_count() or 1)
    cpu_fraction = min(1.0, max(0.05, float(os.getenv("GPU_MESH_CPU_FRACTION", "0.5"))))
    ram_fraction = min(1.0, max(0.05, float(os.getenv("GPU_MESH_RAM_FRACTION", "0.5"))))
    ram_total = psutil.virtual_memory().total / (1024 ** 3)
    cpu_available = max(0.1, cpu_total * cpu_fraction)
    ram_available = max(0.1, ram_total * ram_fraction)
    gpus = []
    try:
        import torch
        if torch.cuda.is_available():
            for index in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(index)
                try:
                    free_bytes, total_bytes = torch.cuda.mem_get_info(index)
                except Exception:
                    total_bytes = int(props.total_memory)
                    free_bytes = total_bytes
                total_gib = total_bytes / (1024 ** 3)
                gpus.append({
                    "name": str(props.name)[:120],
                    "total_vram_gib": round(total_gib, 3),
                    "available_vram_gib": round(min(total_gib, free_bytes / (1024 ** 3)), 3),
                })
    except ImportError:
        pass
    return {
        "cpu_cores": round(cpu_available, 2),
        "ram_gib": round(ram_available, 3),
        "storage_gib": 0.0,
        "gpus": gpus,
    }


def run_agent() -> None:
    base_url = os.environ.get("GPU_MESH_API_URL", "").rstrip("/")
    access_token = os.environ.get("GPU_MESH_ACCESS_TOKEN", "")
    state_path = Path(os.environ.get(
        "GPU_MESH_WORKER_STATE",
        str(Path.home() / ".gpu-mesh" / "worker.json")
    )).expanduser()
    interval = max(15, int(os.environ.get("GPU_MESH_HEARTBEAT_SECONDS", "30")))
    if not base_url.startswith("https://"):
        raise SystemExit("GPU_MESH_API_URL must use HTTPS")
    if not access_token:
        raise SystemExit("GPU_MESH_ACCESS_TOKEN is required")
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        node_id = state["node_id"]
        worker_token = state["worker_token"]
    else:
        resources = detect_resources()
        result = _request(
            base_url + "/v1/mesh/workers",
            access_token,
            method="POST",
            body={"provider_id": "volunteer-worker", **resources, "shared": True},
        )
        node_id = result["node_id"]
        worker_token = result["worker_token"]
        state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps({
            "node_id": node_id,
            "worker_token": worker_token,
        }), encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(state_path)
        os.chmod(state_path, 0o600)
    while True:
        resources = detect_resources()
        _request(
            f"{base_url}/v1/mesh/workers/{node_id}/heartbeat",
            access_token,
            method="POST",
            worker_token=worker_token,
            body={
                "cpu_available": resources["cpu_cores"],
                "ram_available_gib": resources["ram_gib"],
                "storage_available_gib": resources["storage_gib"],
                "gpus": resources["gpus"],
            },
        )
        time.sleep(interval)


if __name__ == "__main__":
    run_agent()
