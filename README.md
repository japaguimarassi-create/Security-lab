# Kodex 0.4.0 — Local Language Model and Project Workspace

Kodex is an experimental, mobile-first programming assistant with a locally executed neural language model. Version 0.4.0 keeps conversation separate from implementation planning, bundles trained model weights into the Android APK, and adds a usable local file workspace.

## What changed in 0.4.0

- **Chat-first behavior remains:** greetings, short replies, and normal questions do not turn into build tasks automatically.
- **Local project workspace:** create, edit, rename, delete, import and download text files; preview HTML in a restricted iframe; run basic static checks; export the project as a ZIP.
- **No runtime package downloads:** workspace functionality uses browser/platform features and is packaged with the Android app.
- **Explicit Build mode:** prepare an implementation brief and optional model-generated draft; the chat mode stays conversational.
- **Local neural model:** one-layer LSTM, 512-token byte-level BPE vocabulary, 128-dimensional embedding and hidden state, and exactly **264,192 trainable parameters** before quantization.
- **No remote AI API:** each APK build trains model weights from random initialization and embeds an int8-quantized model into the app.
- **Conversation history:** threads are stored in local browser/app storage.

## Local file workspace 0.4.0

Open `workspace.html` from the chat screen using **Arquivos**. The workspace starts with an editable HTML/CSS/JavaScript example. It supports creating files and relative folders, editing content, renaming and deleting files, importing multiple text files, downloading one file, exporting all project text files as a ZIP, basic JSON/classic-JavaScript/HTML checks, and sandboxed HTML preview.

The workspace is **local to Kodex's WebView/browser storage**. It does not automatically read other Android files, write to the GitHub repository, authenticate to GitHub, run shell commands, install dependencies, or compile arbitrary projects. Import files explicitly with the picker and export a ZIP to move your work elsewhere. Binary files and ZIP import are not supported by this version.

Safety limits: up to 200 project files, 512 KiB per file, and 1,500 KiB of total text for local project storage. The preview runs in a sandboxed iframe with a restrictive Content Security Policy; it is a convenience preview, not a security-grade sandbox. Static checks are not a replacement for compiler or test execution.

## Agent instruction conventions

The root `AGENTS.md` records the product's persistent operating rules for compatible coding agents, and `.github/copilot-instructions.md` carries repository-specific guidance for GitHub Copilot. Their purpose is to preserve the project direction: conversation by default, mobile/offline-first, no unapproved AI API, truthful execution reports, incremental changes, and validation.

## Important limits

The 264,192 figure is the actual trainable parameter count, not a count of biological neurons. In standard language-model terms, this is a **tiny/compact model**, not a medium-scale or frontier model.

The training data at `training/data/mobile_dialogue.jsonl` contains 90 curated, mostly Portuguese conversation and programming examples. The default APK workflow runs 500 training steps from random initialization. This proves that model training, quantization, bundling, and on-device inference are connected; it does not prove broad language understanding or reliable coding ability. The model can make mistakes, repeat phrases, or return poor answers. The chat filters some obviously invalid outputs and uses explicit fallback responses for common greetings and very short messages. The separate workspace is a file editor, not evidence of stronger model intelligence.

Chat Build mode still drafts a brief and checklist; it does not edit the repository or run commands. The new separate workspace edits only the files created or imported into its local storage. Repository context displayed in chat is descriptive; source files are not automatically read.

## Open the project

- [Kodex branch](https://github.com/japaguimarassi-create/Security-lab/tree/kodex-programming-ai)
- [APK build workflow](https://github.com/japaguimarassi-create/Security-lab/actions/workflows/build-kodex-apk.yml)
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

Push changes to `kodex-programming-ai` that touch the Android app, model runtime, or model training files to trigger the GitHub Actions build. The artifact is named `Kodex-Android-APK-v0.4.0` and remains available for 14 days. It is a debug APK signed with the debug key; it is not a Google Play-certified release.

## Privacy and safety

The local model does not require an inference API key and does not send chat prompts to a remote model service. The chat history is kept in local app/browser storage. The Build mode only prepares a proposed response; no code is executed and no project files are changed automatically.
