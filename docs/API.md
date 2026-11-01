# API

Set KLOD_API_KEY before exposing the service. All /v1 routes require X-API-Key.

```bash
curl http://localhost:8000/health
curl -H "X-API-Key: $KLOD_API_KEY" http://localhost:8000/v1/models
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" -H "X-API-Key: $KLOD_API_KEY" \
  -d '{"messages":[{"role":"user","content":"Olá, Klod!"}]}'
```

The generation endpoint returns HTTP 503 while the model is not loaded. Use a separate memory namespace for each app or entity.
