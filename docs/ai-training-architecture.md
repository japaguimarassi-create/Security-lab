# Kodex AI training and runtime architecture

## What is actually implemented

- A decoder-only causal Transformer implemented directly with PyTorch modules.
- A deterministic byte-level BPE tokenizer trained from the training split.
- JSONL/text corpus loading, UTF-8 validation, normalization, deduplication, deterministic train/validation split, and size limits.
- Next-token training with AdamW, gradient clipping, repeatable seeds, explicit train/validation loss, token-count estimates and checkpointing.
- Resumable latest checkpoints and best-checkpoint selection by validation loss.
- Optional PyTorch DistributedDataParallel training through torchrun; all ranks execute the same model shape and synchronize gradients.
- A SQLite experiment queue for millions of independent trial definitions with bounded active workers, atomic claims, failed-run status, logs and validation-loss ranking.
- A local model chat CLI and a scoped local developer terminal.
- A browser project terminal that manipulates the existing local file workspace and can prepare a training plan without pretending browser JavaScript can execute Python or access an OS shell.

The standard model configuration has 2,002,048 trainable parameters when the tokenizer's vocabulary contains 1,024 tokens. If BPE training yields fewer merges, the realized model count is lower; its current 4-layer/192-hidden architecture still exceeds the requested 780,000-parameter threshold. Parameter count is not the same thing as a count of biological neurons.

## Training flow

1. Inspect and validate corpus files with `python -m kodex_ai.prepare_data --input PATH`.
2. Split examples into deterministic training and validation subsets.
3. Fit byte-level BPE merges on the training subset only.
4. Initialize Transformer weights from random initialization (unless resuming a checkpoint).
5. Train by predicting the next token in each sampled sequence.
6. Periodically calculate train and validation loss and estimate how many tokens were processed.
7. Save `checkpoint_best.pt`, `checkpoint_last.pt`, tokenizer/config metadata, metrics and a training summary.
8. Load the resulting checkpoint into the local chat CLI for generation.

Training loss decreasing does not prove language understanding or answer correctness. The current corpus is deliberately small and mostly Portuguese, so overfitting remains a known risk. Use a larger, licensed, provenance-tracked corpus and a held-out evaluation set before drawing conclusions about quality.

## Parallelism: queued work versus active work

The sweep orchestrator accepts up to 10,000,000 job rows in its SQLite queue. Each row defines an independent experiment, not a new model that begins running instantly. Worker processes claim rows atomically and run separate training commands up to the requested worker count. A local SQLite queue coordinates processes on a shared local filesystem; it is not a cross-cloud message broker. If a multi-node cluster is required, deploy a shared scheduler/database or queue service and secure it independently.

PyTorch DDP is a different form of parallelism: several processes train replicas of the *same* model on different batches while synchronizing gradients. It can use multiple devices/hosts, but needs valid process-group rendezvous, network communication, compatible hardware, and enough memory. DDP does not turn one process into millions and does not create compute resources.

The workflow doesn't convert wall-clock training into fictional "years equivalent". It records actual optimizer steps, tokens processed estimates, time and validation results. More steps on a tiny dataset can only repeat that data and often make overfitting worse; wall-clock duration alone is not a valid substitute for dataset coverage, compute, architecture, or evaluation.

## Why GitHub Actions is not a million-worker cluster

GitHub Actions concurrency is bounded by plan and runner type, and the quotas change. The current documentation lists 20/40/60/500 concurrent standard jobs for Free/Pro/Team/Enterprise; larger runners have different limits (documented up to 1,000 total jobs, with GPU limits on eligible plans). Standard hosted runners do not provide GPU jobs. The workflow in this branch runs tests and a two-step CPU smoke-training run on relevant pushes; a longer checkpoint training run is opt-in through workflow_dispatch and uploads model artifacts rather than an APK. These repository-level queue settings do not bypass GitHub account concurrency limits.

Sources:
- [GPT-6 Astra](https://developers.openai.com/api/docs/models/gpt-6-astra)
- [GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol)
- [Codex and AGENTS.md instructions](https://developers.openai.com/cookbook/examples/gpt-5/codex_prompting_guide)
- [OpenAI article on GPT-6 Astra and agent instructions](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra)
- [GitHub Copilot coding-agent best practices](https://docs.github.com/en/copilot/using-github-copilot/using-copilot-coding-agent-to-work-on-tasks/best-practices-for-using-copilot-to-work-on-tasks)
- [GitHub Actions concurrency limits](https://docs.github.com/en/actions/reference/limits)
- [Hugging Face causal language modelling](https://huggingface.co/docs/transformers/tasks/language_modeling)
- [PyTorch DistributedDataParallel](https://docs.pytorch.org/docs/stable/generated/torch.nn.parallel.DistributedDataParallel.html)
