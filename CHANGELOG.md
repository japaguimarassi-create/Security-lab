# Changelog

## 0.5.0 — AI training lab and project terminal

- Added a causal decoder-only Transformer with 2,002,048 trainable parameters at a 1,024-token vocabulary.
- Added byte-level BPE tokenizer training, corpus ingest/deduplication, deterministic train/validation split, next-token loss, gradient clipping, metrics, checkpoints, resume support and a local interactive chat CLI.
- Added a SQLite-backed queue for up to 10,000,000 independent experiment definitions with bounded concurrency and validation-loss ranking.
- Added optional PyTorch DistributedDataParallel execution for properly provisioned multi-process hardware.
- Added a real local project CLI and a browser terminal for the Kodex file workspace.
- Added CI tests and an actual two-step training smoke run for the larger model configuration.
- Added an opt-in workflow for longer training that produces PyTorch checkpoint artifacts only. No APK is built by this branch.
- Preserved the existing AGENTS.md and Copilot repository instructions without modifying them.

### Limits
The corpus is still small and the full training workflow is opt-in. The CI smoke run executes two optimizer steps and does not produce a generally capable chatbot. Million-trial queues are not millions of concurrent processes; concurrency is hardware and runner limited.


## 0.4.0 — Local project workspace

- Added a standalone, mobile-first workspace that creates, edits, renames, deletes, imports, and downloads project text files.
- Added local project persistence, a multi-file editor with line numbers, relative-path validation, file-count and size limits, and ZIP export.
- Added basic static checks for JSON, classic JavaScript syntax, and HTML structure; module JavaScript receives a warning when it cannot be checked by the local parser.
- Added isolated HTML preview in a sandboxed iframe with a restrictive Content Security Policy.
- Added root AGENTS.md and GitHub Copilot repository instructions that preserve chat-first, mobile/offline-first, truthful reporting, and safe file handling.
- Added regression tests for project paths, static-check reporting, starter files, ZIP structure, and preview policy.
- Updated the Android package to 0.4.0 and included workspace assets in APK packaging.

### Known limitations

- The chat's Build mode still creates a plan/brief; it does not autonomously edit this repository or run shell commands.
- Workspace files are local to the app/browser and are not committed to GitHub. Importing/exporting is explicit.
- Only text files are imported. ZIP import, binary assets, arbitrary terminal execution, dependencies and compilation are not implemented.
- Static checks do not replace the relevant compiler, real tests, a security review, or human review.
- The local neural model is unchanged and remains experimental.
