# Kodex 0.5.0 — Project Terminal and AI Training Lab

Kodex is an experimental, mobile-first programming workspace. Version 0.5.0 adds a project-file terminal, a separate PyTorch Transformer training pipeline, reproducible checkpoints and a bounded concurrent experiment scheduler. This branch is for source, tests and training workflows; no APK is built by its AI Training Lab workflow.

## What changed in 0.5.0

- **Chat-first behavior remains:** greetings, short replies, and normal questions do not turn into build tasks automatically.
- **Local project workspace:** create, edit, rename, delete, import and download text files; preview HTML in a restricted iframe; run basic static checks; export the project as a ZIP.
- **Scoped terminal:** commands such as `ls`, `cat`, `touch`, `write`, `append`, `mv`, `grep`, `find`, `check`, `preview` and `zip` act on workspace files, not on the phone's operating system.
- **Transformer training lab:** a six-layer causal Transformer with 1,958,977 trainable parameters, trained from random initialization with PyTorch.
- **Bounded experiment scheduler:** can describe up to 1,000,000 deterministic logical trials and execute a selected subset with a configured worker limit.
- **Dedicated GitHub Actions workflow:** runs checks, short training smoke tests, and uploads checkpoints/metrics as an artifact without invoking Gradle or creating an APK.
- **Explicit Build mode:** prepare an implementation brief and optional model-generated draft; the chat mode stays conversational.
- **Local neural model:** one-layer LSTM, 512-token byte-level BPE vocabulary, 128-dimensional embedding and hidden state, and exactly **264,192 trainable parameters** before quantization.
- **No remote AI API:** each APK build trains model weights from random initialization and embeds an int8-quantized model into the app.
- **Conversation history:** threads are stored in local browser/app storage.

## Local file workspace and terminal

Open `workspace.html` from the chat screen using **Arquivos**. The workspace starts with an editable HTML/CSS/JavaScript example. It supports creating files and relative folders, editing content, renaming and deleting files, importing multiple text files, downloading one file, exporting all project text files as a ZIP, basic JSON/classic-JavaScript/HTML checks, and sandboxed HTML preview.

The workspace is **local to Kodex's WebView/browser storage**. It does not automatically read other Android files, write to the GitHub repository, or authenticate to GitHub. The workspace terminal is a restricted project-file command environment, not Bash or an Android system shell; it cannot install dependencies, run native compilers, or execute arbitrary OS commands. Import files explicitly with the picker and export a ZIP to move your work elsewhere. Binary files and ZIP import are not supported by this version.

Safety limits: up to 200 project files, 512 KiB per file, and 1,500 KiB of total text for local project storage. The preview runs in a sandboxed iframe with a restrictive Content Security Policy; it is a convenience preview, not a security-grade sandbox. Static checks are not a replacement for compiler or test execution.

## Agent instruction conventions

The root `AGENTS.md` records the product's persistent operating rules for compatible coding agents, and `.github/copilot-instructions.md` carries repository-specific guidance for GitHub Copilot. Their purpose is to preserve the project direction: conversation by default, mobile/offline-first, no unapproved AI API, truthful execution reports, incremental changes, and validation.

## Important limits

The existing mobile chat LSTM has 264,192 trainable parameters. The separate training-lab Transformer has 1,958,977 trainable parameters. These are parameter counts, not counts of biological neurons, and both architectures are tiny experiments, not medium-scale or frontier models.

The training directory includes a 90-example conversational corpus and a separate 71-example programming/model-training curriculum. This is still a small dataset and can cause severe overfitting. Passing a load test or lowering training loss does not prove broad language understanding or reliable code generation. The larger Transformer is not connected to the chat runtime and is not packaged in an APK by this branch.

Chat Build mode still drafts a brief and checklist; it does not edit the repository or run commands. The file workspace edits only files created or explicitly imported into its local storage. The terminal's `check` command performs static checks; `preview` runs an HTML file in the constrained iframe; neither substitutes for real compiler tests. Repository context displayed in chat is descriptive; source files are not automatically read.

## Open the project

- [Kodex branch](https://github.com/japaguimarassi-create/Security-lab/tree/kodex-programming-ai)
- [APK build workflow](https://github.com/japaguimarassi-create/Security-lab/actions/workflows/build-kodex-apk.yml)
- [Local MLM profile](src/ai/neuron-profile.json)
- [Training corpus](training/data/mobile_dialogue.jsonl)
- [Model training and quantization](training/build_mobile_mlm.py)
- [On-device inference runtime](src/ai/mobile-mlm.js)

## Model architecture and parameter count

The mobile chat LSTM profile remains as historical app code. The new training-lab model is a decoder-only causal Transformer trained for autoregressive next-token prediction:

- Byte-level BPE tokenizer: 256 byte tokens plus 256 learned merges = vocabulary size 512.
- Token embedding: 512 × 128 = 65,536 parameters.
- Input LayerNorm: 128 weights + 128 biases = 256 parameters.
- One LSTM layer: 132,096 parameters.
- Output LayerNorm: 256 parameters.
- Language-model head: 128 × 512 weights + 512 biases = 66,048 parameters.

**Total: 65,536 + 256 + 132,096 + 256 + 66,048 = 264,192 parameters.**

The app's existing LSTM is still separate. The Transformer training lab writes PyTorch checkpoints and metrics to `training/runs/`; the new Transformer is not connected to the JavaScript chat runtime and is not turned into an APK in this branch.

## Run the training lab

With Python 3.12 and PyTorch installed:

```sh
python -m unittest training.tests.test_mobile_mlm training.tests.test_transformer -v
python training/train_transformer.py --data training/data --dry-run
python training/train_transformer.py --data training/data --out-dir training/runs/experiment-001 --steps 2000 --batch-size 4 --eval-every 100
python training/train_transformer.py --data training/data --out-dir training/runs/experiment-001 --steps 4000 --resume training/runs/experiment-001/latest.pt
```

The model has 257 byte/EOS tokens, a 128-token context, 160-dimensional embeddings, 5 attention heads, 6 Transformer blocks and a 640-dimensional feed-forward layer. The script checks the exact parameter count (1,958,977), holds out validation examples before tokenization, records train/validation loss, saves latest and best checkpoints, and can resume optimizer/scheduler state.

Plan up to a million logical experiments without executing them:

```sh
python training/run_sweep.py --data training/data --trials 1000000 --execute 0
```

Run a bounded concurrent subset on your actual machine:

```sh
python training/run_sweep.py --data training/data --trials 1000000 --execute 8 --workers 2 --steps 100
```

The scheduler creates trial configurations lazily, runs only `--execute` actual training jobs and caps parallel processes at `--workers`. Millions of queued candidates do not mean millions of processes running simultaneously. Trial count, step count, or compressed wall-clock time cannot honestly be called equivalent to years of learning.

## GitHub build policy for this branch

Use **Actions → Kodex AI Training Lab → Run workflow** on branch `kodex-0.4.0-workspace`. Select `smoke`, `train`, or `sweep`. It installs CPU PyTorch, runs tests, trains the model and uploads checkpoints/metrics as an artifact. This workflow does not invoke Gradle, build an APK, or publish an Android app. GitHub Actions runner and matrix limits still apply; larger sweeps require proportionate compute and execution time.

## Privacy and safety

The local chat model does not require an inference API key and does not send prompts to a remote model service. Chat Build mode still prepares a brief rather than editing repository files automatically. Workspace files stay in local app/browser storage until explicitly imported or exported. The training pipeline runs only when invoked locally or through the separate GitHub Actions workflow.
