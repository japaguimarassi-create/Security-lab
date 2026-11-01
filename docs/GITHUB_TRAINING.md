# KLOD training entirely in GitHub

The repository contains the training code, five stage configurations, request files, tests, workflow and generated artifacts. No Kaggle, Colab, notebook service or external training orchestrator is used.

## Important GPU requirement

The current model plan is unchanged:

- Frozen teacher: `Qwen/Qwen3-1.7B`.
- Student: `Qwen/Qwen3-1.7B-Base`.
- Student training: 4-bit QLoRA, one epoch per stage.
- Stages: 20%, 40%, 60%, 80% and 100%.

Teacher generation and QLoRA training both require a CUDA GPU in the current configuration. The workflow checks for `nvidia-smi` before installing large training dependencies. A CPU-only runner stops with an explicit error; it does not claim to have trained the model and does not silently replace the 1.7B model.

The default GitHub-hosted runner is CPU-only. GitHub-managed GPU runners are an organization/enterprise feature requiring GitHub Team or GitHub Enterprise Cloud. This repository currently belongs to a personal account, so the default runner cannot execute the requested GPU training. Until a compatible GPU runner is available, GitHub can validate the requests and run the regular CI tests, but the model-training job remains blocked.

If a compatible runner is later attached to the repository, set the repository Actions variable `KLOD_GPU_RUNNER` to the runner label. Do not set it to a CPU runner.

## Native GitHub GPU runner setup

The current repository is owned by a personal account. To use a GitHub-hosted GPU runner without an external compute service:

1. Create or use a GitHub organization and transfer this repository to it.
2. Put that organization on GitHub Team or GitHub Enterprise Cloud.
3. In the organization, open **Settings → Actions → Runners → New runner → New GitHub-hosted runner**.
4. Select a Linux GPU-powered runner. GitHub's published Linux GPU configuration is 4 vCPU, 28 GB RAM, one NVIDIA Tesla T4 with 16 GB VRAM and 176 GB SSD.
5. Give the runner a name/label and allow this repository to use its runner group.
6. In the repository, open **Settings → Secrets and variables → Actions → Variables** and create `KLOD_GPU_RUNNER` with that exact runner label.

The workflow already reads `vars.KLOD_GPU_RUNNER` and checks `nvidia-smi` before installing training libraries. If the variable is missing or the selected image does not expose an NVIDIA GPU, the training job stops before model training.

### Cost and billing

The current published Linux GPU runner rate is **US$0.052 per minute** (US$3.12 per hour). The GitHub Team list price is **US$4 per user per month**. Larger runners are metered while jobs run; public repositories are not exempt from larger-runner billing. Actual billing and any eligible included compute value must be checked in the organization's Billing settings before starting a run.

The current workflow gives a training job a six-hour timeout. At the published Linux GPU rate, six hours would cost up to **US$18.72 for that one job** if it used the entire timeout. This is a ceiling from the configured timeout, not a prediction of actual training duration or cost. Set an Actions spending limit and have the account's billing owner approve the setup before enabling GPU jobs.

### Artifact visibility

This repository is currently public. Anyone with repository read access can download its GitHub Actions artifacts. Do not upload private datasets, personal information, secrets or model weights that must remain private while the repository is public. Change the repository to private before running a training cycle whose adapter artifacts or teacher candidates are confidential.

## Request lifecycle

The workflow is triggered by a commit changing `data/github/run-request.json` on `development` or one of the five training branches. It can also be started manually from Actions.

### 1. Generate teacher candidates

On `development`, set the request to:

```json
{
  "phase": "generate"
}
```

Commit the file. After the GPU job completes, the Actions run publishes `klod-teacher-candidates`, containing `teacher_candidates.jsonl` and `teacher_run.json`.

Review the candidate answers. Automated screening detects malformed, empty, short, oversized, echoed and repetitive answers; it cannot prove factual correctness. Only choose IDs whose answers you have checked. At least 20 approved IDs are required.

### 2. Train stage 20%

On `training/20-percent`, use this structure and replace the run ID and example IDs with the real values:

```json
{
  "phase": "train_stage",
  "stage_percent": 20,
  "teacher_run_id": 123456789,
  "previous_stage_run_id": null,
  "approved_ids": [
    "pt-001",
    "pt-002"
  ]
}
```

The example list above is abbreviated; the real request must contain at least 20 distinct, valid IDs from the teacher artifact.

Commit the request. The workflow downloads the teacher artifact, applies the explicit approval list, validates the dataset and GPU, trains one epoch from the base model, runs the blind evaluation and uploads the adapter and report artifacts.

### 3. Continue the remaining stages

Use the run ID of the completed previous stage. Keep the same teacher run and approved IDs.

| Branch | Stage | Previous stage run |
|---|---:|---|
| `training/40-percent` | 40% | Completed 20% run ID |
| `training/60-percent` | 60% | Completed 40% run ID |
| `training/80-percent` | 80% | Completed 60% run ID |
| `training/100-percent` | 100% | Completed 80% run ID |

Each next stage downloads the previous adapter from the GitHub Actions artifact. The adapter weights are not committed to Git. The workflow stops if an artifact is missing, expired, corrupt or does not contain the expected LoRA files.

## Artifacts

Each teacher-generation run creates:

- `klod-teacher-candidates`: candidates and generation metadata.

Each completed stage creates:

- `klod-stage-N-adapter`: LoRA adapter ZIP for the next stage.
- `klod-stage-N-report`: training metrics, blind comparisons and stage metadata.

Artifacts are retained for 30 days. Complete the next stage before the preceding adapter artifact expires. The blind teacher/student answer key is intentionally excluded from uploaded reports.

Do not put credentials, access tokens or private personal data into candidate files or artifacts. Store credentials only in GitHub Actions Secrets.

## What 100% means

100% means all five planned one-epoch stages completed. It does not mean 100% accuracy, general intelligence or superiority over the teacher. Evaluate the blind comparisons and expand the reviewed dataset before making quality claims.

The `main` branch is not part of this workflow.
