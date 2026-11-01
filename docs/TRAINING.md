# KLOD training pipeline

## Teacher-student distillation (KLOD 0.6)

The current instruct checkpoint is used as a frozen teacher. It generates candidate answers for a broad curriculum. A separate student starts from Qwen3-1.7B-Base and learns from reviewed teacher demonstrations through a new LoRA adapter. The teacher is not optimized and its weights are not copied into the student; the student receives gradients during SFT.

Model roles:

- Teacher: \`Qwen/Qwen3-1.7B\`, the current instruct model.
- Student base: \`Qwen/Qwen3-1.7B-Base\`.
- Student output adapter: \`outputs/klod-teacher-distilled\`.

The starter curriculum in \`configs/distillation_prompts.jsonl\` has 48 Portuguese and English prompts spanning science, mathematics, programming, research, history, geography, humanities, writing, education, languages, business, data analysis, design, arts and general reasoning. Expand it before treating the result as a broadly capable model.

### Teacher generation parameters

Configured in \`configs/training/distillation.yaml\`:

| Parameter | Value |
|---|---:|
| Teacher model | \`Qwen/Qwen3-1.7B\` |
| Student base | \`Qwen/Qwen3-1.7B-Base\` |
| Maximum input tokens | 4096 |
| Maximum new tokens | 512 |
| Temperature | 0.65 |
| Top-p | 0.90 |
| Repetition penalty | 1.08 |
| Maximum starter prompts | 48 |
| Seed | 42 |
| 4-bit teacher loading | Disabled |

Generate the candidates:

\`\`\`bash
pip install -e ".[training]"
python scripts/training_preflight.py --stage teacher
python scripts/generate_teacher_data.py
\`\`\`

The script stores candidate conversations and provenance metadata at \`data/generated/teacher_candidates.jsonl\`. Automated checks detect empty answers, short/long answers, prompt echoes and excessive repetition. These checks cannot validate factual correctness, so every candidate begins with \`approved: false\`.

Review candidate rows. Change \`approved\` to \`true\` only after checking the answer for accuracy, relevance, clarity, language, code correctness and unsupported claims. Keep rejected examples unapproved. Then export:

\`\`\`bash
python scripts/approve_teacher_data.py --minimum 20
\`\`\`

The export step includes only explicitly approved rows that passed the automated checks. It writes \`data/processed/teacher_approved.jsonl\`. The student training config requires approval metadata; pending examples cannot enter the student training run.

### Student QLoRA parameters

Configured in \`configs/training/distillation_sft.yaml\`:

| Parameter | Value |
|---|---:|
| Base model | \`Qwen/Qwen3-1.7B-Base\` |
| LoRA rank | 16 |
| LoRA alpha | 32 |
| LoRA dropout | 0.05 |
| Learning rate | 0.00002 |
| Maximum sequence length | 2048 |
| Maximum steps | 300 |
| Per-device batch size | 1 |
| Gradient accumulation | 16 |
| Effective batch size | 16 |
| Validation ratio | 5% |
| Quantization | NF4 4-bit |
| Gradient checkpointing | Enabled |
| Seed | 42 |

Run the validation gate and SFT:

\`\`\`bash
python scripts/training_preflight.py --stage sft --config configs/training/distillation_sft.yaml
python scripts/train_sft.py --config configs/training/distillation_sft.yaml
\`\`\`

The adapter will be saved to \`outputs/klod-teacher-distilled\`. To serve it, configure:

\`\`\`bash
KLOD_MODEL_ID=Qwen/Qwen3-1.7B-Base
KLOD_ADAPTER_PATH=outputs/klod-teacher-distilled
\`\`\`

The values above are a controlled starter experiment, not a claim of optimal hyperparameters. The 48 seed prompts are not enough for general-purpose mastery. Grow the dataset to thousands of diverse, reviewed examples, protect a held-out set from contamination, evaluate every major domain and check that the student does not regress against the teacher.

## Other dataset formats

Continued pretraining JSONL uses \`text\`, \`source_url\`, \`license\`, \`language\` and \`attribution\`.

SFT JSONL uses \`messages\`, an array of role/content messages. The final message must be from the assistant. Assistant-only loss is used for conversational instruction data.

DPO JSONL uses \`prompt\`, \`chosen\` and \`rejected\`. Each preference pair must be reviewed.

## Build a broad continued-pretraining corpus

Prepare separate, licensed and quality-filtered corpora for Portuguese, English, Spanish, other languages, code, mathematics/science, humanities, general instruction/conversation and technical documents. The initial mixture is an experiment: Portuguese 30%, English 25%, Spanish 5%, other languages 5%, code 10%, mathematics/science 10%, humanities 5%, instruction/conversation 5% and technical documents 5%.

\`\`\`bash
python scripts/build_mixture.py --config configs/data_mixture.yaml --output data/processed/mixture.jsonl --max-documents 500000
python scripts/training_preflight.py --stage pretrain
python scripts/train_pretrain.py
\`\`\`

## Full training path

After continued pretraining and SFT, prepare at least 100 human-reviewed preference pairs for DPO:

\`\`\`bash
python scripts/training_preflight.py --stage dpo
python scripts/train_dpo.py
python scripts/evaluate.py --model Qwen/Qwen3-1.7B-Base --adapter outputs/klod-dpo --dataset data/eval/heldout.jsonl
\`\`\`

The training scripts use 4-bit NF4 QLoRA and require an NVIDIA CUDA GPU with bitsandbytes support. A GPU with 16 GiB or more is a practical starting point, not a guarantee. Reduce sequence lengths and batch size if memory is insufficient.

## Release gate

The source code and generated candidates are not trained model weights. No adapter is complete until a real GPU run saves it and separate held-out evaluation passes. Record the base revision, adapter hash, datasets, licenses, config digest, Git commit and domain metrics before promoting any checkpoint.
