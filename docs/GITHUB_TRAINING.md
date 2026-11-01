# KLOD training completely inside GitHub — free CPU edition

This pipeline runs exclusively in GitHub Actions on the standard Linux runner. It does not use Kaggle, Colab, paid GPUs, cloud notebooks or external execution services.

## Why it can be free

GitHub documents standard Linux runners for public repositories as free and unlimited in Actions minutes. The standard `ubuntu-latest` runner provides 4 vCPUs, 16 GB RAM and 14 GB SSD. This free arrangement requires the repository to remain public. Private repositories are subject to the plan's included monthly minutes.

Official references:
- [GitHub runner selection](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job)
- [GitHub Actions billing](https://docs.github.com/en/actions/concepts/billing-and-usage)

Anyone can read a public repository and download its public outputs. Use only public or synthetic examples. Never put secrets, personal information, private records or confidential data in the dataset, logs or artifacts.

## Model and training method

The model architecture and teacher/student identities are preserved:

- Frozen teacher: `Qwen/Qwen3-1.7B`.
- Student: `Qwen/Qwen3-1.7B-Base`.
- Trainable parameters: LoRA adapters only; the base model remains frozen.
- Precision on CPU: FP32.
- Optimizer: PyTorch AdamW.
- Sequence length: 512 tokens for the free runner's memory budget.
- LoRA rank: 8, alpha 16, applied to attention and MLP projections.
- Curriculum: five sequential one-epoch stages, 20%, 40%, 60%, 80% and 100%.

This is **LoRA, not QLoRA**. Four-bit quantization and bitsandbytes are disabled because the free runner has no CUDA GPU. FP32 base weights use more RAM and CPU training is much slower than GPU training. The context window and adapter rank are reduced to keep the run within the 16 GB RAM budget. No guarantee of completing each stage within the six-hour GitHub job ceiling is made until the real run demonstrates it.

## First: verify real CPU training support

On `development`, change `data/github/run-request.json` to:

```json
{
  "phase": "cpu_smoke"
}
```

Commit it. The workflow downloads the public Qwen3-1.7B-Base checkpoint, attaches LoRA, performs one real forward/backward/optimizer step on a tiny synthetic string and saves a disposable smoke-test adapter. It reports peak resident memory. This is a hardware compatibility test only; it is not one of the five training stages.

After the test, reset the request to:

```json
{
  "phase": "setup",
  "note": "GitHub-only CPU training; setup validation only."
}
```

## Generate the teacher dataset

On `development`, change the request to:

```json
{
  "phase": "generate"
}
```

Commit. The same free CPU runner loads the frozen teacher, generates up to 48 candidates with a 256-token output cap, and uploads `klod-teacher-candidates`. This step may be slow on CPU.

Review every candidate answer. Automated checks are not a factuality guarantee. Keep at least 20 distinct IDs that you have manually verified. Do not approve answers just to make the minimum.

## Execute the stages

For each branch, set `data/github/run-request.json` to `phase: train_stage`, add the correct `stage_percent`, the successful teacher-generation run ID, at least 20 manually approved IDs, and the previous stage run ID.

| Branch | Stage | Previous adapter |
|---|---:|---|
| `training/20-percent` | 20% | Qwen3-1.7B-Base |
| `training/40-percent` | 40% | 20% artifact |
| `training/60-percent` | 60% | 40% artifact |
| `training/80-percent` | 80% | 60% artifact |
| `training/100-percent` | 100% | 80% artifact |

Every stage downloads the previous LoRA adapter from GitHub Actions artifacts and continues training it for one additional epoch. The five stages must run in order. Adapter and report artifacts are retained for 14 days, so continue the chain before the previous artifact expires.

## Limitations

- Public-repository Actions minutes are free and unlimited for standard runners; GPU-powered larger runners are not used.
- Standard Linux runners have 4 vCPUs, 16 GB RAM and 14 GB SSD. Each hosted Actions job has a maximum duration of six hours.
- CPU training can take much longer than the former QLoRA GPU version. A stage may hit the six-hour job limit; the workflow must not claim success unless a saved adapter and metrics are validated.
- The free GitHub plan includes 500 MB of artifact storage. Adapter rank 8 and 14-day retention reduce storage pressure, but remove old runs/artifacts if the repository reaches its storage allowance.
- The repository is public. Its code, teacher candidates, logs and downloadable artifacts must be treated as public.
- 100% means five one-epoch adapter-training stages completed. It does not mean 100% accuracy or model superiority.

The `main` branch is not part of the training flow.
