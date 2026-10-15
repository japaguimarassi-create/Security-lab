# Kodex — Programming Intelligence Workbench

Kodex is an experimental programming workspace for research and implementation of a coding assistant. Its first milestone is a responsive, dependency-free workbench plus a tested agent-runtime foundation. The interface is designed as a software engineering console rather than a generic chat page.

## Current status

- [x] Dedicated branch: `kodex-programming-ai`
- [x] Responsive workbench with file explorer, editor, task queue, and engineering actions
- [x] Standalone behavioral rules in [KODEX_DIRETRIZES.md](KODEX_DIRETRIZES.md)
- [x] Research notes comparing official Codex and GitHub Copilot capabilities
- [x] Explicit 264,192-unit experimental architecture profile
- [x] Model/tool interfaces and a bounded agent-loop scaffold
- [x] Automated Node.js tests and CI workflow
- [ ] Trained or downloaded coding model
- [ ] Real inference adapter connected to the UI
- [ ] Sandboxed project-file editing and command execution
- [ ] Repository indexing, embeddings, retrieval, and citation pipeline
- [ ] Benchmarks on coding tasks and adversarial safety evaluations

The unchecked items are not implemented yet. The UI's local review and explanation helpers are deterministic starter utilities, not a trained AI model.

## Try the interface

Open `index.html` in a modern browser, or enable GitHub Pages for this branch in the repository settings. The site uses static files and has no third-party runtime dependencies.

## Run automated checks

Requires Node.js 20 or newer.

```sh
npm test
npm run check
```

## Architecture

- `index.html`, `styles.css`, `app.js`: interactive client-side workbench.
- `src/ai/neuron-profile.json`: named experimental logical-unit budget. It is an architecture target, not trained weights.
- `src/ai/agent-loop.mjs`: bounded orchestration contract with explicit model and tool interfaces.
- `src/ai/heuristic-model.mjs`: deterministic fallback for tests and local demonstrations only.
- `src/quality/quality-gate.mjs`: transparent completion checks.
- `tests/`: automated checks for the architecture and agent loop.
- `docs/ENGINEERING_RESEARCH.md`: design findings from official product documentation.
- `KODEX_DIRETRIZES.md`: project directives only.

## About the 264,192 neurons

The initial profile totals **264,192 logical units**, which exceeds the requested 264,000 threshold. This number alone does not create intelligence. The profile has no trained weights and is not yet a working large neural network; it is a testable architectural budget for a future sparse, expert-routed model. Real capability requires a trained model or a properly integrated existing model, a curated programming corpus, tool-use training or orchestration, and evaluations.

## Design principles

Kodex is being built around repository-aware context, a plan/act/verify loop, observable tool calls, human approval for risky actions, test execution, code review, and evidence-backed answers. This borrows high-level engineering practices documented for Codex and Copilot without copying their proprietary implementation or branding.

## Security and privacy

No model provider is connected by default. Do not put provider keys in browser code. Never execute generated code or shell commands outside a restricted workspace. Read [KODEX_DIRETRIZES.md](KODEX_DIRETRIZES.md) before contributing.

## Research

See [docs/ENGINEERING_RESEARCH.md](docs/ENGINEERING_RESEARCH.md) for official sources and how the findings shape Kodex.