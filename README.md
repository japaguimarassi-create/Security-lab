# KLOD AI + GPU Mesh Core 0.8.0

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

## Treinamento no GitHub

Consulte [docs/GITHUB_TRAINING.md](docs/GITHUB_TRAINING.md) para a execução gratuita por GitHub Actions em CPU, revisão dos exemplos, sequência das cinco etapas e recuperação dos artefatos. O modelo professor e aluno continuam sendo Qwen3-1.7B. O fluxo das cinco etapas usa LoRA FP32 sem bitsandbytes, pois os runners gratuitos não têm GPU. O teste cpu_smoke verifica a memória e um passo real de retropropagação antes do treino completo.

## Important training distinction

The teacher is frozen during generation; it does not update student weights directly. It supplies demonstrations. The student learns through supervised fine-tuning of its LoRA adapter. No trained adapter is included in GitHub, and no GPU training is claimed until the commands have actually run and evaluation has passed.

See `docs/TRAINING.md`, `docs/ARCHITECTURE.md`, `docs/API.md` and `docs/SPECIALISTS.md`.


## Blinded teacher/student evaluation

A separate eight-question held-out set is provided at `data/eval/distillation_heldout.jsonl`. It is not included in the training mixture or teacher prompt seeds. After training the adapter, run `python scripts/evaluate_teacher_student.py`. The tool generates both models' answers for the same held-out prompts, randomizes A/B order, and writes the mapping to `evaluation/distillation_answer_key.json`. Keep the answer key private until blind human review is complete. Do not train on the held-out prompts or their answers.


## GPU Mesh Core

GPU Mesh adds a protected resource-control dashboard at `/mesh`, with account registration, per-device GPU/VRAM inventory, CPU/RAM visibility, voluntary worker heartbeats, weekly quotas and task-allocation planning.

Read [docs/GPU_MESH.md](docs/GPU_MESH.md) for the full branch architecture, provider limits, deployment model and cryptographic design.

### Start the API and dashboard

Install the base package and start the service:

```bash
python -m pip install -e .
KLOD_API_KEY='use-a-long-random-secret' uvicorn klod.api:app --host 127.0.0.1 --port 8000
```

Open `/mesh` in the browser. The dashboard uses separate account sessions; KLOD's legacy endpoints continue to require `X-API-Key`.

### Volunteer worker

On a machine you own, install the worker extra and run it with an account access token:

```bash
python -m pip install -e ".[worker]"
export GPU_MESH_API_URL="https://your-domain"
export GPU_MESH_ACCESS_TOKEN="account-session-token"
export GPU_MESH_SHARE="true"
gpu-mesh-worker
```

Sharing is disabled unless `GPU_MESH_SHARE=true` is explicitly set. After enrollment, the worker uses its dedicated node token. It claims signed task manifests and executes only the built-in `cpu-sha256`, `gpu-matmul` and `gpu-mandelbrot` workloads. Arbitrary scripts and shell commands are not accepted.



### Kaggle private-kernel worker

The optional adapter submits one private Kaggle kernel per task using the Kaggle CLI, polls status and downloads the output artifact. It needs the owner's Kaggle API token and an explicitly configured hardware profile:

```bash
pip install -e ".[kaggle]"
export GPU_MESH_API_URL="https://your-domain"
export GPU_MESH_ACCESS_TOKEN="account-session-token"
export KAGGLE_USERNAME="your-kaggle-user"
export KAGGLE_API_TOKEN="your-kaggle-api-token"
export GPU_MESH_KAGGLE_ACCELERATOR="NvidiaTeslaT4"
export GPU_MESH_KAGGLE_GPU_COUNT="1"
export GPU_MESH_KAGGLE_GPU_VRAM_GIB="16"
export GPU_MESH_SHARE="true"
gpu-mesh-kaggle-worker
```

Private kernels are removed after their output is collected by default. Set `GPU_MESH_KAGGLE_KEEP_KERNELS=true` to preserve them. The declared hardware profile must match the accelerator your account can actually run.

### Hugging Face ZeroGPU worker

Deploy the contents of [examples/huggingface_zerogpu](examples/huggingface_zerogpu) as a Gradio Space. Then install the optional bridge and configure your own Space and HF token:

```bash
pip install -e ".[huggingface]"
export GPU_MESH_API_URL="https://your-domain"
export GPU_MESH_ACCESS_TOKEN="account-session-token"
export HF_TOKEN="your-hf-token"
export GPU_MESH_HF_SPACE_ID="your-user/your-space"
export GPU_MESH_HF_ZEROGPU_SIZE="large"
export GPU_MESH_SHARE="true"
gpu-mesh-hf-worker
```

The default ZeroGPU worker profile is 48 GiB with a 120-second per-task limit; xlarge advertises 96 GiB. The bridge checks the user's ZeroGPU remaining quota before dispatch. Provider quota and queue availability are not guaranteed by GPU Mesh.

### Google Colab

Open [examples/colab/GPU_Mesh_Worker.ipynb](examples/colab/GPU_Mesh_Worker.ipynb) in Colab, select a runtime accelerator, enter the GPU Mesh HTTPS URL and account token, then run the cells. This is an interactive worker tied to that Colab session; it goes offline when the session ends.

### Task dispatch and rebalancing

The dashboard submits allowlisted task payloads, shows task results and supports cancellation. Jobs with no available worker remain in a persisted queue. When more workers join, use **Alocar pendentes** in the dashboard or call `POST /v1/mesh/jobs/{job_id}/reschedule`. The server reserves resources and weekly quota before assigning each pending task.

CPU SHA-256 results are recomputed server-side. CUDA results are reported by the worker and are not remote hardware attestations. The worker process is bounded and uses OS resource limits where supported; it is not a container or microVM.

### Encrypted source archive

The canonical general-relativity corpus in `src/klod/mesh/relativity.py` is a mandatory component of Argon2id key derivation. AES-256-GCM encrypts the exported source bundle. A private random `GPU_MESH_MASTER_SECRET` (at least 32 bytes) is also mandatory; public mathematical formulas alone are not a secret. Configure that value as a GitHub Actions secret to run the encrypted archive workflow. Source files and Git history in this public repository remain readable; the vault encrypts the exported archive, not the public Git objects.


## Vercel + Neon website deployment

The GPU Mesh dashboard can run on Vercel's free personal Hobby plan with a Neon Free PostgreSQL database. The deployment uses the lightweight FastAPI entrypoint in `index.py` and static files in `public/`; it does not load Qwen or run a persistent worker process. See [docs/DEPLOY_VERCEL_NEON.md](docs/DEPLOY_VERCEL_NEON.md) for setup, secrets and verification.
