from __future__ import annotations

import hashlib
import hmac
import json
import multiprocessing
import os
import queue
import time
import urllib.error
import urllib.request
from pathlib import Path
from threading import Event, Thread
from typing import Any

from .workloads import execute_workload


def _request(url: str, access_token: str = "", method: str = "GET",
             worker_token: str | None = None, lease_token: str | None = None,
             body: dict[str, Any] | None = None) -> dict:
    payload = json.dumps(body, allow_nan=False).encode("utf-8") if body is not None else None
    headers = {"Accept": "application/json"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if worker_token:
        headers["X-Worker-Token"] = worker_token
    if lease_token:
        headers["X-Task-Lease"] = lease_token
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
    memory = psutil.virtual_memory()
    ram_total = memory.total / (1024 ** 3)
    ram_available = min(ram_total * ram_fraction, memory.available / (1024 ** 3) * ram_fraction)
    cpu_available = max(0.1, cpu_total * cpu_fraction)
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
        "ram_gib": round(max(0.1, ram_available), 3),
        "storage_gib": 0.0,
        "gpus": gpus,
    }


def _canonical_manifest(manifest: dict[str, Any]) -> bytes:
    return json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def verify_manifest(manifest: dict[str, Any], signature: str,
                    worker_token: str, node_id: str) -> bool:
    if not isinstance(manifest, dict) or manifest.get("version") != 1:
        return False
    if manifest.get("node_id") != node_id or not worker_token:
        return False
    if int(manifest.get("lease_expires_at", 0)) <= int(time.time()):
        return False
    expected = hmac.new(
        worker_token.encode("utf-8"),
        _canonical_manifest(manifest),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, str(signature))


def _apply_child_limits(runtime_seconds: int) -> None:
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024 * 1024, 16 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
        resource.setrlimit(resource.RLIMIT_CPU, (runtime_seconds, runtime_seconds + 2))
    except (ImportError, AttributeError, OSError, ValueError):
        pass


def _execute_child(output_queue, manifest: dict[str, Any], cancel_event) -> None:
    _apply_child_limits(int(manifest["max_runtime_seconds"]))
    try:
        result = execute_workload(
            manifest["workload"],
            manifest["payload"],
            manifest.get("device_index"),
            cancel_event,
        )
        output_queue.put({"ok": True, "result": result})
    except Exception as exc:
        output_queue.put({
            "ok": False,
            "error_code": type(exc).__name__[:80] or "worker_error",
        })


def _run_bounded_task(manifest: dict[str, Any], cancel_event: Event) -> dict[str, Any]:
    runtime = int(manifest["max_runtime_seconds"])
    if not 1 <= runtime <= 3600:
        raise RuntimeError("invalid_task_runtime")
    context = multiprocessing.get_context("spawn")
    output_queue = context.Queue(maxsize=1)
    process_event = context.Event()
    process = context.Process(
        target=_execute_child,
        args=(output_queue, manifest, process_event),
        daemon=True,
    )
    process.start()
    deadline = time.monotonic() + runtime
    try:
        while process.is_alive():
            process.join(timeout=0.25)
            if cancel_event.is_set():
                process_event.set()
                process.join(timeout=5)
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5)
                raise RuntimeError("task_cancelled")
            if time.monotonic() >= deadline:
                process.terminate()
                process.join(timeout=5)
                raise RuntimeError("task_timeout")
        try:
            message = output_queue.get(timeout=5)
        except queue.Empty as exc:
            raise RuntimeError("worker_process_no_result") from exc
        if not message.get("ok"):
            raise RuntimeError(message.get("error_code", "worker_task_failed"))
        return message["result"]
    finally:
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
        output_queue.close()


def _send_heartbeat(base_url: str, node_id: str, worker_token: str,
                    access_token: str = "") -> dict[str, Any]:
    resources = detect_resources()
    return _request(
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


def _maintain_task(base_url: str, node_id: str, worker_token: str,
                   manifest: dict[str, Any], lease_token: str,
                   stop_event: Event, cancel_event: Event) -> None:
    task_id = manifest["task_id"]
    while not stop_event.wait(15):
        try:
            _send_heartbeat(base_url, node_id, worker_token)
            state = _request(
                f"{base_url}/v1/mesh/workers/{node_id}/tasks/{task_id}/renew",
                method="POST",
                worker_token=worker_token,
                lease_token=lease_token,
            )
            if state.get("cancel_requested") or not state.get("renewed"):
                cancel_event.set()
                return
        except Exception:
            if stop_event.wait(5):
                return
            continue


def _execute_claimed_task(base_url: str, node_id: str, worker_token: str,
                          claimed: dict[str, Any], heartbeat_interval: int) -> None:
    manifest = claimed["manifest"]
    lease_token = claimed["lease_token"]
    signature = claimed["manifest_signature"]
    if not verify_manifest(manifest, signature, worker_token, node_id):
        raise RuntimeError("manifest_signature_invalid")
    task_id = manifest["task_id"]
    started = _request(
        f"{base_url}/v1/mesh/workers/{node_id}/tasks/{task_id}/start",
        method="POST",
        worker_token=worker_token,
        lease_token=lease_token,
    )
    if not started.get("started"):
        return

    stop_event = Event()
    cancel_event = Event()
    maintainer = Thread(
        target=_maintain_task,
        args=(base_url, node_id, worker_token, manifest, lease_token,
              stop_event, cancel_event),
        daemon=True,
    )
    maintainer.start()
    try:
        result = _run_bounded_task(manifest, cancel_event)
        _request(
            f"{base_url}/v1/mesh/workers/{node_id}/tasks/{task_id}/complete",
            method="POST",
            worker_token=worker_token,
            lease_token=lease_token,
            body={"result": result},
        )
    except Exception as exc:
        error_code = str(exc)[:80] or type(exc).__name__
        try:
            _request(
                f"{base_url}/v1/mesh/workers/{node_id}/tasks/{task_id}/fail",
                method="POST",
                worker_token=worker_token,
                lease_token=lease_token,
                body={"error_code": error_code},
            )
        except Exception:
            raise exc
    finally:
        stop_event.set()
        maintainer.join(timeout=3)
    _send_heartbeat(base_url, node_id, worker_token)


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
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        node_id = state["node_id"]
        worker_token = state["worker_token"]
    else:
        if not access_token:
            raise SystemExit("GPU_MESH_ACCESS_TOKEN is required for first-time worker registration")
        resources = detect_resources()
        result = _request(
            base_url + "/v1/mesh/workers",
            access_token,
            method="POST",
            body={
                "provider_id": "volunteer-worker",
                **resources,
                "shared": os.getenv("GPU_MESH_SHARE", "false").lower() == "true",
            },
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
        try:
            _send_heartbeat(base_url, node_id, worker_token)
            claimed = _request(
                f"{base_url}/v1/mesh/workers/{node_id}/tasks/claim",
                method="POST",
                worker_token=worker_token,
            ).get("task")
            if claimed:
                _execute_claimed_task(base_url, node_id, worker_token, claimed, interval)
            else:
                time.sleep(min(5, interval))
        except KeyboardInterrupt:
            break
        except Exception:
            time.sleep(min(10, interval))


if __name__ == "__main__":
    run_agent()
