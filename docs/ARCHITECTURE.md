# KLOD 0.5 architecture

- General-purpose system prompt and open-domain fallback.
- Conservative domain router with an explicit force-general option.
- Optional modules for programming, science, mathematics, research, writing, education, creative work, business and Minecraft.
- Qwen3-1.7B foundation model with optional PEFT adapter.
- Multilingual E5 embeddings, loaded lazily and locally.
- SQLite memory with optional semantic recall.
- Source-attributed knowledge documents, overlapping passages, FTS5 and vector similarity.
- Reciprocal-rank fusion for lexical and semantic retrieval.
- Authenticated REST API; callers may inspect or override routing.
- Structured action planner checked against caller allowlists; it does not execute actions.
- Continued pretraining, assistant-only SFT, DPO and held-out evaluation pipeline.

All specialist modules share the same language model. They are prompt and retrieval configurations, not independent expert models. The domain router is a deterministic routing utility, not a second AI model.

SQLite's brute-force vector scan is suitable for small and medium collections. Use a vector database for very large indexes.
