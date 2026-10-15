# Repository-wide instructions for Kodex

- Read AGENTS.md before implementing a change. Preserve the user's established product requirements and any more-specific applicable instructions.
- Keep the product chat-first: ordinary conversation, greetings, one-word messages, and short replies never trigger a build plan automatically. Construction requires a clear implementation request or explicit mode selection.
- The app must remain mobile-first and usable on Android. Prefer offline/local execution and never add a remote AI API, analytics, login requirement, or paid dependency without explicit approval.
- Be accurate about the 264,192-parameter local LSTM: it is an experimental tiny model, not a GPT/Copilot replacement. Do not claim model quality from a smoke test alone.
- Inspect the repository and the affected files before editing. Create the smallest complete change, then add regression tests and run the available test, syntax-check, and build commands.
- Never claim to have opened files, run commands, passed tests, or connected a repository unless tool output proves it.
- File workspace actions operate only on user-created/imported project files stored locally by Kodex. Validate relative paths and reject traversal and absolute paths. Enforce size/count limits and treat imported code as untrusted.
- Preview user HTML in a sandboxed iframe with restrictive Content Security Policy. Do not provide ambient filesystem access or authenticated network credentials to preview code.
- Keep plans, generated drafts, static checks, tests, APK builds, and deployments clearly distinguished in UI and documentation.
- Use Brazilian Portuguese for the app's user-facing copy. Keep code and technical identifiers in English.
- Update tests, documentation, package/APK versions, and workflow paths together when applicable. Review the final diff for regressions and unrelated edits.
