# Klod modules

- **Inference engine**: loads the selected base checkpoint and optional PEFT adapter, applies the model's official chat template, limits context and serializes generation access.
- **Memory**: namespace-isolated SQLite key/value memory, intended for conversations or individual game entities.
- **Knowledge**: SQLite FTS5 keyword retrieval with source URL, license and attribution retained. This is lexical retrieval, not embedding-based semantic search.
- **Planner**: requests a JSON action plan and validates every action against the caller's allowlist. It never executes game actions.
- **API**: authenticated REST interface. Minecraft mods and apps call this service; their own code validates and performs in-game effects.
- **Training**: continued pretraining, supervised fine tuning, preference optimization and held-out evaluation. Training is separate from inference.
