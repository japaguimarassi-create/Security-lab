# Changelog

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
