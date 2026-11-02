from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from .agent import _request, verify_manifest


class KaggleWorkerError(RuntimeError):
    pass


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise KaggleWorkerError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise KaggleWorkerError(f"{name} must be between {minimum} and {maximum}")
    return value


def _resource_profile() -> dict[str, Any]:
    cpu = _env_int("GPU_MESH_KAGGLE_CPU_CORES", 4, 1, 256)
    ram = _env_int("GPU_MESH_KAGGLE_RAM_GIB", 16, 1, 1024)
    gpu_count = _env_int("GPU_MESH_KAGGLE_GPU_COUNT", 2, 0, 8)
    vram = _env_int("GPU_MESH_KAGGLE_GPU_VRAM_GIB", 16, 1, 96)
    accelerator = os.environ.get("GPU_MESH_KAGGLE_ACCELERATOR", "NvidiaTeslaT4")
    max_task_seconds = _env_int("GPU_MESH_KAGGLE_MAX_TASK_SECONDS", 3600, 1, 86400)
    if not re.fullmatch(r"[A-Za-z0-9_-]{2,40}", accelerator):
        raise KaggleWorkerError("GPU_MESH_KAGGLE_ACCELERATOR has an invalid format")
    gpus = [{
        "name": accelerator,
        "total_vram_gib": float(vram),
        "available_vram_gib": float(vram),
        "max_task_seconds": max_task_seconds,
    } for _ in range(gpu_count)]
    return {
        "cpu_cores": float(cpu),
        "ram_gib": float(ram),
        "storage_gib": 0.0,
        "gpus": gpus,
        "accelerator": accelerator,
    }


def render_kernel_script(manifest: dict[str, Any]) -> str:
    workload_source = Path(__file__).with_name("workloads.py").read_text(encoding="utf-8")
    serialized = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    footer = f"""

import json as _mesh_json
from pathlib import Path as _mesh_path

_MESH_MANIFEST = _mesh_json.loads({serialized!r})
_MESH_RESULT = execute_workload(
    _MESH_MANIFEST["workload"],
    _MESH_MANIFEST["payload"],
    _MESH_MANIFEST.get("device_index"),
)
_mesh_output = _mesh_path("/kaggle/working/gpu_mesh_result.json")
_mesh_output.parent.mkdir(parents=True, exist_ok=True)
_mesh_output.write_text(
    _mesh_json.dumps(_MESH_RESULT, ensure_ascii=False, allow_nan=False),
    encoding="utf-8",
)
print("GPU_MESH_TASK_COMPLETE", _MESH_MANIFEST["task_id"])
"""
    return workload_source.rstrip() + "\n" + footer


def build_kernel_metadata(username: str, slug: str, workload: str,
                          accelerator: str) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9_-]{2,40}", username):
        raise KaggleWorkerError("KAGGLE_USERNAME has an invalid format")
    if not re.fullmatch(r"[a-z0-9-]{3,50}", slug):
        raise KaggleWorkerError("Kernel slug has an invalid format")
    is_gpu = workload in ("gpu-matmul", "gpu-mandelbrot")
    metadata = {
        "id": f"{username}/{slug}",
        "title": f"GPU Mesh {slug.removeprefix('gpu-mesh-')}",
        "code_file": "main.py",
        "language": "python",
        "kernel_type": "script",
        "is_private": "true",
        "enable_gpu": "true" if is_gpu else "false",
        "enable_internet": "false",
        "machine_shape": accelerator if is_gpu else "",
        "dataset_sources": [],
        "competition_sources": [],
        "kernel_sources": [],
        "model_sources": [],
    }
    if is_gpu and not accelerator:
        raise KaggleWorkerError("GPU tasks require a configured Kaggle accelerator")
    return metadata


class KaggleKernelAdapter:
    def __init__(self, base_url: str, node_id: str, worker_token: str,
                 username: str, accelerator: str, poll_seconds: int = 20):
        if not base_url.startswith("https://"):
            raise KaggleWorkerError("GPU_MESH_API_URL must use HTTPS")
        if not username or not worker_token or not node_id:
            raise KaggleWorkerError("Kaggle worker identity is incomplete")
        if not shutil.which("kaggle"):
            raise KaggleWorkerError("Kaggle CLI is not installed; install klod-ai[kaggle]")
        if not os.environ.get("KAGGLE_API_TOKEN"):
            raise KaggleWorkerError("KAGGLE_API_TOKEN is required")
        self.base_url = base_url.rstrip("/")
        self.node_id = node_id
        self.worker_token = worker_token
        self.username = username
        self.accelerator = accelerator
        self.poll_seconds = max(10, min(120, int(poll_seconds)))

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

    def _cli(self, args: list[str], timeout: int = 120) -> str:
        try:
            completed = subprocess.run(
                ["kaggle", *args],
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=os.environ.copy(),
            )
        except subprocess.TimeoutExpired as exc:
            raise KaggleWorkerError("Kaggle CLI command timed out") from exc
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "Kaggle CLI failed")[-2000:]
            raise KaggleWorkerError(detail)
        return completed.stdout[-6000:]

    def _heartbeat(self, profile: dict[str, Any]) -> None:
        self._api(
            f"/v1/mesh/workers/{self.node_id}/heartbeat",
            method="POST",
            body={
                "cpu_available": profile["cpu_cores"],
                "ram_available_gib": profile["ram_gib"],
                "storage_available_gib": profile["storage_gib"],
                "gpus": profile["gpus"],
            },
        )

    def _status(self, kernel_id: str) -> str:
        output = self._cli(["kernels", "status", kernel_id], timeout=90)
        match = re.search(
            r"KernelWorkerStatus\.([A-Z_]+)|status[\"']?\s*[:=]\s*[\"']?([A-Z_]+)",
            output,
            re.IGNORECASE,
        )
        if match:
            return (match.group(1) or match.group(2)).upper()
        upper = output.upper()
        for state in ("CANCEL_ACKNOWLEDGED", "CANCEL_REQUESTED", "COMPLETE", "RUNNING", "QUEUED", "ERROR"):
            if state in upper:
                return state
        return "UNKNOWN"

    def _submit(self, manifest: dict[str, Any]) -> tuple[str, Path]:
        task_id = str(manifest["task_id"])
        slug = "gpu-mesh-" + re.sub(r"[^a-f0-9]", "", task_id.lower())[:24]
        metadata = build_kernel_metadata(
            self.username, slug, manifest["workload"], self.accelerator
        )
        workspace = Path(tempfile.mkdtemp(prefix="gpu-mesh-kaggle-"))
        (workspace / "main.py").write_text(render_kernel_script(manifest), encoding="utf-8")
        (workspace / "kernel-metadata.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        args = ["kernels", "push", "--path", str(workspace),
                "--timeout", str(int(manifest["max_runtime_seconds"]))]
        if manifest["workload"] in ("gpu-matmul", "gpu-mandelbrot"):
            args.extend(["--accelerator", self.accelerator])
        try:
            self._cli(args, timeout=max(300, min(1800, int(manifest["max_runtime_seconds"]) + 180)))
        except Exception:
            shutil.rmtree(workspace, ignore_errors=True)
            raise
        return metadata["id"], workspace

    def _poll(self, kernel_id: str, manifest: dict[str, Any],
              lease_token: str, profile: dict[str, Any]) -> str:
        deadline = time.monotonic() + int(manifest["max_runtime_seconds"]) + 300
        next_renew = time.monotonic()
        while time.monotonic() < deadline:
            state = self._status(kernel_id)
            if state in ("COMPLETE", "ERROR", "CANCEL_ACKNOWLEDGED"):
                return state
            if state in ("CANCEL_REQUESTED",):
                raise KaggleWorkerError("Kaggle task cancellation was requested")
            now = time.monotonic()
            if now >= next_renew:
                self._heartbeat(profile)
                lease = self._api(
                    f"/v1/mesh/workers/{self.node_id}/tasks/{manifest['task_id']}/renew",
                    method="POST",
                    lease_token=lease_token,
                )
                if lease.get("cancel_requested"):
                    raise KaggleWorkerError("GPU Mesh cancellation was requested")
                next_renew = now + 30
            time.sleep(self.poll_seconds)
        raise KaggleWorkerError("Kaggle execution exceeded the Mesh task deadline")

    def _download_result(self, kernel_id: str, workspace: Path) -> dict[str, Any]:
        output_dir = workspace / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        self._cli(
            ["kernels", "output", kernel_id, "--path", str(output_dir)],
            timeout=180,
        )
        result_path = (output_dir / "gpu_mesh_result.json").resolve()
        if output_dir.resolve() not in result_path.parents or not result_path.is_file():
            raise KaggleWorkerError("Kaggle output did not contain gpu_mesh_result.json")
        if result_path.stat().st_size > 65536:
            raise KaggleWorkerError("Kaggle result exceeds 64 KiB")
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if not isinstance(result, dict):
            raise KaggleWorkerError("Kaggle returned an invalid result")
        return result

    def run_once(self, profile: dict[str, Any]) -> bool:
        claimed = self._api(
            f"/v1/mesh/workers/{self.node_id}/tasks/claim",
            method="POST",
        ).get("task")
        if not claimed:
            return False
        manifest = claimed["manifest"]
        lease_token = claimed["lease_token"]
        if not verify_manifest(
            manifest, claimed["manifest_signature"], self.worker_token, self.node_id
        ):
            raise KaggleWorkerError("Task manifest signature is invalid")
        start = self._api(
            f"/v1/mesh/workers/{self.node_id}/tasks/{manifest['task_id']}/start",
            method="POST",
            lease_token=lease_token,
        )
        if not start.get("started"):
            return True
        workspace = None
        kernel_id = None
        try:
            kernel_id, workspace = self._submit(manifest)
            state = self._poll(kernel_id, manifest, lease_token, profile)
            if state != "COMPLETE":
                raise KaggleWorkerError(f"Kaggle kernel ended with status {state}")
            result = self._download_result(kernel_id, workspace)
            completed = self._api(
                f"/v1/mesh/workers/{self.node_id}/tasks/{manifest['task_id']}/complete",
                method="POST",
                lease_token=lease_token,
                body={"result": result},
            )
            if completed.get("completed") or completed.get("cancelled"):
                return True
            raise KaggleWorkerError("GPU Mesh did not accept the Kaggle result")
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
            if workspace is not None:
                if kernel_id and os.getenv("GPU_MESH_KAGGLE_KEEP_KERNELS", "false").lower() != "true":
                    try:
                        self._cli(["kernels", "delete", kernel_id, "--yes"], timeout=60)
                    except Exception:
                        pass
                shutil.rmtree(workspace, ignore_errors=True)

    def run_forever(self) -> None:
        profile = _resource_profile()
        while True:
            try:
                self._heartbeat(profile)
                if not self.run_once(profile):
                    time.sleep(10)
            except KeyboardInterrupt:
                break
            except Exception:
                time.sleep(20)


def main() -> None:
    base_url = os.environ.get("GPU_MESH_API_URL", "").rstrip("/")
    access_token = os.environ.get("GPU_MESH_ACCESS_TOKEN", "")
    state_path = Path(os.environ.get(
        "GPU_MESH_KAGGLE_WORKER_STATE",
        str(Path.home() / ".gpu-mesh" / "kaggle-worker.json"),
    )).expanduser()
    username = os.environ.get("KAGGLE_USERNAME", "")
    if not base_url.startswith("https://"):
        raise SystemExit("GPU_MESH_API_URL must use HTTPS")
    if not access_token:
        raise SystemExit("GPU_MESH_ACCESS_TOKEN is required for worker enrollment")
    if not username:
        raise SystemExit("KAGGLE_USERNAME is required")
    if not os.environ.get("KAGGLE_API_TOKEN"):
        raise SystemExit("KAGGLE_API_TOKEN is required; keep it outside the repository")
    profile = _resource_profile()
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        node_id = state["node_id"]
        worker_token = state["worker_token"]
    else:
        response = _request(
            base_url + "/v1/mesh/workers",
            access_token,
            method="POST",
            body={
                "provider_id": "kaggle-notebooks",
                "cpu_cores": profile["cpu_cores"],
                "ram_gib": profile["ram_gib"],
                "storage_gib": 0,
                "gpus": profile["gpus"],
                "shared": os.getenv("GPU_MESH_SHARE", "false").lower() == "true",
            },
        )
        node_id = response["node_id"]
        worker_token = response["worker_token"]
        state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps({
            "node_id": node_id,
            "worker_token": worker_token,
        }), encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(state_path)
        os.chmod(state_path, 0o600)

    KaggleKernelAdapter(
        base_url,
        node_id,
        worker_token,
        username,
        profile["accelerator"],
        poll_seconds=_env_int("GPU_MESH_KAGGLE_POLL_SECONDS", 20, 10, 120),
    ).run_forever()


if __name__ == "__main__":
    main()
