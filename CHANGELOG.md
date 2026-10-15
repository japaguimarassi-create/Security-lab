# Changelog

## 0.5.0 — Project terminal and AI training lab

- Added an interactive, command-history-enabled project terminal for scoped workspace files.
- Added file commands: `pwd`, `ls`, `tree`, `cd`, `cat`, `head`, `tail`, `wc`, `stat`, `touch`, `mkdir`, `rmdir`, `write`, `append`, `mv`, `rm`, `grep` and `find`.
- Added terminal access to static checks, isolated HTML preview, ZIP export and training experiment planning.
- Added a six-layer causal Transformer with 1,958,977 trainable parameters and byte/EOS tokenization, plus separate train/validation data, loss metrics, checkpoint/resume and deterministic seeds.
- Added a curated 71-example programming and model-training curriculum alongside the existing conversational corpus.
- Added a streaming experiment scheduler that can define up to one million logical trials and execute a subset through a bounded process pool.
- Added a dedicated GitHub Actions AI Training Lab workflow for tests, CPU training and artifact upload. It does not call Gradle or create an APK.
- Added architecture, data-split, tokenization, parameter-count and scheduler tests.

### Limits retained

- The chat runtime still uses its previous local LSTM; the larger Transformer has not been integrated into chat inference.
- The UI terminal is a restricted project-file shell, not Bash or an Android OS terminal. It does not execute arbitrary native commands, install packages, or run compilers.
- One million logical trials can be queued/described, not run all at once without corresponding compute capacity.
- The training dataset remains small, so overfitting is likely; validation and external evaluation are required.
- The project AGENTS.md and GitHub Copilot instruction files are not changed by this release.

## 0.4.0 — Local project workspace

- Added a standalone, mobile-first workspace that creates, edits, renames, deletes, imports, and downloads project text files.
- Added local project persistence, a multi-file editor with line numbers, relative-path validation, file-count and size limits, and ZIP export.
- Added basic static checks for JSON, classic JavaScript syntax, and HTML structure; module JavaScript receives a warning when it cannot be checked by the local parser.
- Added isolated HTML preview in a sandboxed iframe with a restrictive Content Security Policy.
- Added root AGENTS.md and GitHub Copilot repository instructions that preserve chat-first, mobile/offline-first, truthful reporting, and safe file handling.
- Added regression tests for project paths, static-check reporting, starter files, ZIP structure, and preview policy.
- Updated the Android package source version to 0.4.0; no APK is built by the AI Training Lab branch.

### Known limitations

- The chat's Build mode still creates a plan/brief; it does not autonomously edit this repository or run shell commands.
- Workspace files are local to the app/browser and are not committed to GitHub. Importing/exporting is explicit.
- Only text files are imported. ZIP import, binary assets, arbitrary terminal execution, dependencies and compilation are not implemented.
- Static checks do not replace the relevant compiler, real tests, a security review, or human review.
- The local neural model is experimental.
