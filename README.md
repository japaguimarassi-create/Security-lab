# KLOD AI 0.5.0

KLOD is a general-purpose multilingual AI runtime. It is designed for open-domain conversation and work across everyday questions, programming, science, mathematics, research, education, writing, creative development, business and specialized technical subjects. Minecraft is one optional specialist, not the identity or limit of the system.

## Core capabilities

- One persistent general-purpose assistant prompt and a shared language-model runtime.
- Conservative automatic domain routing with a general fallback for ambiguous or unfamiliar topics.
- Optional specialist prompts for programming, science, mathematics, research, writing, education, creative development, business and Minecraft.
- SQLite persistent memory with lexical and optional semantic recall.
- Hybrid knowledge retrieval: FTS5 + multilingual embeddings + reciprocal-rank fusion.
- Source/license/attribution metadata returned with retrieved answers.
- Structured action planner with caller-provided allowlists; plans are not executed automatically.
- Continued pretraining, SFT, DPO and evaluation pipeline.

## Quick start

Python 3.11+:

\`\`\`bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[model,embeddings]"
cp .env.example .env
uvicorn klod.api:app --host 127.0.0.1 --port 8000
\`\`\`

Set a strong \`KLOD_API_KEY\`. Keep \`KLOD_LOAD_MODEL=false\` until the device has enough memory; generation returns 503 until the model is loaded. The embedding model loads lazily on first semantic use and runs locally. Set \`KLOD_SEMANTIC_SEARCH=false\` to disable it.

## General chat and automatic routing

Use \`POST /v1/chat/completions\` for every subject. The router may select a focused prompt when the user's message clearly matches a domain. Unclear requests stay with the general assistant.

\`\`\`json
{
  "messages": [{"role": "user", "content": "Explique a relatividade geral."}],
  "auto_route": true
}
\`\`\`

Use \`"auto_route": false\` to force the general assistant, or set \`"specialist": "science"\` to choose a specialist explicitly. The response includes \`specialist\` and \`routing\` metadata. Check \`POST /v1/route\` to inspect a routing decision before sending a request.

## Optional specialist modules

Available modules: \`general\`, \`programming\`, \`science\`, \`mathematics\`, \`research\`, \`writing\`, \`education\`, \`creative\`, \`business\` and \`minecraft\`.

- \`GET /v1/specialists\`
- \`POST /v1/specialists/{name}/chat\`

All modules use the same foundation language model. They are prompts and optional knowledge namespaces, not separate trained model weights.

## Semantic knowledge

Documents keep source URL, license and attribution. They are split into passages and indexed with \`intfloat/multilingual-e5-small\`. The API performs hybrid lexical/semantic retrieval and returns source metadata. Local SQLite vector scanning suits small corpora; use a vector database as the corpus grows.

The E5-small embedding model supports multilingual retrieval and is separate from KLOD's language model. It is downloaded from Hugging Face on first use.

## Training status

This repository includes training code, configs and a Colab notebook. No KLOD-specific language-model adapter is claimed until an actual GPU run creates and evaluates it. The current runtime uses an external Qwen3 foundation model; adding specialist prompts does not create separately trained expert models.

See \`docs/API.md\`, \`docs/SPECIALISTS.md\`, \`docs/TRAINING.md\` and \`docs/ARCHITECTURE.md\`.
