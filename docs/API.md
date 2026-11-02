# KLOD and GPU Mesh REST API v0.7

## Authentication

The legacy KLOD endpoints use the `X-API-Key` header. Configure `KLOD_API_KEY` before exposing those routes; the service fails closed when the value is absent.

GPU Mesh routes use account sessions. Register and log in at `/v1/mesh/auth/register` and `/v1/mesh/auth/login`; send the opaque session as `Authorization: Bearer <token>`. Sessions can be revoked with `POST /v1/mesh/auth/logout`. Passwords use Argon2id, session tokens are random and only their SHA-256 hashes are stored. Registration and login have database-backed attempt limits.

A worker uses a separate per-node secret in the `X-Worker-Token` header for heartbeats. After a worker is enrolled, it does not need to keep the account session alive. The owner can revoke a node.

## Legacy KLOD endpoints

- `GET /health`: runtime, model and embedding status.
- `GET /v1/models` and `POST /v1/models/load`: model metadata and loading.
- `POST /v1/chat/completions`: general chat.
- `GET /v1/specialists`, `POST /v1/route`.
- `POST /v1/specialists/{name}/chat`.
- `POST /v1/actions/plan`: allowlist-validated proposals; no action is executed.
- `POST /v1/memory`, `POST /v1/memory/search`.
- `POST /v1/knowledge/documents`, `POST /v1/knowledge/index`, `POST /v1/knowledge/search`.

## GPU Mesh routes

- `GET /mesh`: browser dashboard.
- `GET /v1/mesh/providers`: provider capability catalog; public.
- `POST /v1/mesh/auth/register`, `POST /v1/mesh/auth/login`, `POST /v1/mesh/auth/logout`.
- `GET /v1/mesh/account`, `GET /v1/mesh/quota`.
- `POST /v1/mesh/workers`, `GET /v1/mesh/workers`, `DELETE /v1/mesh/workers/{node_id}`.
- `POST /v1/mesh/workers/{node_id}/heartbeat`: per-node token only.
- `GET /v1/mesh/resources`: online resource inventory, per physical GPU.
- `POST /v1/mesh/jobs`: create a resource allocation plan.
- `GET /v1/mesh/jobs`, `GET /v1/mesh/jobs/{job_id}`, `DELETE /v1/mesh/jobs/{job_id}`.

A planned job reserves estimated weekly quota. Cancelling a planning-only job releases that reservation. Job planning does not execute a program, create a VM, or start a remote process.

## Example

```bash
curl https://your-domain/v1/mesh/providers
curl -X POST https://your-domain/v1/mesh/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"user@example.com","password":"a-strong-password"}'
```

For resource registration, job planning and encrypted-source commands, consult [GPU_MESH.md](GPU_MESH.md). Serve the API through HTTPS and configure rate limits at the reverse proxy as an additional defense.
