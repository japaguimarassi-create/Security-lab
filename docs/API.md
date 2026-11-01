# Klod REST API

Set `KLOD_API_KEY` to a long random secret. Every `/v1/*` endpoint requires header `X-API-Key`.

## Run

```bash
pip install -e ".[model]"
KLOD_API_KEY='replace-with-secret' KLOD_LOAD_MODEL=true uvicorn klod.api:app --host 127.0.0.1 --port 8000
```

## Chat with optional memory and retrieved documents

```bash
curl -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" -H "X-API-Key: $KLOD_API_KEY" \
  -d '{"messages":[{"role":"user","content":"Explique o assunto"}],"memory_namespace":"villager-14","knowledge_namespace":"minecraft"}'
```

## Knowledge ingestion

```json
{"namespace":"minecraft","title":"Documento técnico","body":"Texto do documento com pelo menos 80 caracteres ...","source_url":"https://example.org/docs","license":"CC-BY-4.0","attribution":"Autor / projeto"}
```

POST it to `/v1/knowledge/documents`. The API accepts only an explicit license allowlist and preserves provenance. This endpoint stores supplied content; it does not crawl arbitrary URLs.

Search with `POST /v1/knowledge/search` and `{"namespace":"minecraft","query":"Forge entity registration","limit":5}`.

## Structured action planning

POST `/v1/actions/plan` with `task`, `environment`, and `allowed_actions`. The response has `executed:false`. The client must validate state, permissions and parameters before executing any action.

## Status and loading

- `GET /health`: unauthenticated health and model-load status.
- `GET /v1/models`: model metadata.
- `POST /v1/models/load`: explicitly load the model after API startup.

Do not expose this API to the public internet without TLS, rate limiting, key rotation and request-size limits.
