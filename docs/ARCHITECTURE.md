# KLOD 0.4 architecture

- **Language model:** Qwen3-1.7B foundation with optional PEFT adapter.
- **Embedding model:** multilingual-e5-small, independent from the language model; loaded lazily and executed locally.
- **Inference engine:** official model chat template, input/output bounds, generation lock and optional PEFT adapter.
- **Memory:** namespace-isolated SQLite records with optional normalized embedding vectors.
- **Knowledge:** source-attributed documents, overlapping passages, FTS5 lexical search and vector similarity.
- **Rank fusion:** reciprocal-rank fusion combines lexical and semantic candidates.
- **Specialists:** programming/Minecraft system prompts and default knowledge namespaces.
- **Planner:** JSON proposals checked against caller allowlists; no game action is executed by the API.
- **API:** authenticated REST endpoints; mods call it asynchronously.
- **Training:** continued pretraining, assistant-only SFT, DPO and held-out evaluation.

SQLite's brute-force vector scan is for small and medium local collections. Use a vector DB/pgvector for large indexes.
