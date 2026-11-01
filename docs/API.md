# KLOD REST API v0.5

Every /v1 endpoint requires the X-API-Key header. Set KLOD_API_KEY to a strong secret before running the server.

## Endpoints

- GET /health: runtime, model and embedding status.
- GET /v1/models and POST /v1/models/load: model metadata and loading.
- POST /v1/chat/completions: default general chat with optional automatic domain routing.
- GET /v1/specialists: available optional modules.
- POST /v1/route: inspect a message's route.
- POST /v1/specialists/{name}/chat: explicitly select a module.
- POST /v1/actions/plan: allowlist-validated plans; the API does not execute them.
- POST /v1/memory and /v1/memory/search: persistent memory.
- POST /v1/knowledge/documents, /v1/knowledge/index and /v1/knowledge/search: sourced retrieval.

Chat accepts specialist (optional explicit module) and auto_route (default true). Explicit specialist selection wins. Set auto_route=false to force the general-purpose prompt. The router selects a module only when it detects clear subject signals; vague and unfamiliar topics remain general. Responses include specialist and routing metadata.

Example request:

```json
{"messages":[{"role":"user","content":"Explique a relatividade geral."}],"auto_route":true}
```

Install and run:

```bash
pip install -e ".[model,embeddings]"
KLOD_API_KEY='replace-with-secret' KLOD_LOAD_MODEL=true uvicorn klod.api:app --host 127.0.0.1 --port 8000
```

The embedding model is loaded locally on first semantic use. Set KLOD_SEMANTIC_SEARCH=false to disable semantic retrieval. Documents retain source URL, license and attribution. SQLite vector scanning is intended for modest corpora; consider Qdrant or pgvector for large indexes.

All domain modules use the same language model. They are prompt and retrieval configurations, not separately trained model weights. Retrieved documents are evidence, not executable instructions. The action planner only returns proposals; client applications must validate permissions and state before acting.
