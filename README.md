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

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[model,embeddings]"
cp .env.example .env
uvicorn klod.api:app --host 127.0.0.1 --port 8000
```

Set a strong `KLOD_API_KEY`. Keep `KLOD_LOAD_MODEL=false` until the device has enough memory. The embedding model loads lazily on first semantic use and runs locally. Set `KLOD_SEMANTIC_SEARCH=false` to disable it.

## General chat

Use `POST /v1/chat/completions` for every subject. Automatic routing selects a specialist only when the topic is clear. Set `auto_route=false` to force the general assistant or use `specialist` to select one explicitly.

## Teacher-student training

KLOD 0.6 adds an executable distillation pipeline.

- Teacher: `Qwen/Qwen3-1.7B`, matching the current instruct model used by the runtime.
- Student: `Qwen/Qwen3-1.7B-Base`, initialized separately with a new LoRA adapter.
- Curriculum: 48 starter prompts spanning science, mathematics, programming, research, history, geography, writing, education, languages, business, data analysis, design, arts and general reasoning.
- Teacher generation: temperature 0.65, top-p 0.90, repetition penalty 1.08, 512 maximum new tokens and 4096 input tokens.
- Student: NF4 QLoRA, LoRA rank 16, alpha 32, dropout 0.05, learning rate 2e-5, sequence length 2048, batch size 1, gradient accumulation 16 and 5 epochs.

Generate the teacher's candidate answers:

```bash
pip install -e ".[training]"
python scripts/training_preflight.py --stage teacher
python scripts/generate_teacher_data.py
```

Candidates are saved in `data/generated/teacher_candidates.jsonl`. Review them interactively:

```bash
python scripts/review_teacher_data.py
```

Approve only answers that are correct, relevant and useful. The automatic checks catch empty, short, oversized, echoed and repetitive answers, but do not prove factual correctness. Export the approved records and train:

```bash
python scripts/approve_teacher_data.py --minimum 20
python scripts/training_preflight.py --stage sft --config configs/training/distillation_sft.yaml
python scripts/train_sft.py --config configs/training/distillation_sft.yaml
```

The training config rejects examples that have not passed the automated screen and been explicitly approved. The adapter is saved to `outputs/klod-teacher-distilled`. Configure inference with `KLOD_MODEL_ID=Qwen/Qwen3-1.7B-Base` and `KLOD_ADAPTER_PATH=outputs/klod-teacher-distilled`.

The 48 prompts validate the pipeline; they are not enough to produce broad expert-level ability. Expand the curriculum substantially, use diverse reviewed examples, reserve a separate evaluation set and compare the student against the teacher before promoting a checkpoint.

## Treinamento no Kaggle

Consulte [docs/TREINAMENTO_KAGGLE.md](docs/TREINAMENTO_KAGGLE.md) para configurar o notebook, ativar internet e GPU, aprovar demonstrações e recuperar os resultados. O notebook está em [notebooks/KLOD_Kaggle_Teacher_Distillation.ipynb](notebooks/KLOD_Kaggle_Teacher_Distillation.ipynb).

## Important training distinction

The teacher is frozen during generation; it does not update student weights directly. It supplies demonstrations. The student learns through supervised fine-tuning of its LoRA adapter. No trained adapter is included in GitHub, and no GPU training is claimed until the commands have actually run and evaluation has passed.

See `docs/TRAINING.md`, `docs/ARCHITECTURE.md`, `docs/API.md` and `docs/SPECIALISTS.md`.


## Blinded teacher/student evaluation

A separate eight-question held-out set is provided at `data/eval/distillation_heldout.jsonl`. It is not included in the training mixture or teacher prompt seeds. After training the adapter, run `python scripts/evaluate_teacher_student.py`. The tool generates both models' answers for the same held-out prompts, randomizes A/B order, and writes the mapping to `evaluation/distillation_answer_key.json`. Keep the answer key private until blind human review is complete. Do not train on the held-out prompts or their answers.

Colab notebook: [Open KLOD Teacher Distillation](https://colab.research.google.com/github/japaguimarassi-create/Security-lab/blob/development/notebooks/KLOD_Teacher_Distillation.ipynb).
