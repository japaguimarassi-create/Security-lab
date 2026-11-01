# KLOD AI 0.4.0

Klod is a modular multilingual LLM platform with a REST API, persistent memory, semantic knowledge retrieval, specialist prompts and staged training.

## Modules

- Qwen3 1.7B inference engine with optional PEFT adapter.
- SQLite memory with lexical + semantic recall.
- Hybrid knowledge retrieval: FTS5 + multilingual embeddings + reciprocal-rank fusion.
- Programming and Minecraft specialist modules.
- Structured planner with caller-provided action allowlists.
- Continued pretraining, SFT, DPO and evaluation pipeline.

## Quick start

Python 3.11+:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[model,embeddings]"
cp .env.example .env
uvicorn klod.api:app --host 127.0.0.1 --port 8000
```

Set a strong `KLOD_API_KEY`. Keep `KLOD_LOAD_MODEL=false` until the device has enough memory; generation returns 503 until model loading is enabled. The embedding model loads lazily on first semantic use and runs locally. Set `KLOD_SEMANTIC_SEARCH=false` to disable it.

## Specialists

- `POST /v1/specialists/programming/chat`
- `POST /v1/specialists/minecraft/chat`
- `GET /v1/specialists`

These are prompt and retrieval modules sharing one LLM; they are not separately trained model weights.

## Semantic knowledge

Documents keep source URL, license and attribution. They are split into passages and indexed with `intfloat/multilingual-e5-small`. The API performs hybrid lexical/semantic retrieval and returns source metadata. Local SQLite vector scanning suits small corpora; use a vector database as the corpus grows.

The E5-small embedding model supports 94 languages, uses 384-dimensional vectors and is MIT licensed. It is separate from Klod's 1.7B language model. It is downloaded from Hugging Face on first use.

## Training status

This repository includes training code, configs and a Colab notebook. No KLOD-specific 1.7B adapter is claimed until an actual GPU run creates and evaluates it. A phone or ordinary GitHub CPU runner is not adequate training infrastructure.

See `docs/API.md`, `docs/SPECIALISTS.md`, `docs/TRAINING.md` and `docs/ARCHITECTURE.md`.
