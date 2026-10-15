# Kodex AI Lab: training architecture, evidence, and limits

This document describes the **actual code in this branch**, separates queued experiments from executed training, and records the engineering references used to design it. The lab does not build an APK.

## Executive overview

The lab has two model architectures, with the advanced one wired to the current training workflow:

1. A causal decoder-only Transformer baseline in `training/model.py`, with exactly 1,678,592 trainable parameters.
2. The active experimental architecture in `training/kodex_lm.py`, which adds rotary positional embeddings, grouped-query attention, SwiGLU expert feed-forward layers, sparse top-k mixture-of-experts routing, router load-balancing loss, and multi-token prediction heads. The default `ModelConfig()` has **2,378,880 trainable parameters** as verified in GitHub Actions. The training run adjusts vocabulary size to its BPE tokenizer, so the exact count is recorded in each run and may be larger.
3. The active trainer in `training/train_kodex_model.py`, which fits the byte-level BPE tokenizer only on the training split, optimizes the causal language objective, selects the best checkpoint by held-out validation loss, evaluates the test split after selection, and stores tokenizer/corpus hashes, optimizer state, and metrics.
4. A candidate experiment scheduler in `training/experiment_swarm.py`, plus tokenizer training utilities in `training/train_tokenizer.py` and corpus safeguards in `training/prepare_corpus.py`.

The current training workflow is CPU-first, with separate jobs for model validation and actual training. Before claiming a model is useful, use held-out examples, generated answer inspection, and records of the real run. A parameter count is not an intelligence measurement.

## What “a language model trained from scratch” involves

### Data and permissions
A model learns from the tokens and patterns in its corpus; adding layers does not create data or knowledge. The existing dialogue corpus in `training/data/mobile_dialogue.jsonl` is a small, curated starter corpus, suitable for proving the training path and regression tests—not for establishing general conversational or programming ability.

For larger code corpora, use the licensed-source manifest format handled by `training/prepare_corpus.py`. Each candidate source must identify a relative file path, source URL, commit reference, allowlisted license, and explicit `training_permitted: true`. The preparer rejects traversal and symlinks, blocks likely secrets and unsupported file types, and deduplicates byte-identical normalized files. The secret scan is heuristic: it is not a guarantee that secrets or personal information are absent. A source being publicly accessible is not by itself proof that its license or terms permit model training.

### Tokenization
`training/train_tokenizer.py` can train a byte-level BPE tokenizer from UTF-8 text. A special end-of-sequence token allows the data pipeline to separate training examples. The tokenizer must be trained only on the training split when evaluating held-out examples; fitting it on test text can leak information about the evaluation set.

### Model and objective
Autoregressive language modeling uses causal attention so the prediction at a position cannot use future tokens. The ordinary next-token objective is cross-entropy between logits and the next-token targets. The experimental architecture also has a multi-token prediction objective and a mixture-of-experts routing loss. The causal attention regression tests alter future input tokens and verify that earlier logits do not change.

### Optimization, evaluation, and checkpointing
A practical run records the exact config, random seed, source corpus hash, steps, loss, validation/test metrics, timing, and generated outputs. Training code uses AdamW, warmup plus cosine learning-rate decay, gradient clipping, separated train/validation/test records, and model/optimizer checkpoint saving. Resume checkpoints should include optimizer state as well as model weights, so optimization state does not silently reset.

Validation and test splits are kept out of gradient updates. Do not repeatedly tune against the test set. A smoke test proves that a code path runs; it does not prove that answers are accurate or useful. Loss/perplexity provide diagnostics, not a complete quality score, so manually review generated samples for usefulness, factual correctness, instruction adherence, repetition, and coding validity.

## Experiment scheduling: millions of candidates vs. millions of running jobs

`training/experiment_swarm.py` can deterministically represent up to 1,000,000,000 candidate trial IDs without materializing a billion-entry queue. Each shard derives its trial IDs from a stable formula, and each candidate gets a deterministic seed and hyperparameter configuration. With `--mode plan`, the system only creates a plan. With `--mode execute`, it trains only the bounded number of trials specified by `--max-executions`.

The queue supports `--batch-index` so later runs continue to new candidate IDs rather than repeating the first batch. Keep `--shard-count` and `--max-executions` constant across batches: batch \(b\) starts at candidate ID \(shard\_id + b \times max\_executions \times shard\_count\). This partitions each shard's ordered candidate IDs into non-overlapping batches. Regression tests verify the batches cover every test candidate exactly once with no overlap.

The GitHub Actions workflow limits each matrix to 256 jobs. Actual simultaneous execution can be lower because of runner availability, concurrency quotas, queueing, and account/org settings. With 256 shards and 100 sequential trials per shard, the theoretical batch maximum is 25,600 candidate attempts; at that cap, one million attempts take at least 40 batches if all jobs complete. Each job has a six-hour cap, and each trial has its own timeout, so adjust training steps and batch size to the actual runner throughput.

A million planned candidate configurations are not a million trained models. A sweep is not a single model receiving a million times more learning, and it cannot be described as “years of learning” without measured training tokens, steps, FLOPs or hardware throughput, and runtime.

The public repository's standard `ubuntu-latest` hosted runner is documented as a fresh Linux VM with 4 CPUs and 16 GB RAM; public-repository standard runners are free under GitHub's documented policy, but capacity and matrix limits still apply. These CPU runners are practical for tests and small experiments. Serious scale-up needs a larger dataset and compute, measurement of tokens/second and GPU utilization, a suitable hardware pool, and a deliberate distributed-training setup.

For one model trained across multiple devices, PyTorch DistributedDataParallel synchronizes gradients across replicas; the application remains responsible for distributing data. That is a different design from this lab's hyperparameter sweep, where separate runners train different candidate models. A larger GPU cluster or managed compute system would be needed to scale a single model's optimization substantially.

## Terminal and execution boundary

`terminal.html` is a project terminal for the files stored in the local Kodex workspace. It is not a system shell and does not execute arbitrary `bash`, `apt`, `pip`, or `npm` commands. It can inspect and manipulate workspace files, run static checks, and execute JavaScript in a constrained iframe. Actual Python model training runs on GitHub Actions. The terminal does not claim that remote training started unless an actual workflow is run and a real run ID/log is available.

No APK build is part of the `kodex-ai-lab` workflow.

## How this compares with Codex and Copilot

The GPT-6 Astra and GPT-6.1 Sol model documentation describes those hosted models as capable of complex coding/agentic work. This branch does not use those models or claim to replicate them. Kodex is a separate experimental from-scratch model plus a tool-and-workflow layer.

The tool workflow follows compatible engineering practices: inspect actual files, keep persistent instructions, plan focused changes, use explicit tools, run tests, inspect diffs, and report evidence. These practices are inspired by the public Codex `AGENTS.md` guidance and GitHub Copilot's repository/custom-instruction and coding-agent documentation; the existing `AGENTS.md` and `.github/copilot-instructions.md` were intentionally preserved unchanged.

## Research references

- [OpenAI GPT-6 Astra model documentation](https://developers.openai.com/api/docs/models/gpt-6-astra)
- [OpenAI GPT-6.1 Sol model documentation](https://developers.openai.com/api/docs/models/gpt-6.1-sol)
- [OpenAI model selection and GPT-6 guidance](https://developers.openai.com/api/docs/models)
- [OpenAI Codex: AGENTS.md guidance](https://github.com/openai/codex/blob/main/docs/agents_md.md)
- [GitHub Copilot coding-agent best practices](https://docs.github.com/en/copilot/using-github-copilot/using-copilot-coding-agent-to-work-on-tasks/best-practices-for-using-copilot-to-work-on-tasks)
- [GitHub Copilot repository custom instructions](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/add-custom-instructions/add-repository-instructions)
- [GitHub Actions workflow syntax: matrix job limit](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstrategymatrix)
- [GitHub-hosted runner specifications](https://docs.github.com/en/enterprise-cloud@latest/actions/reference/runners/github-hosted-runners)
- [PyTorch DistributedDataParallel](https://docs.pytorch.org/docs/stable/generated/torch.nn.parallel.DistributedDataParallel.html)
- [Hugging Face Transformers: causal language modeling](https://huggingface.co/docs/transformers/en/tasks/language_modeling)
- [Hugging Face Tokenizers: quick tour](https://huggingface.co/docs/tokenizers/en/quicktour)
- [Chinchilla compute-optimal language model training research](https://arxiv.org/abs/2203.15556)

The scaling-law research is relevant because parameter count and training-token count need to be considered together. It does not provide a formula that turns a queue of trial IDs into years of meaningful learning.
