# Deploy KLOD GPU Mesh

This deployment publishes the GPU Mesh dashboard and its API from one FastAPI container. The dashboard is available at `/` and `/mesh`; the health endpoint is `/healthz`.

## Railway service

1. Create a Railway project and connect `japaguimarassi-create/Security-lab`, branch `main`.
2. Use the repository Dockerfile. The container binds to the injected `PORT` (fallback 8000).
3. Attach one persistent volume at `/data`. Keep the service at one replica because this release uses SQLite databases on a single mounted volume.
4. Set the deployment healthcheck path to `/healthz`.
5. Enable Serverless/App Sleep to reduce idle compute usage. A sleeping service starts on the next request; the first request can be slower.
6. Generate the public Railway domain and keep HTTPS enabled.

## Required variables

Set these in the hosting provider's secret-variable interface. Never commit the secret values.

| Variable | Value |
|---|---|
| `KLOD_LOAD_MODEL` | `false` |
| `KLOD_DATABASE_PATH` | `/data/klod.sqlite3` |
| `GPU_MESH_DATABASE_PATH` | `/data/gpu_mesh.sqlite3` |
| `KLOD_API_KEY` | Generate a random secret with at least 32 bytes |
| `GPU_MESH_MASTER_SECRET` | Generate a different random secret with at least 32 bytes |
| `GPU_MESH_SHARE` | `false` |

The first secret protects the legacy KLOD API. The second is used by the encrypted source-vault feature. Keep both private and back them up securely.

## Verify after deployment

- Open `/` and confirm the GPU Mesh login page appears.
- Open `/healthz`; it should return HTTP 200 and `status: ok`.
- Create an account using a unique email and a password of at least 12 UTF-8 bytes.
- Sign out and sign in again.
- Confirm that the account survives a service restart before inviting workers.
- Register a CPU worker and run the `cpu-sha256` test first.

## Free-plan limits and product scope

The Railway Free plan currently lists a 30-day trial with US$5 in credits, followed by a Free plan with US$1/month in included usage, a 0.5 GB memory limit and up to 0.5 GB volume storage. Compute and storage are usage-metered. Set a hard compute-usage limit in Railway before leaving the deployment unattended. Do not upgrade the plan or raise its spending limit without reviewing the price.

This container deploys the **GPU Mesh control panel and API**, not the Qwen model. Model loading is intentionally disabled because the Free service memory limit is too small for local model inference. GPU work still requires external volunteer/provider workers and their own quotas.
