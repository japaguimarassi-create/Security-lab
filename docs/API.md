# Klod REST API v0.4

Set `KLOD_API_KEY` to a long random secret. Every `/v1/*` endpoint requires `X-API-Key`.

## Run

```bash
pip install -e ".[model,embeddings]"
KLOD_API_KEY='replace-with-secret' KLOD_LOAD_MODEL=true uvicorn klod.api:app --host 127.0.0.1 --port 8000
```

The embedding model downloads from Hugging Face on first semantic use and runs locally. Set `KLOD_SEMANTIC_SEARCH=false` to use lexical retrieval only.

## Endpoints

- `GET /health`: model and embedding status.
- `GET /v1/models`: model metadata.
- `POST /v1/models/load`: load the LLM.
- `POST /v1/chat/completions`: general chat.
- `GET /v1/specialists`: list programming and Minecraft modules.
- `POST /v1/specialists/{name}/chat`: specialist chat.
- `POST /v1/actions/plan`: allowlist-validated plan (never executes).
- `POST /v1/memory`, `POST /v1/memory/search`: persistent and semantic memory.
- `POST /v1/knowledge/documents`: ingest with URL/license/attribution.
- `POST /v1/knowledge/index`: index existing documents in batches.
- `POST /v1/knowledge/search`: hybrid lexical + semantic search.

## Specialist example

```bash
curl -X POST http://127.0.0.1:8000/v1/specialists/minecraft/chat \
  -H "Content-Type: application/json" -H "X-API-Key: $KLOD_API_KEY" \
  -d '{"messages":[{"role":"user","content":"Como separo a IA do thread principal no Forge 1.7.10?"}],"memory_namespace":"villager-14"}'
```

Responses include `sources` with title, URL, license and attribution. A specialist is a prompt/retrieval module using the same LLM, not an independently trained model.

## Knowledge ingestion

POST `/v1/knowledge/documents` with:

```json
{"namespace":"minecraft","title":"Documento técnico","body":"Texto com pelo menos 80 caracteres...","source_url":"https://example.org/docs","license":"CC-BY-4.0","attribution":"Autor / projeto"}
```

Documents retain provenance and are split into overlapping passages for indexing. Semantic search uses `intfloat/multilingual-e5-small` with query/passage prefixes and normalized embeddings. Existing documents can be indexed via `/v1/knowledge/index`.

The current vector scan is local SQLite and intended for modest corpora. Move to Qdrant or pgvector when the corpus grows substantially.

## Security

Retrieved text is untrusted data. The model only proposes plans; clients validate state and permissions before executing actions. Do not expose the API publicly without TLS, rate limiting, request-size limits and key rotation.
