import json
import os

import gradio as gr
import spaces

from klod.mesh.workloads import execute_workload, validate_workload


SPACE_SIZE = os.getenv("HF_ZEROGPU_SIZE", "large").lower()
if SPACE_SIZE not in ("large", "xlarge"):
    raise RuntimeError("HF_ZEROGPU_SIZE must be large or xlarge")

try:
    SPACE_MAX_TASK_SECONDS = int(os.getenv("GPU_MESH_HF_MAX_TASK_SECONDS", "120"))
except ValueError as exc:
    raise RuntimeError("GPU_MESH_HF_MAX_TASK_SECONDS must be an integer") from exc

if not 1 <= SPACE_MAX_TASK_SECONDS <= 120:
    raise RuntimeError("GPU_MESH_HF_MAX_TASK_SECONDS must be between 1 and 120")

SPACE_PROFILE = {
    "size": SPACE_SIZE,
    "vram_gib": 48 if SPACE_SIZE == "large" else 96,
    "max_task_seconds": SPACE_MAX_TASK_SECONDS,
    "quota_multiplier": 2 if SPACE_SIZE == "xlarge" else 1,
}


def get_gpu_mesh_profile() -> dict:
    return dict(SPACE_PROFILE)


def _gpu_duration(workload: str, payload_json: str, device_index: int,
                  max_runtime_seconds: int) -> int:
    runtime = int(max_runtime_seconds)
    if not 1 <= runtime <= SPACE_MAX_TASK_SECONDS:
        raise gr.Error("Requested runtime exceeds this Space's configured task duration.")
    payload = json.loads(payload_json)
    if workload not in ("gpu-matmul", "gpu-mandelbrot"):
        raise gr.Error("The GPU endpoint accepts only allowlisted CUDA workloads.")
    validate_workload(workload, payload)
    return runtime


@spaces.GPU(size=SPACE_SIZE, duration=_gpu_duration)
def run_gpu_task(workload: str, payload_json: str, device_index: int,
                 max_runtime_seconds: int) -> dict:
    payload = json.loads(payload_json)
    validate_workload(workload, payload)
    result = execute_workload(workload, payload, int(device_index))
    result["gpu_mesh_space_profile"] = get_gpu_mesh_profile()
    return result


def run_cpu_task(workload: str, payload_json: str) -> dict:
    if workload != "cpu-sha256":
        raise gr.Error("The CPU endpoint accepts only cpu-sha256.")
    payload = json.loads(payload_json)
    validate_workload(workload, payload)
    return execute_workload(workload, payload)


with gr.Blocks(title="GPU Mesh ZeroGPU Bridge") as demo:
    gr.Markdown("# GPU Mesh · Hugging Face ZeroGPU")
    gr.Markdown("Private bridge API for allowlisted GPU Mesh tasks. GPU capacity is allocated only while a GPU function runs.")
    with gr.Tab("Bridge profile"):
        profile_view = gr.JSON(label="Effective Space hardware profile", value=get_gpu_mesh_profile())
        profile_button = gr.Button("Refresh profile")
        profile_button.click(
            get_gpu_mesh_profile,
            outputs=profile_view,
            api_name="mesh_profile",
        )
    with gr.Tab("CUDA workload"):
        gpu_workload = gr.Dropdown(
            choices=["gpu-matmul", "gpu-mandelbrot"],
            value="gpu-matmul",
            label="Workload",
        )
        gpu_payload = gr.Code(
            value='{"matrix_size":512,"seed":42}',
            language="json",
            label="JSON payload",
        )
        gpu_index = gr.Number(value=0, precision=0, label="CUDA device index")
        runtime = gr.Number(
            value=min(60, SPACE_MAX_TASK_SECONDS),
            precision=0,
            minimum=1,
            maximum=SPACE_MAX_TASK_SECONDS,
            label="Maximum runtime (seconds)",
        )
        gpu_button = gr.Button("Run CUDA workload")
        gpu_result = gr.JSON(label="Result")
        gpu_button.click(
            run_gpu_task,
            inputs=[gpu_workload, gpu_payload, gpu_index, runtime],
            outputs=gpu_result,
            api_name="run_gpu_task",
        )
    with gr.Tab("CPU workload"):
        cpu_payload = gr.Code(
            value='{"text":"GPU Mesh","iterations":10000}',
            language="json",
            label="JSON payload",
        )
        cpu_button = gr.Button("Run CPU workload")
        cpu_result = gr.JSON(label="Result")
        cpu_button.click(
            run_cpu_task,
            inputs=[gr.State("cpu-sha256"), cpu_payload],
            outputs=cpu_result,
            api_name="run_cpu_task",
        )


if __name__ == "__main__":
    demo.launch()
