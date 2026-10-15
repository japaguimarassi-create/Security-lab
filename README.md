# Kodex AI Lab 0.5.0 — Terminal and Transformer Training

Kodex is an experimental, mobile-first programming assistant with a locally executed neural language model. Version 0.5.0 adds a project terminal and a from-scratch causal Transformer training lab while retaining the existing local file workspace. This branch does not build an APK.

## Existing application behavior retained

- **Chat-first behavior remains:** greetings, short replies, and normal questions do not turn into build tasks automatically.
- **Local project workspace:** create, edit, rename, delete, import and download text files; preview HTML in a restricted iframe; run basic static checks; export the project as a ZIP.
- **No runtime package downloads:** the local editor and terminal use browser/platform features; this branch's ML workflow does not package an Android app.
- **Explicit Build mode:** prepare an implementation brief and optional model-generated draft; the chat mode stays conversational.
- **Legacy chat runtime:** source still contains the original 264,192-parameter LSTM chat path. That older model is not the model trained by the new ML workflow.
- **No remote AI API:** each APK build trains model weights from random initialization and embeds an int8-quantized model into the app.
- **Conversation history:** threads are stored in local browser/app storage.

## Kodex Project Terminal 0.5.0

Open [terminal.html](terminal.html) from the chat or file workspace. The terminal provides commands for the shared local project files: `pwd`, `ls`, `tree`, `cat`, `head`, `tail`, `grep`, `find`, `touch`, `mkdir`, `write`, `append`, `cp`, `mv`, `rm --yes`, `node --check`, `run js`, `check`, `status`, and `export`.

This is a **project terminal**, not a general Android/Linux shell. It does not run `bash`, `apt`, `npm`, `pip`, or arbitrary operating-system commands. JavaScript can be run in a restricted iframe with a five-second cutoff. The actual training/build executor is a GitHub Actions workflow, whose source and logs are available to inspect.

## AI training lab 0.5.0

The **active workflow** trains the experimental model in `training/kodex_lm.py` from random initialization, using a tokenizer trained from the training split. The architecture includes rotary positional embeddings, grouped-query attention, sparse top-k mixture-of-experts routing (four experts, two selected per token), and auxiliary multi-token prediction heads.

The default `ModelConfig()` tested in CI has **2,378,880 trainable parameters**. That is a parameter count, not a biological neuron count. During a real run, the BPE tokenizer's vocabulary becomes part of the model config, so the exact count may be higher; the trainer prints and records the actual count and config. The simpler comparison baseline in `training/model.py` has **1,678,592 parameters**.

The real training path is `training/train_kodex_model.py`; `training/train_tokenizer.py` trains a byte-level BPE tokenizer on the training split only. The trainer uses cross-entropy, AdamW, warmup plus cosine decay, gradient clipping, train/validation/test splits, a best-validation checkpoint, resumable last-step checkpoint, corpus/tokenizer hashes, perplexity diagnostics, and checkpoint cards. `training/evaluate_kodex_model.py` samples held-out prompts and writes its exact-match and word-overlap diagnostics. Those metrics are not complete quality measures and require human review.

The starter dialogue corpus remains small (about 90 curated examples). It is enough for a mechanical smoke test, not for a capable general chat/coding assistant. Larger training needs many more high-quality, licensed, deduplicated tokens and rigorous held-out evaluations. The project includes `training/prepare_corpus.py` to filter a source manifest using an explicit license allowlist, source commit, training permission flag, path checks, duplicate removal, and heuristic secret scanning. The scanner is not a guarantee that data is safe or license-compliant; contributors still need to review every source.

### Million-scale candidate queue

`training/experiment_swarm.py` can represent up to **1,000,000,000 candidate trial IDs** without materializing a billion-row file. The IDs are split deterministically across shards and hyperparameters are derived from a stable seed formula. This makes a queue of candidates possible; it does not claim that every candidate was trained.

The workflow supports:
- `plan`: report a candidate batch without executing models.
- `smoke`: run a two-step end-to-end test.
- `train`: train one model and evaluate held-out generations.
- `sweep`: execute a bounded batch of independent model trials in parallel shards.

A GitHub Actions matrix is limited to 256 jobs per workflow run. Actual concurrent runners may be fewer due to availability and account limits. With 256 shards and 100 sequential trials per shard, the theoretical upper batch size is 25,600 trial attempts; one million attempted trials would therefore need at least 40 batches, assuming all runners start and all trials complete successfully. Keep `shards` and `trials_per_shard` the same while increasing `batch_index` from 0 to continue the queue without repeating completed candidate IDs. For example, at 256 shards × 100 trials/shard, run batch indices 0 through 39. Each Actions job has a six-hour limit, and each individual trial has a timeout, so reduce work per batch or steps if a job cannot finish within its time budget.

This is not the same as one model receiving a million simultaneous gradient updates and cannot honestly be equated to “years of training” without actual measurements of training tokens, steps, throughput, compute, and elapsed time. A large list of planned runs is only a plan until logs and metrics prove execution.

### Run the remote training workflow

Open [Kodex ML Lab workflow](https://github.com/japaguimarassi-create/Security-lab/actions/workflows/kodex-ml-lab.yml) on branch `kodex-ai-lab`. Pushes to this branch run syntax checks, regression tests, a parameter-count assertion, and the default smoke training test. Once the workflow is available in the repository's default branch, the **Actions → Kodex ML Lab → Run workflow** form exposes the `plan`, `smoke`, `train`, and `sweep` modes and their batch controls.

Artifacts include metrics, checkpoints, tokenizer, model card, sample generations, and batch summaries; they are retained for 14 days. **The workflow does not build an APK.**

## Local file workspace 0.4.0

Open `workspace.html` from the chat screen using **Arquivos**. The workspace starts with an editable HTML/CSS/JavaScript example. It supports creating files and relative folders, editing content, renaming and deleting files, importing multiple text files, downloading one file, exporting all project text files as a ZIP, basic JSON/classic-JavaScript/HTML checks, and sandboxed HTML preview.

The workspace and project terminal are **local to Kodex's WebView/browser storage**. They do not automatically read other Android files or write to GitHub. The project terminal is not a general-purpose OS shell; the Python training process and any build run inside GitHub Actions. Import files explicitly with the picker and export a ZIP to move your work elsewhere. Binary files and ZIP import are not supported by this version.

Safety limits: up to 200 project files, 512 KiB per file, and 1,500 KiB of total text for local project storage. The preview runs in a sandboxed iframe with a restrictive Content Security Policy; it is a convenience preview, not a security-grade sandbox. Static checks are not a replacement for compiler or test execution.

## Agent instruction conventions

The root `AGENTS.md` records the product's persistent operating rules for compatible coding agents, and `.github/copilot-instructions.md` carries repository-specific guidance for GitHub Copilot. Their purpose is to preserve the project direction: conversation by default, mobile/offline-first, no unapproved AI API, truthful execution reports, incremental changes, and validation.

## Important limits

The legacy 264,192-parameter chat model remains very small and is not the active training target in this branch. The new 2.38M+ parameter sparse Transformer is still an experimental small model—not GPT-6 Astra, GPT-6.1 Sol, Codex, or Copilot.

The starter data at `training/data/mobile_dialogue.jsonl` contains around 90 curated, mostly Portuguese conversation/programming examples. A successful two-step smoke run verifies that tokenizer training, model forward/backward, checkpointing, and evaluation connect; it does not prove broad language understanding or reliable coding ability. The model can repeat text, produce invalid output, and fail coding tasks.

Chat Build mode still drafts a brief and checklist; it does not edit the repository or run commands. The new separate workspace edits only the files created or imported into its local storage. Repository context displayed in chat is descriptive; source files are not automatically read.

## Open the project

- [Kodex AI Lab branch](https://github.com/japaguimarassi-create/Security-lab/tree/kodex-ai-lab)
- [Kodex ML Lab workflow (no APK build)](https://github.com/japaguimarassi-create/Security-lab/actions/workflows/kodex-ml-lab.yml)
- [Terminal](terminal.html)
- [Active sparse Transformer architecture](training/kodex_lm.py)
- [Active training script](training/train_kodex_model.py)
- [Trainable byte-level BPE tokenizer](training/train_tokenizer.py)
- [Held-out generation evaluator](training/evaluate_kodex_model.py)
- [Simple Transformer baseline](training/model.py)
- [Dialogue normalizer](training/normalize_dialogue_corpus.py)
- [Licensed code-corpus preparer](training/prepare_corpus.py)
- [Million-scale trial scheduler](training/experiment_swarm.py)
- [Research and limits](docs/ml-training-system.md)
- [Local MLM profile](src/ai/neuron-profile.json)
- [Training corpus](training/data/mobile_dialogue.jsonl)
- [Model training and quantization](training/build_mobile_mlm.py)
- [On-device inference runtime](src/ai/mobile-mlm.js)

## Legacy chat model profile (not the active training target)

The older in-app model profile (kept in the repository from the previous branch) was trained for autoregressive next-token prediction:

- Byte-level BPE tokenizer: 256 byte tokens plus 256 learned merges = vocabulary size 512.
- Token embedding: 512 × 128 = 65,536 parameters.
- Input LayerNorm: 128 weights + 128 biases = 256 parameters.
- One LSTM layer: 132,096 parameters.
- Output LayerNorm: 256 parameters.
- Language-model head: 128 × 512 weights + 512 biases = 66,048 parameters.

**Total: 65,536 + 256 + 132,096 + 256 + 66,048 = 264,192 parameters.**

Weights are quantized per tensor to signed 8-bit values for app delivery. The app reconstructs the small network and computes predictions locally in JavaScript. The weights are generated by the APK workflow and are not kept as a source-controlled model checkpoint.

## Legacy model build (not used by this branch's workflow)

Use Python 3.12 and PyTorch:

```sh
python -m pip install torch
python -m unittest training.tests.test_mobile_mlm -v
python training/build_mobile_mlm.py --data training/data/mobile_dialogue.jsonl --output kodex-model.js --steps 500 --batch-size 8 --seed 42
```

These commands reproduce the older local inference model, not the new AI Lab trainer. The current `kodex-ml-lab.yml` workflow uses `training/train_kodex_model.py` and intentionally does not invoke Gradle or package an APK.

## APK

Push changes to `kodex-programming-ai` that touch the Android app, model runtime, or model training files to trigger the GitHub Actions build. This `kodex-ai-lab` branch does not compile an APK. The ML workflow publishes training metrics and checkpoints as artifacts; these are not Android installation packages.

## Privacy and safety

The local model does not require an inference API key and does not send chat prompts to a remote model service. The chat history is kept in local app/browser storage. The Build mode only prepares a proposed response; no code is executed and no project files are changed automatically.
