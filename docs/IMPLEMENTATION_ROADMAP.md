# Kodex implementation roadmap

## Honest starting point

The current branch contains a working static workbench, deterministic local code inspections, a bounded agent-loop contract, tests, and CI. It contains **no trained model weights, tokenizer, inference engine, codebase embeddings, or sandboxed command runner**. The roadmap below is the path from this scaffold to a real coding assistant, not a claim that those systems already exist.

## Stage 1 — Secure runtime foundations

Deliverables:
- [x] Explicit model-adapter contract through `model.complete()`.
- [x] Tool allowlist and structured tool-call validation.
- [x] Maximum step count and cancellation signal.
- [x] Approval gate for tools marked as consequential.
- [x] Trace events for steps, tool start/finish, denied approvals, and final status.
- [x] Automated tests and CI.
- [ ] Per-tool JSON schemas and bounded output sizes.
- [ ] Durable task records, token/cost ceilings, wall-clock timeouts, and crash recovery.
- [ ] Redacted logs and a versioned trace format.

Exit criterion: malformed model outputs cannot invoke tools; every tool is allowlisted; write/execute/network operations are blocked unless an explicit policy grants them.

## Stage 2 — Real inference without hard-wiring a vendor

Select an existing, legally usable code-capable model before attempting to train a foundation model from scratch. Compare model license, supported languages, context size, quantization options, tool-use ability, memory requirement, benchmark performance, and redistribution rights.

Preferred integration order:
1. Add a server-side adapter contract with timeouts, cancellation, typed errors, rate limits, and redacted telemetry.
2. Prototype a local model runtime compatible with the target hardware.
3. Keep inference selection independent of the UI and agent tools.
4. Make remote providers optional, explicit, and disabled until the user configures them.
5. Never embed provider secrets inside `app.js`, static HTML, or any downloadable front-end bundle.

An adapter only becomes supported after an integration test returns a model response, handles failure/cancellation, and confirms that secrets are not exposed in browser assets or logs.

## Stage 3 — Programming knowledge and retrieval

Build a source registry before building a large dataset:
- Official language specifications and documentation.
- Official compiler, build tool, standard library, and framework documentation.
- License-compatible educational examples and repositories.
- Version metadata, source URLs, license identifiers, retrieval date, and deduplication fingerprints.

Then implement:
- Language-aware parsing where practical; safe fallback chunking otherwise.
- File/path/line provenance for every retrieved code fragment.
- Hybrid search: exact identifiers and BM25 first, semantic retrieval once a compatible embedding model exists.
- Ranking by language, package version, recency, and repository context.
- Secret, binary, generated-file, dependency-folder, and user-exclusion filters.
- Prompt-injection handling: repository text is untrusted context, never a replacement for runtime policy.
- Clear separation between the model's pretrained knowledge and retrieved current documentation.

Exit criterion: benchmark retrieval precision and recall on questions with known relevant files; every quoted project fact points to a real path and range.

## Stage 4 — Programming workbench

Implementation sequence:
1. Workspace file access through a root-confined API.
2. Search symbols and code references.
3. Apply a unified diff to a temporary working tree.
4. Display the exact proposed diff and affected files.
5. Run permitted tests, linters, compilers, and type checkers in a sandbox.
6. Detect failures and allow bounded repair iterations.
7. Present validation results and let the user accept, reject, or export the diff.
8. Add Git branch creation and pull-request preparation only behind explicit permissions.

Do not let model output reach a shell or filesystem directly. The host runtime must validate path containment, tool arguments, command allowlists, resource ceilings, and network policy.

## Stage 5 — Evaluation, not self-reported intelligence

Create a held-out evaluation set with:
- Small bug fixes with regression tests.
- Multi-file feature tasks.
- Code understanding questions with path-and-line evidence.
- Unit-test generation and mutation testing.
- Type errors, lint failures, and compiler diagnostics.
- Dependency/version and API-documentation questions.
- Prompt injection in README files, comments, tests, and web content.
- Data-leakage, path traversal, approval-bypass, and command-abuse tests.

Measure task pass rate, regression rate, test coverage, security findings, instruction adherence, citation accuracy, repair attempts, latency, memory, and cost. Record model, prompt, tool versions, runtime settings, and dataset version. Avoid evaluating only on examples used for training.

## Stage 6 — Specialization and optional training

Training is a later step, not a substitute for correct data and evaluation:
1. Begin with a suitable pretrained model and confirm its license.
2. Curate and deduplicate training examples with explicit provenance.
3. Remove secrets, personal information, malicious payloads with no defensive purpose, and content that cannot lawfully be used.
4. Build instruction-following examples for explain, implement, test, debug, refactor, review, and documentation tasks.
5. Use held-out tests before selecting fine-tuning or adapter training.
6. Compare base and adapted model on both target tasks and safety regressions.
7. Keep data, training config, checkpoints, evaluation results, and release notes versioned.
8. Only claim a measured capability after reproducible evaluation.

A 264,192-unit layout by itself is not a foundation model. A viable language model also needs a tokenizer, learned parameters, training objective, data pipeline, optimizer/training compute, checkpoints, inference implementation, and evaluations. A densely connected implementation of the proposed layer sizes would be impractical; the profile intentionally reserves the count for future sparse/expert-routed research rather than allocating dense matrices.

## Immediate next deliverables

- Implement a typed, local-file-only workspace tool with path traversal protection.
- Add tests for all permission boundaries and malformed tool input.
- Add one real inference adapter selected after deciding between local-only and optional remote execution.
- Connect Ask/Build/Review modes to the agent runtime rather than to local demo utilities.
- Add a release checklist requiring successful CI, documented limitations, and reproducible evaluation results.