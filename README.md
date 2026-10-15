# Kodex 0.5.0 — Local AI Training Lab and Project Terminal

Kodex is an experimental, mobile-first programming assistant with a locally executed neural language model. Version 0.5.0 adds a project terminal, a from-scratch causal Transformer, reproducible training and validation, resumable checkpoints, an interactive local chat CLI, and a persistent SQLite experiment queue. This branch does not build an APK.

## What changed in 0.5.0

- **Chat-first behavior remains:** greetings, short replies, and normal questions do not turn into build tasks automatically.
- **Project terminal:** browser terminal commands operate only on files stored in Kodex's local workspace; the Python CLI can run a limited set of real local commands.
- **New neural model:** decoder-only causal Transformer with tied token/output embeddings; configured for **2,002,048 trainable parameters** when its BPE vocabulary reaches 1,024 tokens.
- **Real training pipeline:** PyTorch, explicit train/validation split, next-token prediction, gradient clipping, evaluation metrics, checkpoint-best/checkpoint-last, and resume support.
- **Experiment queue:** SQLite-backed queue accepts up to 10,000,000 planned independent experiments and runs only a bounded number of workers at once.
- **Distributed training:** the trainer can run under torchrun/PyTorch DistributedDataParallel on properly configured multi-process hardware.
- **Local neural chat:** `python -m kodex_ai.chat --checkpoint ...` loads a trained checkpoint and answers without a remote inference API.
- **No APK workflow:** the added workflow runs tests and, when explicitly requested, trains and uploads a model checkpoint artifact; it does not package Android applications.
- **Local project workspace:** create, edit, rename, delete, import and download text files; preview HTML in a restricted iframe; run basic static checks; export the project as a ZIP.
- **No runtime package downloads:** workspace functionality uses browser/platform features; the AI-lab branch adds no Android packaging workflow.
- **Explicit Build mode:** prepare an implementation brief and optional model-generated draft; the chat mode stays conversational.
- **Local neural model:** one-layer LSTM, 512-token byte-level BPE vocabulary, 128-dimensional embedding and hidden state, and exactly **264,192 trainable parameters** before quantization.
- **No remote AI API:** each APK build trains model weights from random initialization and embeds an int8-quantized model into the app.
- **Conversation history:** threads are stored in local browser/app storage.

## AI training and experiment queue 0.5.0

Install Python 3.12 and PyTorch in a desktop/Linux/CI environment:

```sh
python -m pip install -r requirements-ai.txt
python -m kodex_ai.prepare_data --input training/data/mobile_dialogue.jsonl
python -m kodex_ai.train --dry-run --data training/data/mobile_dialogue.jsonl
python -m kodex_ai.train --data training/data/mobile_dialogue.jsonl --steps 1000 --output-dir artifacts/kodex-ai-run
python -m kodex_ai.chat --checkpoint artifacts/kodex-ai-run/checkpoint_best.pt
```

The model is a small causal Transformer trained to predict the next token. Its default configuration has 4 layers, hidden size 192, 6 attention heads, feed-forward size 768, block size 128, learned byte-level BPE vocabulary of up to 1,024 tokens, and tied token/output embeddings. The count is 2,002,048 parameters at vocabulary size 1,024; it is a parameter count, not a count of literal/biological neurons. If the corpus does not produce all 768 BPE merges, the actual count is lower but remains above 1.8 million for the current architecture.

Train/validation splits are deterministic for the chosen seed. Evaluation logs train and validation loss, estimates tokens processed, and saves the best validation checkpoint plus the latest resumable checkpoint. After interruption, resume with `--resume artifacts/kodex-ai-run/checkpoint_last.pt` and keep the same model shape and block size.

### Queue millions of experiments without pretending they run simultaneously

```sh
python -m kodex_ai.sweep plan --trials 1000000 --steps 100 --db artifacts/kodex-sweep/jobs.sqlite3
python -m kodex_ai.sweep status --db artifacts/kodex-sweep/jobs.sqlite3
python -m kodex_ai.sweep run --workers 2 --max-completions 2 --db artifacts/kodex-sweep/jobs.sqlite3
python -m kodex_ai.sweep retry-failed --db artifacts/kodex-sweep/jobs.sqlite3
```

The persistent SQLite database schedules independent runs with varying seeds, learning rates, dropout, weight decay, and batch sizes. It supports millions of queued trials, atomic trial claiming and bounded local concurrency. One million jobs in a queue is not one million active training processes. Actual simultaneous training is bounded by the available CPUs/GPUs, RAM, disk, and worker count. Use a properly provisioned multi-node PyTorch DDP environment for distributed training; it synchronizes gradients across processes but does not create additional compute by itself.

The CLI terminal is real local command execution for the approved project commands and scoped file operations:

```sh
python -m kodex_ai.terminal
```

The default terminal is restricted. The optional `--unsafe-shell` mode explicitly enables arbitrary shell commands and can access the user's system; enable it only when necessary. The browser terminal does not run OS processes; it edits only the local project workspace and prints the corresponding Python commands for real training.

## Local file workspace 0.4.0

Open `workspace.html` from the chat screen using **Arquivos**, or `terminal.html` using **Terminal**. The workspace starts with an editable HTML/CSS/JavaScript example. It supports creating files and relative folders, editing content, renaming and deleting files, importing multiple text files, downloading one file, exporting all project text files as a ZIP, basic JSON/classic-JavaScript/HTML checks, and sandboxed HTML preview.

The workspace is **local to Kodex's WebView/browser storage**. It does not automatically read other Android files, write to the GitHub repository, authenticate to GitHub, run shell commands, install dependencies, or compile arbitrary projects. Import files explicitly with the picker and export a ZIP to move your work elsewhere. Binary files and ZIP import are not supported by this version.

Safety limits: up to 200 project files, 512 KiB per file, and 1,500 KiB of total text for local project storage. The preview runs in a sandboxed iframe with a restrictive Content Security Policy; it is a convenience preview, not a security-grade sandbox. Static checks are not a replacement for compiler or test execution.

## Agent instruction conventions

The root `AGENTS.md` records the product's persistent operating rules for compatible coding agents, and `.github/copilot-instructions.md` carries repository-specific guidance for GitHub Copilot. Their purpose is to preserve the project direction: conversation by default, mobile/offline-first, no unapproved AI API, truthful execution reports, incremental changes, and validation.

## Important limits

The 264,192 figure is the actual trainable parameter count, not a count of biological neurons. In standard language-model terms, this is a **tiny/compact model**, not a medium-scale or frontier model.

The training data at `training/data/mobile_dialogue.jsonl` contains 90 curated, mostly Portuguese conversation and programming examples. The default APK workflow runs 500 training steps from random initialization. This proves that model training, quantization, bundling, and on-device inference are connected; it does not prove broad language understanding or reliable coding ability. The model can make mistakes, repeat phrases, or return poor answers. The chat filters some obviously invalid outputs and uses explicit fallback responses for common greetings and very short messages. The separate workspace is a file editor, not evidence of stronger model intelligence.

Chat Build mode still drafts a brief and checklist; it does not edit the repository or run commands. The new separate workspace edits only the files created or imported into its local storage. Repository context displayed in chat is descriptive; source files are not automatically read.

## Open the project

- [Kodex AI Lab v0.5.0 branch](https://github.com/japaguimarassi-create/Security-lab/tree/kodex-ai-lab-v0.5.0)
- [AI Lab validation and optional checkpoint-training workflow](https://github.com/japaguimarassi-create/Security-lab/actions/workflows/ai-lab.yml)
- [Terminal CLI](kodex_ai/terminal.py)
- [Transformer model](kodex_ai/model.py)
- [Training pipeline](kodex_ai/train.py)
- [Experiment queue](kodex_ai/sweep.py)
- [Local chat CLI](kodex_ai/chat.py)
- [Agent workflow research notes](docs/ai-training-architecture.md)

The old APK workflow and the 264,192-parameter browser/mobile LSTM remain in the repository for the prior application branch. This new branch's training CLI is separate from the in-app LSTM and does not build, update, sign, or release an APK. Its optional workflow produces PyTorch checkpoint files only.

## Model architecture and parameter count

The compact network is trained for autoregressive next-token prediction:

- Byte-level BPE tokenizer: 256 byte tokens plus 256 learned merges = vocabulary size 512.
- Token embedding: 512 × 128 = 65,536 parameters.
- Input LayerNorm: 128 weights + 128 biases = 256 parameters.
- One LSTM layer: 132,096 parameters.
- Output LayerNorm: 256 parameters.
- Language-model head: 128 × 512 weights + 512 biases = 66,048 parameters.

**Total: 65,536 + 256 + 132,096 + 256 + 66,048 = 264,192 parameters.**

Weights are quantized per tensor to signed 8-bit values for app delivery. The app reconstructs the small network and computes predictions locally in JavaScript. The weights are generated by the APK workflow and are not kept as a source-controlled model checkpoint.

## Reproduce the mobile model build

Use Python 3.12 and PyTorch:

```sh
python -m pip install torch
python -m unittest training.tests.test_mobile_mlm -v
python training/build_mobile_mlm.py --data training/data/mobile_dialogue.jsonl --output kodex-model.js --steps 500 --batch-size 8 --seed 42
```

The generated `kodex-model.js` contains tokenizer merges, quantized tensors, the exact parameter count, and basic training metrics. The GitHub Actions APK workflow performs the same steps before Gradle packages the app assets.

## APK

This branch uses a separate AI-lab workflow for tests and optional model training. It does not invoke Android packaging. The existing 0.4.0 branch's APK notes are historical. This 0.5.0 AI-lab branch does not build an APK. Its optional model-training workflow artifact is a PyTorch checkpoint, not an Android application. It is a debug APK signed with the debug key; it is not a Google Play-certified release.

## Privacy and safety

The local model does not require an inference API key and does not send chat prompts to a remote model service. The chat history is kept in local app/browser storage. The Build mode only prepares a proposed response; no code is executed and no project files are changed automatically.
