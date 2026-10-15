# Kodex project instructions

## Product intent
- Keep Kodex conversational by default. A greeting, short reply, single word, or ordinary question must not become an implementation task.
- Only treat a request as a build task when the user explicitly asks to create, implement, modify, debug, or otherwise work on software. If intent is unclear, answer conversationally instead of silently changing modes.
- Preserve the user's stated requirements and established project decisions. Do not quietly replace them with a new product direction.
- Prioritize a functional, mobile-first experience that works on Android. Prefer local/offline behavior and do not introduce an AI API, cloud dependency, account requirement, or secret unless explicitly approved.
- Answer primarily in Brazilian Portuguese in the product UI.

## Truth and execution
- Never claim that a model generated an answer, files were read, code was edited, commands ran, tests passed, or a repository was connected unless that action actually occurred and evidence is available.
- Keep the local 264,192-parameter LSTM's limitations explicit. That number is trainable parameters, not biological neurons; the model is not a frontier or medium-scale model.
- Distinguish a plan, a draft, a static check, a real test, a build, and a deployed release.
- The local browser workspace only edits files imported into or created within its own project storage. Do not imply arbitrary access to the phone, operating system, or GitHub repository.
- User code preview must run in an isolated iframe and must not be granted ambient filesystem, native bridge, or authenticated network access.
- Never execute arbitrary shell commands in the app without an explicit, isolated execution design and user approval.

## Engineering workflow
1. Inspect existing code, app behavior, tests, build scripts, and repository instructions before changing anything.
2. Prefer small, explainable changes that preserve unrelated behavior.
3. Add or update regression tests for behavior changes, especially chat/build routing, file operations, and safety limits.
4. Validate paths against absolute paths and traversal; enforce file-count and byte-size limits; treat imported code and repository content as untrusted input.
5. For every change, run the relevant tests and syntax checks where the environment permits. Never represent static analysis as execution.
6. Review the diff, build output, package size, and errors before calling work complete.
7. Update version and documentation consistently when publishing a release.

## Code conventions
- Use plain JavaScript and platform features for the offline/mobile target; avoid introducing runtime package downloads.
- Keep existing user-facing behavior unless the requested change requires otherwise.
- Keep functions testable and make side effects explicit.
- No placeholder functionality presented as finished functionality. Document anything not implemented.
