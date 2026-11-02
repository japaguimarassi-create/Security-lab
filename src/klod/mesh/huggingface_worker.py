from __future__ import annotations

import json
import os
import time
from pathlib import Path
from threading import Event, Thread
from typing import Any

from .agent import _request, verify_manifest


class HuggingFaceWorkerError(RuntimeError):
    pass


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError as exc:
        raise HuggingFaceWorkerError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise HuggingFaceWorkerError(f"{name} must be between {minimum} and {maximum}")
    return value


def _profile() -> dict[str, Any]:
    size = os.environ.get("GPU_MESH_HF_ZEROGPU_SIZE", "large").lower()
    if size not in ("large", "xlarge"):
        raise HuggingFaceWorkerError("GPU_MESH_HF_ZEROGPU_SIZE must be large or xlarge")
    max_task_seconds = _env_int("GPU_MESH_HF_MAX_TASK_SECONDS", 120, 1, 120)
    vram = 48.0 if size == "large" else 96.0
    return {
        "cpu_cores": float(_env_int("GPU_MESH_HF_CPU_CORES", 2, 1, 32)),
        "ram_gib": float(_env_int("GPU_MESH_HF_RAM_GIB", 8, 1, 128)),
        "storage_gib": 0.0,
        "gpus": [{
            "name": f"Hugging Face ZeroGPU {size}",
            "total_vram_gib": vram,
            "available_vram_gib": vram,
            "max_task_seconds": max_task_seconds,
        }],
        "max_task_seconds": max_task_seconds,
    }


def _quota_remaining_seconds(token: str) -> float:
    try:
        from huggingface_hub import HfApi
    except ImportError as exc:
        raise HuggingFaceWorkerError(
            "Install klod-ai[huggingface] to verify ZeroGPU quota"
        ) from exc
    try:
        quota = HfApi(token=token).get_zero_gpu_quota()
    except Exception as exc:
        raise HuggingFaceWorkerError(
            "Unable to read Hugging Face ZeroGPU quota; the token needs billing-usage read permission"
        ) from exc
    remaining = getattr(quota, "remaining", None)
    if remaining is None and isinstance(quota, dict):
        remaining = quota.get("remaining")
    if remaining is None:
        raise HuggingFaceWorkerError("Hugging Face did not return a remaining GPU quota")
    return max(0.0, float(remaining))


class HuggingFaceZeroGPUWorker:
    def __init__(self, base_url: str, node_id: str, worker_token: str,
                 space_id: str, hf_token: str, profile: dict[str, Any]):
        if not base_url.startswith("https://"):
            raise HuggingFaceWorkerError("GPU_MESH_API_URL must use HTTPS")
        if not all((node_id, worker_token, space_id, hf_token)):
            raise HuggingFaceWorkerError("Mesh worker identity, HF Space ID and token are required")
        self.base_url = base_url.rstrip("/")
        self.node_id = node_id
        self.worker_token = worker_token
        self.space_id = space_id
        self.hf_token = hf_token
        self.profile = profile
        self._client = None

    def _api(self, path: str, method: str = "GET",
             body: dict[str, Any] | None = None,
             lease_token: str | None = None) -> dict[str, Any]:
        return _request(
            self.base_url + path,
            method=method,
            worker_token=self.worker_token,
            lease_token=lease_token,
            body=body,
        )

    def _get_client(self):
        if self._client is None:
            try:
                from gradio_client import Client
            except ImportError as exc:
                raise HuggingFaceWorkerError(
                    "Install klod-ai[huggingface] to call a Gradio Space"
                ) from exc
            self._client = Client(self.space_id, hf_token=self.hf_token, verbose=False)
        return self._client

    def _heartbeat(self) -> None:
        self._api(
            f"/v1/mesh/workers/{self.node_id}/heartbeat",
            method="POST",
            body={
                "cpu_available": self.profile["cpu_cores"],
                "ram_available_gib": self.profile["ram_gib"],
                "storage_available_gib": self.profile["storage_gib"],
                "gpus": self.profile["gpus"],
            },
        )

    def _maintain_lease(self, manifest: dict[str, Any], lease_token: str,
                        stop: Event, cancel: Event) -> None:
        task_id = manifest["task_id"]
        while not stop.wait(15):
            try:
                self._heartbeat()
                state = self._api(
                    f"/v1/mesh/workers/{self.node_id}/tasks/{task_id}/renew",
                    method="POST",
                    lease_token=lease_token,
                )
                if state.get("cancel_requested") or not state.get("renewed"):
                    cancel.set()
                    return
            except Exception:
                if stop.wait(5):
                    return

    def _invoke_space(self, manifest: dict[str, Any]) -> dict[str, Any]:
        if manifest["requires_gpu"]:
            remaining = _quota_remaining_seconds(self.hf_token)
            required = float(manifest["max_runtime_seconds"])
            if remaining < required:
                raise HuggingFaceWorkerError(
                    f"ZeroGPU quota too low: {remaining:.0f}s remaining, {required:.0f}s requested"
                )
            result = self._get_client().predict(
                manifest["workload"],
                json.dumps(manifest["payload"], ensure_ascii=False, allow_nan=False),
                int(manifest.get("device_index") or 0),
                int(manifest["max_runtime_seconds"]),
                api_name="/run_gpu_task",
            )
        else:
            result = self._get_client().predict(
                manifest["workload"],
                json.dumps(manifest["payload"], ensure_ascii=False, allow_nan=False),
                api_name="/run_cpu_task",
            )
        if not isinstance(result, dict):
            raise HuggingFaceWorkerError("Hugging Face Space returned a non-object result")
        return result

    def run_once(self) -> bool:
        claim = self._api(
            f"/v1/mesh/workers/{self.node_id}/tasks/claim",
            method="POST",
        ).get("task")
        if not claim:
            return False
        manifest = claim["manifest"]
        lease_token = claim["lease_token"]
        if not verify_manifest(
            manifest, claim["manifest_signature"], self.worker_token, self.node_id
        ):
            raise HuggingFaceWorkerError("Task manifest signature is invalid")
        started = self._api(
            f"/v1/mesh/workers/{self.node_id}/tasks/{manifest['task_id']}/start",
            method="POST",
            lease_token=lease_token,
        )
        if not started.get("started"):
            return True

        stop = Event()
        cancel = Event()
        keeper = Thread(
            target=self._maintain_lease,
            args=(manifest, lease_token, stop, cancel),
            daemon=True,
        )
        keeper.start()
        try:
            result = self._invoke_space(manifest)
            completion = self._api(
                f"/v1/mesh/workers/{self.node_id}/tasks/{manifest['task_id']}/complete",
                method="POST",
                lease_token=lease_token,
                body={"result": result},
            )
            if not (completion.get("completed") or completion.get("cancelled")):
                raise HuggingFaceWorkerError("GPU Mesh did not accept the Space result")
            return True
        except Exception as exc:
            try:
                self._api(
                    f"/v1/mesh/workers/{self.node_id}/tasks/{manifest['task_id']}/fail",
                    method="POST",
                    lease_token=lease_token,
                    body={"error_code": type(exc).__name__[:80]},
                )
            except Exception:
                pass
            raise
        finally:
            stop.set()
            keeper.join(timeout=3)
            self._heartbeat()

    def run_forever(self) -> None:
        while True:
            try:
                self._heartbeat()
                if not self.run_once():
                    time.sleep(10)
            except KeyboardInterrupt:
                break
            except Exception:
                time.sleep(20)


def main() -> None:
    base_url = os.environ.get("GPU_MESH_API_URL", "").rstrip("/")
    access_token = os.environ.get("GPU_MESH_ACCESS_TOKEN", "")
    space_id = os.environ.get("GPU_MESH_HF_SPACE_ID", "")
    hf_token = os.environ.get("HF_TOKEN", "")
    state_path = Path(os.environ.get(
        "GPU_MESH_HF_WORKER_STATE",
        str(Path.home() / ".gpu-mesh" / "huggingface-worker.json"),
    )).expanduser()
    if not base_url.startswith("https://"):
        raise SystemExit("GPU_MESH_API_URL must use HTTPS")
    if not access_token or not hf_token or not space_id:
        raise SystemExit("GPU_MESH_ACCESS_TOKEN, HF_TOKEN and GPU_MESH_HF_SPACE_ID are required")
    profile = _profile()
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        node_id = state["node_id"]
        worker_token = state["worker_token"]
    else:
        result = _request(
            base_url + "/v1/mesh/workers",
            access_token,
            method="POST",
            body={
                "provider_id": "huggingface-zerogpu",
                "cpu_cores": profile["cpu_cores"],
                "ram_gib": profile["ram_gib"],
                "storage_gib": profile["storage_gib"],
                "gpus": profile["gpus"],
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

    HuggingFaceZeroGPUWorker(
        base_url, node_id, worker_token, space_id, hf_token, profile
    ).run_forever()


if __name__ == "__main__":
    main()
