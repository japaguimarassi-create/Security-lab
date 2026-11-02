# Vercel + Neon deployment

This deployment serves the GPU Mesh dashboard as Vercel static assets and the FastAPI control plane as a single Python Function. Neon PostgreSQL stores accounts, sessions, workers, resource reservations, quotas, jobs and tasks. The AI model is not loaded by this site.

## Accounts and plan

- Vercel Hobby: free for personal projects, with monthly function and compute quotas.
- Neon Free: 1 GB PostgreSQL storage and 100 compute-hours per project per month. Compute scales to zero after five minutes of inactivity.
- The first request after idle may be slower while Neon resumes its compute. The app opens short-lived database connections for individual operations; use Neon's pooled connection string for the Vercel environment.

Provider quotas can change. Check the current plan dashboards before relying on the limits.

## Vercel project

1. Connect the GitHub repository `japaguimarassi-create/Security-lab`.
2. Select the `main` branch.
3. Keep the repository root as the project root. The Python entrypoint is `index.py`; `pyproject.toml` points Vercel to `index:app`.
4. Keep the static dashboard files in `public/`. The frontend calls the API on the same origin at `/v1/mesh`.
5. Deploy with the Python 3.12 runtime.

## Neon database

1. Create a Neon project on the Free plan.
2. Create a database or use the default database.
3. Copy the pooled connection string (the hostname contains `-pooler`) and store it in Vercel as the secret environment variable `DATABASE_URL`.
4. Do not place the connection string in GitHub files, frontend JavaScript, build logs or chat messages.

The app initializes its database tables during cold start. Do not run multiple app versions against an incompatible schema.

## Required Vercel environment variables

| Variable | Value |
|---|---|
| `DATABASE_URL` | Neon pooled PostgreSQL connection string |
| `KLOD_LOAD_MODEL` | `false` |
| `GPU_MESH_SHARE` | `false` |

The GPU Mesh API resolves `DATABASE_URL` when `GPU_MESH_DATABASE_PATH` is not provided. The web app does not load the Qwen model, run training, or start a persistent worker process.

## Post-deploy validation

1. Open `/healthz`; it must return HTTP 200 and `status: ok`.
2. Open `/` and confirm the login page and static assets load.
3. Register using a unique email and a password of at least 12 UTF-8 bytes.
4. Sign out and sign back in.
5. Register a test CPU worker; verify it appears after a second refresh.
6. Submit one `cpu-sha256` task and confirm the server-verified result.
7. Restart/redeploy the Vercel project and verify the account and worker records remain in Neon.

Do not publish the service as ready until these checks pass.

## Runtime boundaries

- This is a request-driven control plane, not an always-on worker host.
- Workers must run on a separate machine/provider and connect over HTTPS.
- Vercel Function time limits apply to each HTTP request; long-running compute runs on registered workers, not inside the API request.
- The dashboard and API use server-side PostgreSQL. Browser code never receives `DATABASE_URL`.
- The Qwen model remains disabled; the free Vercel Function bundle intentionally contains only the lightweight API and UI dependencies.
