# Kodex AI Lab 0.5.0 — Terminal and Transformer Training

Kodex is an experimental, mobile-first programming assistant with a locally executed neural language model. Version 0.5.0 adds a project terminal and a from-scratch causal Transformer training lab while retaining the existing local file workspace. This branch does not build an APK.

## What changed in 0.4.0

- **Chat-first behavior remains:** greetings, short replies, and normal questions do not turn into build tasks automatically.
- **Local project workspace:** create, edit, rename, delete, import and download text files; preview HTML in a restricted iframe; run basic static checks; export the project as a ZIP.
- **No runtime package downloads:** workspace functionality uses browser/platform features and is packaged with the Android app.
- **Explicit Build mode:** prepare an implementation brief and optional model-generated draft; the chat mode stays conversational.
- **Local neural model:** one-layer LSTM, 512-token byte-level BPE vocabulary, 128-dimensional embedding and hidden state, and exactly **264,192 trainable parameters** before quantization.
- **No remote AI API:** each APK build trains model weights from random initialization and embeds an int8-quantized model into the app.
- **Conversation history:** threads are stored in local browser/app storage.

## Kodex Project Terminal 0.5.0

Open [terminal.html](terminal.html) from the chat or file workspace. The terminal provides commands for the shared local project files: `pwd`, `ls`, `tree`, `cat`, `head`, `tail`, `grep`, `find`, `touch`, `mkdir`, `write`, `append`, `cp`, `mv`, `rm --yes`, `node --check`, `run js`, `check`, `status`, and `export`.

This is a **project terminal**, not a general Android/Linux shell. It does not run `bash`, `apt`, `npm`, `pip`, or arbitrary operating-system commands. JavaScript can be run in a restricted iframe with a five-second cutoff. The actual training/build executor is a GitHub Actions workflow, whose source and logs are available to inspect.

## AI training lab 0.5.0

The new model in `training/model.py` is a decoder-only causal Transformer, trained from random initialization:
- UTF-8 byte tokenizer with 257 IDs (256 possible bytes and EOS).
- Embedding width 256, two Transformer blocks, four attention heads, feed-forward width 1,024, and context length 128.
- **1,678,592 trainable parameters** with tied input/output token embeddings (about 2.13 times 780,000). This is a parameter count, not a count of biological neurons.
- AdamW optimization, warmup plus cosine learning-rate decay, gradient clipping, train/validation/test splits, loss/perplexity metrics, corpus hashes, and resumable checkpoints.
- A deterministic experiment scheduler can represent up to 1,000,000,000 candidate trial IDs without writing a billion-row queue file. Each shard derives its candidates by index and can run a bounded number of actual experiments. Completed shards select the checkpoint with the lowest held-out validation loss and retain the test loss separately.

The model is still small and trained from a tiny current corpus of around 90 conversation/programming examples. Increasing parameter count does not create useful knowledge by itself; the project needs a much larger, licensed, high-quality, deduplicated corpus, carefully controlled validation/test sets, and human review of generated answers.

### Run the remote training workflow

Open [Kodex ML Lab workflow](https://github.com/japaguimarassi-create/Security-lab/actions/workflows/kodex-ml-lab.yml) on branch `kodex-ai-lab`. The workflow supports:
- `plan`: schedule and shard the candidate queue without training models.
- `smoke`: run a two-step end-to-end test.
- `train`: train one model and create checkpoints/metrics.
- `sweep`: run bounded independent training trials across shards.

The sweep does **not** secretly train a million models just because the queue contains a million candidate IDs. GitHub Actions caps each job matrix at 256 jobs, and the actual number of simultaneous runners depends on plan quotas and runner capacity. Use the `trials_per_shard` limit to control the real compute budget. Run outputs are artifacts retained for 14 days.

## Local file workspace 0.4.0

Open `workspace.html` from the chat screen using **Arquivos**. The workspace starts with an editable HTML/CSS/JavaScript example. It supports creating files and relative folders, editing content, renaming and deleting files, importing multiple text files, downloading one file, exporting all project text files as a ZIP, basic JSON/classic-JavaScript/HTML checks, and sandboxed HTML preview.

The workspace and project terminal are **local to Kodex's WebView/browser storage**. It does not automatically read other Android files, write to the GitHub repository, authenticate to GitHub, run shell commands, install dependencies, or compile arbitrary projects. Import files explicitly with the picker and export a ZIP to move your work elsewhere. Binary files and ZIP import are not supported by this version.

Safety limits: up to 200 project files, 512 KiB per file, and 1,500 KiB of total text for local project storage. The preview runs in a sandboxed iframe with a restrictive Content Security Policy; it is a convenience preview, not a security-grade sandbox. Static checks are not a replacement for compiler or test execution.

## Agent instruction conventions

The root `AGENTS.md` records the product's persistent operating rules for compatible coding agents, and `.github/copilot-instructions.md` carries repository-specific guidance for GitHub Copilot. Their purpose is to preserve the project direction: conversation by default, mobile/offline-first, no unapproved AI API, truthful execution reports, incremental changes, and validation.

## Important limits

The 264,192 figure is the actual trainable parameter count, not a count of biological neurons. In standard language-model terms, this is a **tiny/compact model**, not a medium-scale or frontier model.

The training data at `training/data/mobile_dialogue.jsonl` contains 90 curated, mostly Portuguese conversation and programming examples. The default APK workflow runs 500 training steps from random initialization. This proves that model training, quantization, bundling, and on-device inference are connected; it does not prove broad language understanding or reliable coding ability. The model can make mistakes, repeat phrases, or return poor answers. The chat filters some obviously invalid outputs and uses explicit fallback responses for common greetings and very short messages. The separate workspace is a file editor, not evidence of stronger model intelligence.

Chat Build mode still drafts a brief and checklist; it does not edit the repository or run commands. The new separate workspace edits only the files created or imported into its local storage. Repository context displayed in chat is descriptive; source files are not automatically read.

## Open the project

- [Kodex branch](https://github.com/japaguimarassi-create/Security-lab/tree/kodex-programming-ai)
- [Kodex ML Lab workflow (no APK build)](https://github.com/japaguimarassi-create/Security-lab/actions/workflows/kodex-ml-lab.yml)
- [Terminal](terminal.html)
- [Transformer architecture](training/model.py)
- [Training script](training/train_language_model.py)
- [Million-scale trial scheduler](training/experiment_swarm.py)
- [Research and limits](docs/ml-training-system.md)
- [Local MLM profile](src/ai/neuron-profile.json)
- [Training corpus](training/data/mobile_dialogue.jsonl)
- [Model training and quantization](training/build_mobile_mlm.py)
- [On-device inference runtime](src/ai/mobile-mlm.js)

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

Push changes to `kodex-programming-ai` that touch the Android app, model runtime, or model training files to trigger the GitHub Actions build. This `kodex-ai-lab` branch does not compile an APK. The ML workflow publishes training metrics and checkpoints as artifacts; these are not Android installation packages.

## Privacy and safety

The local model does not require an inference API key and does not send chat prompts to a remote model service. The chat history is kept in local app/browser storage. The Build mode only prepares a proposed response; no code is executed and no project files are changed automatically.
