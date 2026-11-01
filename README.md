# KLOD AI 0.6.0

KLOD is a general-purpose multilingual AI runtime for open-domain conversation and work across everyday questions, programming, science, mathematics, research, education, writing, creative development, business and specialized technical subjects. Minecraft is one optional specialist.

## Core capabilities

- General-purpose assistant with conservative automatic domain routing.
- Optional specialists for programming, science, mathematics, research, writing, education, creative work, business and Minecraft.
- Persistent memory and hybrid lexical/semantic knowledge retrieval.
- Source/license/attribution metadata for retrieved documents.
- Structured action planner that returns proposals without executing them.
- Teacher-student self-distillation: the current Qwen3 instruct model generates candidate demonstrations; a human-reviewed dataset fine-tunes a separate LoRA student adapter on Qwen3-1.7B-Base.
- Continued pretraining, SFT, DPO and evaluation pipelines.

## Quick start

Python 3.11+:

\`\`\`bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[model,embeddings]"
cp .env.example .env
uvicorn klod.api:app --host 127.0.0.1 --port 8000
\`\`\`

Set a strong \`KLOD_API_KEY\`. Keep \`KLOD_LOAD_MODEL=false\` until the device has enough memory. The embedding model loads lazily on first semantic use and runs locally. Set \`KLOD_SEMANTIC_SEARCH=false\` to disable it.

## General chat

Use \`POST /v1/chat/completions\` for every subject. Automatic routing selects a specialist only when the topic is clear. Set \`auto_route=false\` to force the general assistant or use \`specialist\` to select one explicitly.

## Teacher-student training

KLOD 0.6 adds an executable distillation pipeline.

- Teacher: \`Qwen/Qwen3-1.7B\`, matching the current instruct model used by the runtime.
- Student: \`Qwen/Qwen3-1.7B-Base\`, initialized separately with a new LoRA adapter.
- Curriculum: 48 starter prompts spanning science, mathematics, programming, research, history, geography, writing, education, languages, business, data analysis, design, arts and general reasoning.
- Teacher generation parameters: temperature 0.65, top-p 0.90, repetition penalty 1.08, maximum 512 new tokens and 4096 input tokens.
- Student parameters: NF4 QLoRA, LoRA rank 16, alpha 32, dropout 0.05, learning rate 2e-5, sequence length 2048, batch size 1 and gradient accumulation 16.

Generate teacher candidates:

\`\`\`bash
pip install -e ".[training]"
python scripts/training_preflight.py --stage teacher
python scripts/generate_teacher_data.py
\`\`\`

Candidates are written to \`data/generated/teacher_candidates.jsonl\`. Automated checks remove empty, excessively short, excessively long, echoed and highly repetitive responses. These checks do not establish factual correctness. Review each answer and set \`"approved": true\` only when it is correct and useful.

Export reviewed examples and train the student:

\`\`\`bash
python scripts/approve_teacher_data.py --minimum 20
python scripts/training_preflight.py --stage sft --config configs/training/distillation_sft.yaml
python scripts/train_sft.py --config configs/training/distillation_sft.yaml
\`\`\`

The SFT configuration rejects rows that have not passed the automated screen and been explicitly approved. The resulting adapter is saved to \`outputs/klod-teacher-distilled\`. Configure inference with \`KLOD_MODEL_ID=Qwen/Qwen3-1.7B-Base\` and \`KLOD_ADAPTER_PATH=outputs/klod-teacher-distilled\`.

The 48 prompts are a starter curriculum and a pipeline test, not enough to produce broad expert-level capability. Expand the curriculum substantially, use diverse reviewed examples, reserve a separate evaluation set and compare against the teacher before promoting a checkpoint.

## Important training distinction

The teacher is frozen during generation; it does not update the student's weights directly. It supplies demonstrations. The student learns through supervised fine-tuning of its LoRA adapter. No trained adapter is included in GitHub, and no GPU training is claimed until the commands have actually run and evaluation has passed.

See \`docs/TRAINING.md\`, \`docs/ARCHITECTURE.md\`, \`docs/API.md\` and \`docs/SPECIALISTS.md\`.
