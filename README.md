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
- **No APK workflow:** the AI lab workflow validates the code and briefly trains the larger model configuration; the optional full run uploads a PyTorch checkpoint only.
- **Local project workspace:** create, edit, rename, delete, import and download text files; preview HTML in a restricted iframe; run basic static checks; export the project as a ZIP.
- **No runtime package downloads:** workspace functionality uses browser/platform features; the AI-lab branch adds no Android packaging workflow.
- **Explicit Build mode:** prepare an implementation brief and optional model-generated draft; the chat mode stays conversational.
- **Historical mobile model retained:** the inherited browser/Android LSTM still has 264,192 trainable parameters; it is not the new Python Transformer and its APK build is not run by this branch.
- **No remote inference API:** the new Python training and chat CLI run locally or on a chosen runner; there is no built-in hosted-model dependency.
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

The Python Transformer is configured for **2,002,048 trainable parameters** at vocabulary size 1,024. "Parameters" are learned numerical weights, not literal or biological neurons. It is a small experimental language model, not an equivalent of Codex or Copilot.

The corpus currently has 90 curated, mostly Portuguese examples (81 training and 9 validation examples in the CI run). CI actually trained this Transformer for **two optimizer steps** to verify forward/backward passes, loss calculation, and checkpoint creation. That smoke test proves the training implementation works; it does not make the checkpoint a useful or capable assistant. The longer 1,000–5,000-step training workflow is optional and has not been run by default. Even longer training on only 90 examples can overfit badly; a larger, licensed, deduplicated corpus and a held-out evaluation suite are necessary for meaningful quality.

Millions of experiments can be queued in SQLite, but a queue entry is not a running training process. Active concurrency is limited by worker count, CPU/GPU, RAM, disk, and the runner's quotas. A DDP setup synchronizes gradients across a finite number of processes; it cannot turn one machine into millions of machines or establish "years of equivalent learning."

The browser terminal operates only on Kodex's local project files and **does not execute the phone's OS shell or PyTorch**. The Python CLI is a real terminal but runs only on an environment where Python and the dependencies are installed. Build-mode chat still produces a proposal; it does not autonomously edit the GitHub repository. This branch has no APK build or release job.

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

## CI, checkpoints, and release policy

The [AI Lab workflow](https://github.com/japaguimarassi-create/Security-lab/actions/workflows/ai-lab.yml) runs syntax checks, regression tests, and a real two-step smoke training run using the 2,002,048-parameter configuration. It does not ship that smoke checkpoint as a model release. For a longer training run, open **Actions → Kodex AI Lab validation and training → Run workflow**, choose the `kodex-ai-lab-v0.5.0` branch, enable `train_checkpoint`, and choose 1–5,000 optimizer steps. The output is a PyTorch checkpoint/config/metrics artifact, not an APK. No Android build, signing, or APK upload is performed by this branch.

The optional full training job starts from random initialization and is CPU-based on the standard hosted runner. It is intended as a reproducible experiment, not proof of model intelligence or of years of equivalent training.

## Privacy and safety

The local model does not require an inference API key and does not send chat prompts to a remote model service. The chat history is kept in local app/browser storage. The Build mode only prepares a proposed response; no code is executed and no project files are changed automatically.
