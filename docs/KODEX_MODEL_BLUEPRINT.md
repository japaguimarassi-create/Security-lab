# Kodex model blueprint: from a working pipeline to a competitive model

This document describes the model and training work, its current limits, and the steps required to improve actual capability. It is not a claim that the current checkpoint is state of the art.

## Current implementation

The trainable model is initialized from random weights. Its architecture currently uses:

- A causal decoder-only Transformer.
- RMSNorm and rotary positional embeddings (RoPE).
- Grouped-query attention (GQA) with configurable query and key/value head counts.
- SwiGLU feed-forward networks.
- A sparse mixture of four experts by default, with top-2 routing per token and an auxiliary load-balancing loss.
- Tied token embeddings and output weights.
- PyTorch scaled dot-product attention where supported.

The training loop includes AdamW with beta values 0.9 and 0.95, separate weight-decay groups, warmup/stable/decay learning-rate scheduling, gradient accumulation, gradient clipping, automatic GPU mixed precision, corpus hashes, resumable checkpoints, and a best-validation checkpoint. A separate evaluation command calculates held-out next-token cross-entropy and perplexity. A separate supervised fine-tuning script masks loss on prompts and optimizes assistant response tokens.

These are credible components of a language-model research pipeline, not sufficient conditions for strong reasoning or code generation. Four experts do not automatically outperform a dense network; routing, training data, compute, and evaluations must validate that choice.

## What the reference literature says

Research reports are recipes and evidence to compare against, not code that can be copied blindly into this small implementation.

- [SmolLM3 technical blog](https://huggingface.co/blog/smollm3) describes GQA, selective changes to positional embeddings, intra-document masking, multi-stage domain mixtures, long-context adaptation, reasoning mid-training, supervised fine-tuning, and preference optimization. Its 3B parameter model was trained on roughly 11T tokens using 384 H100 GPUs for 24 days.
- [SmolLM pretraining code and configurations](https://github.com/huggingface/smollm/tree/main/text/pretraining) provides reproducible examples of data-stage configs, tokenized datasets, checkpointing, and distributed training.
- [OLMo 2](https://allenai.org/olmo2) demonstrates the value of open training data, code, intermediate checkpoints, and evaluation records.
- [DeepSeek-V3 technical report and repository](https://github.com/deepseek-ai/DeepSeek-V3) documents sparse mixture-of-experts, Multi-head Latent Attention, multi-token prediction, and multi-stage post-training at a much larger scale.
- [Instella-MoE technical report](https://arxiv.org/abs/2609.00791) reports a from-scratch open MoE model with Gated Multi-head Latent Attention and feedback-driven curation. These are later research directions, not features implemented in Kodex.
- [Mellum 2 technical report](https://arxiv.org/abs/2605.31268) discusses a code-focused MoE design with GQA, sliding-window attention in most layers, and a multi-token prediction head.

The strongest approaches combine architecture, data quality, enough training tokens, specialized mid-training, high-quality instruction data, outcome feedback, and systematic evaluation. No architecture trick removes the need for those ingredients.

## Capability roadmap

### 1. Build an approved, scalable data pipeline

Every source must have a stable origin, commit or version, license, explicit training permission, and a provenance record. Keep test/benchmark solutions out of training data. Screen for secrets, generated files, vendored dependencies, binaries, exact duplicates, and near-duplicates. Run human review or a source allowlist for ambiguous licensing.

Create a mixture that does not overfit to one domain:
- High-quality code and explanatory documentation across languages, paradigms, repositories, and file types.
- Tests, bug reports, patches, code reviews, and debugging examples.
- General text and factual knowledge, mathematics, science, and structured reasoning.
- Portuguese and English, with other languages added deliberately instead of accidentally.
- Safety, privacy, security, and responsible programming examples.

Balance domains by measured token counts and quality rather than simply counting files. Use repository-level and time-based splits when evaluating code so nearly identical files cannot land in both train and validation data. Track exact and near-duplicate rates, language proportions, license proportions, source quality, and data hashes. The checked-in corpora are smoke fixtures only; they must never be mistaken for a production dataset.

### 2. Pretrain the base model

Choose parameter count and token budget together. Establish small, reproducible runs first, then scale only after measuring validation loss, token throughput, memory, numerical stability, and quality per unit of compute. Save optimizer state and configuration for resumption. Keep a separate final holdout that is not used for checkpoint selection.

The present implementation is single-process training with the corpus loaded into memory. Before large-scale pretraining, implement or adopt tested streaming/tokenized shards, packed sequences with document-boundary masking, efficient dataloading, distributed data parallelism, checkpoint retention, run tracking, and robust recovery from hardware interruptions. Avoid writing every intermediate checkpoint into the Git repository.

Potential follow-up experiments include a validated multi-token-prediction objective, sliding-window or hybrid attention, and more efficient expert routing. Each experiment must have an ablation: same data, token budget, optimizer, random seeds where practical, and held-out metrics. Retain GQA plus sparse experts only if those measurements support the trade-off.

### 3. Extend context deliberately

Do not advertise a large context window simply because RoPE can calculate positions beyond training length. Train and evaluate progressively at practical sequence lengths, then use a documented extension strategy. Test retrieval from early and late context positions, long files, multi-file repositories, and instruction retention. Watch for degradation in short tasks after long-context adaptation.

### 4. Train instruction following

Use training/finetune_sft.py after a base checkpoint has learned useful language and code patterns. Each JSONL record should contain a messages array with system, user, assistant, and optionally tool roles. Keep prompts as context and calculate the SFT token loss on assistant turns. Keep validation prompts and responses separate from training data.

A serious SFT collection should include explain, implement, test, debug, refactor, review, documentation, tool-call formatting, uncertainty calibration, multilingual programming, and safe refusal examples. Check data quality and test for memorization. SFT cannot create broad abilities that were never learned in pretraining.

### 5. Align with verifiable outcomes

After a useful base and SFT model exist, compare preference optimization approaches such as DPO/APO and code-outcome signals. Generate candidate patches, then score them using isolated tests, syntax/type checks, regression tests, and human review. Keep evaluation executors separated from model training and do not allow training data to alter the benchmark harness.

Only run generated programs in a separately enforced environment with strict resource and network limits. The current request intentionally excludes any sandbox changes; the sandbox is not part of this update.

### 6. Evaluate capability, not just loss

A serious evaluation suite should include:
- Held-out cross-entropy and perplexity, reported with the exact corpus hash.
- Code completion and generation with hidden tests and no benchmark contamination.
- Syntax, type-check, unit-test, and regression-test pass rates.
- Repository-level edits with patch correctness and regression measures.
- Debugging, code explanation, review accuracy, and instruction adherence.
- General reasoning, mathematics, factuality, Portuguese quality, refusal behavior, and prompt-injection resilience.
- Model size, active parameters, context length, training-token count, throughput, hardware, memory, power/cost estimates, and exact evaluation protocol.

Compare a fixed benchmark set against random, heuristic, and existing open-weight baselines under equivalent settings. Do not select a model on the same examples used to tune it. Record failures rather than silently dropping them. A lower language-model loss alone does not prove better code, reasoning, or factuality.

### 7. Multimodal and general-purpose capabilities

The current model is text-only. To cover image, audio, or video understanding, Kodex would need appropriate encoders/tokenizers, multimodal training data with rights to use it, alignment objectives, and separate evaluation sets. More parameters in a text-only Transformer do not create vision or audio skills. Add modalities only after a reliable text/code baseline and a clear compute budget exist.

## Reproducible smoke checks

The GitHub Actions workflow exercises architecture tests, tiny CPU pretraining, checkpoint resume, local generation, separate holdout evaluation, and a tiny supervised fine-tuning run. Passing those tests only verifies the software path with small human-authored examples. It does not measure frontier capabilities.

For a real run, preserve the training manifest/report, tokenizer file, base and SFT checkpoints, optimizer state, source commit, data hashes, benchmark version, metrics, and hardware/configuration records. Never publish a claim of state-of-the-art capability without repeatable, held-out evidence.
