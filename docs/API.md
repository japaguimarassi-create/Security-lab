# KLOD and GPU Mesh REST API v0.8

## Authentication

Legacy KLOD endpoints use `X-API-Key`. Configure `KLOD_API_KEY` before exposing the service; protected routes fail closed when the value is absent.

GPU Mesh routes use account sessions. Register and log in at `POST /v1/mesh/auth/register` and `POST /v1/mesh/auth/login`; send the opaque session as `Authorization: Bearer <token>`. Revoke it with `POST /v1/mesh/auth/logout`. Passwords use Argon2id; session tokens are random and only SHA-256 hashes are stored. Registration and login have database-backed attempt limits.

Each worker receives a separate node token. It is returned once at registration and sent in `X-Worker-Token`. Task operations also require the short-lived `X-Task-Lease`. The owner can revoke a worker. Worker heartbeat does not depend on the account session after enrollment.

## Legacy KLOD endpoints

- `GET /health`
- `GET /v1/models`, `POST /v1/models/load`
- `POST /v1/chat/completions`
- `GET /v1/specialists`, `POST /v1/route`
- `POST /v1/specialists/{name}/chat`
- `POST /v1/actions/plan`
- `POST /v1/memory`, `POST /v1/memory/search`
- `POST /v1/knowledge/documents`, `POST /v1/knowledge/index`, `POST /v1/knowledge/search`

## GPU Mesh account and inventory

- `GET /mesh`: self-hosted dashboard.
- `GET /v1/mesh/providers`: provider catalog.
- `POST /v1/mesh/auth/register`, `POST /v1/mesh/auth/login`, `POST /v1/mesh/auth/logout`.
- `GET /v1/mesh/account`, `GET /v1/mesh/quota`.
- `POST /v1/mesh/workers`, `GET /v1/mesh/workers`, `DELETE /v1/mesh/workers/{node_id}`.
- `POST /v1/mesh/workers/{node_id}/heartbeat`: node-token authenticated.
- `GET /v1/mesh/resources`: online workers and per-device GPU inventory.

Worker registration accepts `volunteer-worker`, `kaggle-notebooks` and `huggingface-zerogpu`. External worker registration advertises provider-specific `max_task_seconds` per GPU. A provider device is not allocated a task whose runtime exceeds that capability.

## Workload and job routes

- `POST /v1/mesh/jobs`: validate a built-in workload, reserve resources and quota, persist assigned and pending tasks.
- `POST /v1/mesh/jobs/{job_id}/reschedule`: attempt to assign persisted pending tasks to newly available workers.
- `GET /v1/mesh/jobs`, `GET /v1/mesh/jobs/{job_id}`.
- `GET /v1/mesh/jobs/{job_id}/results`: execution status and task results.
- `DELETE /v1/mesh/jobs/{job_id}`: cancel queued/leased tasks and request cooperative cancellation from running tasks.

Allowed workload names are exactly:

- `cpu-sha256`: deterministic SHA-256 workload on CPU. The API recomputes the result before accepting it.
- `gpu-matmul`: CUDA matrix multiplication.
- `gpu-mandelbrot`: CUDA Mandelbrot image computation.

The request body contains a JSON `payload`. Example:

```json
{
  "workload": "gpu-matmul",
  "payload": {"matrix_size": 512, "seed": 42},
  "task_count": 2,
  "min_vram_gib_per_task": 1,
  "cpu_cores_per_task": 1,
  "ram_gib_per_task": 2,
  "max_runtime_seconds_per_task": 120
}
```

The server derives whether a workload requires a GPU; the caller cannot override this decision. Payload size, dimensions, iterations, memory and runtime are bounded. Arbitrary Python, shell, notebook source or user-supplied commands are not accepted.

## Worker task protocol

- `POST /v1/mesh/workers/{node_id}/tasks/claim`: return one leased task or `null`.
- `POST /v1/mesh/workers/{node_id}/tasks/{task_id}/start`.
- `POST /v1/mesh/workers/{node_id}/tasks/{task_id}/renew`: renew lease and resource reservation; reports cancellation requests.
- `POST /v1/mesh/workers/{node_id}/tasks/{task_id}/complete`: submit a JSON result.
- `POST /v1/mesh/workers/{node_id}/tasks/{task_id}/fail`: report a bounded error code.

A task manifest is signed with HMAC-SHA256 using the node token. Each claim receives a short-lived lease token; reclaiming a task invalidates the previous lease. Tasks may retry up to the configured attempt limit. Workers run allowlisted functions in a separate child process with OS resource limits where supported.

GPU hashes and device metrics are worker-reported values. The server does not attest the remote GPU or independently prove the execution. CPU SHA-256 jobs are deterministically recomputed before acceptance.

## Provider adapters

- Self-hosted worker: `pip install -e ".[worker]"`, then `gpu-mesh-worker`.
- Kaggle: `pip install -e ".[kaggle]"`, then `gpu-mesh-kaggle-worker`; requires the account owner's `KAGGLE_API_TOKEN`.
- Hugging Face ZeroGPU: deploy `examples/huggingface_zerogpu`, install `.[huggingface]`, then run `gpu-mesh-hf-worker`; requires an HF token, a Space ID, and remaining ZeroGPU quota.
- Google Colab: start the worker in `examples/colab/GPU_Mesh_Worker.ipynb`; the session is interactive and ephemeral.

Provider limits and account quotas remain separate from GPU Mesh internal weekly quotas.

## Security boundary

The current worker isolation is a bounded child process and a strict workload allowlist; it is not a container or microVM. Do not expose privileged workers or run untrusted workers without isolation appropriate to your threat model. Run the API behind HTTPS. See [GPU_MESH.md](GPU_MESH.md) for setup, quotas, cryptography and provider deployment.
