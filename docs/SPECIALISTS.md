# Klod specialists

The API exposes two prompt-specialized modules:
- `programming`: language/runtime/version awareness, complete implementations, debugging and tests.
- `minecraft`: strict game/loader/Java version separation, legacy 1.7.10 constraints, server/client split and safe asynchronous API calls.

List them with `GET /v1/specialists`. Use `POST /v1/specialists/programming/chat` or `POST /v1/specialists/minecraft/chat` with the normal chat request schema.

Specialists are prompt and retrieval modules layered on the same foundation LLM, not separately trained expert weights. Training independent specialist adapters requires reviewed SFT data, held-out evaluations and actual GPU runs.

Minecraft requests search the `minecraft` namespace by default. Responses include retrieved source metadata in `sources`.
