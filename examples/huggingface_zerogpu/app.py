import json

import gradio as gr
import spaces

from klod.mesh.workloads import execute_workload, validate_workload


def _gpu_duration(workload: str, payload_json: str, device_index: int,
                  max_runtime_seconds: int) -> int:
    runtime = int(max_runtime_seconds)
    if not 1 <= runtime <= 120:
        raise gr.Error("ZeroGPU tasks must request a runtime between 1 and 120 seconds.")
    payload = json.loads(payload_json)
    if workload not in ("gpu-matmul", "gpu-mandelbrot"):
        raise gr.Error("The GPU endpoint accepts only allowlisted CUDA workloads.")
    validate_workload(workload, payload)
    return runtime


@spaces.GPU(duration=_gpu_duration)
def run_gpu_task(workload: str, payload_json: str, device_index: int,
                 max_runtime_seconds: int) -> dict:
    payload = json.loads(payload_json)
    validate_workload(workload, payload)
    return execute_workload(workload, payload, int(device_index))


def run_cpu_task(workload: str, payload_json: str) -> dict:
    if workload != "cpu-sha256":
        raise gr.Error("The CPU endpoint accepts only cpu-sha256.")
    payload = json.loads(payload_json)
    validate_workload(workload, payload)
    return execute_workload(workload, payload)


with gr.Blocks(title="GPU Mesh ZeroGPU Bridge") as demo:
    gr.Markdown("# GPU Mesh · Hugging Face ZeroGPU")
    gr.Markdown("Private bridge API for allowlisted GPU Mesh tasks. GPU capacity is allocated only while a GPU function runs.")
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
        runtime = gr.Number(value=60, precision=0, minimum=1, maximum=120,
                            label="Maximum runtime (seconds)")
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
