# Kodex: training from scratch

## Decision

Build the training pipeline without importing pretrained model weights. Start with a small byte-level decoder-only Transformer, train its weights from random initialization on a documented toy corpus, and prove that checkpoints and generation work. Only after this reproducible baseline should the project scale data, tokenizer, context length, model size, and compute.

The initial prototype is a learning and infrastructure experiment, not a useful Copilot/Codex competitor. Training from scratch means initializing and learning the model's weights without a pretrained checkpoint. It does not mean avoiding open-source libraries such as PyTorch, nor does it mean that the agent runtime, shell tools, IDE, and model weights must all be part of one neural network.

## What must be separate

1. **Training pipeline:** corpus manifests, licensing/provenance, cleaning, deduplication, tokenizer, model architecture, optimizer, checkpointing, metrics, and reproducible configs.
2. **Inference runtime:** tokenizer/model loading, resource limits, structured output validation, timeouts, and logs.
3. **Agent harness:** task planning, repository retrieval, diffs, tool registry, permission checks, tests, approvals, and step budgets.
4. **Sandbox:** OS-enforced file/network/process limits around any code or tools the agent may run.

The sandbox does not need to be embedded in the model or learned from examples. It must enforce permissions outside the model. Before the model can control tools on real projects, the runtime, sandbox, approval policy, path containment, and audit trail must be tested. The model training process itself will not receive repository write or shell-execution tools.

## Stages and exit criteria

### Stage 0 — Reproducibility and governance
- [x] Create a separate branch and CI pipeline.
- [x] Separate project directives from engineering documentation.
- [ ] Version all training configurations and report the source commit.
- [ ] Decide the project-wide license and the conditions for redistributing weights.
- [ ] Establish a dataset card and a model card before publishing any corpus or checkpoint.

Exit: a run can be tied to a precise commit, data manifest, config, and software versions.

### Stage 1 — Tiny from-scratch proof
- [x] Implement a small decoder-only Transformer using PyTorch primitives, initialized randomly.
- [x] Use a transparent UTF-8 byte tokenizer (256 token values) for the first baseline, avoiding dependency on pretrained tokenizer/model assets.
- [x] Train on a small, intentionally limited smoke corpus.
- [x] Save and reload checkpoints; generate bytes after training.
- [ ] Record actual train/validation loss, tokens processed, elapsed time, peak memory, and checkpoint hash for a smoke run.

Exit: the complete loop runs on CPU or a supported GPU and decreases training loss on a tiny test set. Loss reduction alone is not evidence of useful coding ability.

### Stage 2 — A proper tokenizer and a curated corpus
- Train a BPE tokenizer from scratch on the approved training corpus and version its vocabulary.
- Build a manifest-first ingestion pipeline. Every source needs a known origin, license, training permission, and provenance record.
- Start with self-authored examples, code explicitly donated for training, and permissively licensed repositories after license verification.
- Deduplicate exact and near-duplicate code; group related files by repository to reduce leakage.
- Exclude secrets, credentials, private repositories, binary/generated/dependency files, and sources not approved for training.
- Split by repository and time where applicable; never use benchmark solutions in training data.
- Balance languages, paradigms, documentation, tests, configuration, debugging, and safe tool-use examples.

Exit: dataset manifests and filtering reports can reconstruct every retained source without storing secrets in logs.

### Stage 3 — Specialized code pretraining
- Choose the parameter count, context length, and token budget only after measuring available compute and memory.
- Scale training gradually; retain loss curves, throughput, data mix, config, checkpoint hashes, and hardware details.
- Evaluate on held-out code completion, syntax/compilation, tests, code explanation, retrieval, and multilingual programming tasks.
- Do not increase model size simply to satisfy a neuron count. Parameters, active units, training tokens, memory use, and data quality are different measures.

Exit: the model beats small random and heuristic baselines on versioned, held-out metrics, with no benchmark contamination.

### Stage 4 — Instruction and tool-use learning
Only after pretraining produces a useful base model:
- Build high-quality examples for explain, implement, test, debug, refactor, review, and documentation tasks.
- Train instruction-following behavior with curated examples and preference or outcome signals where available.
- Teach the model to emit a strict structured tool-call format, but keep actual permission enforcement in the host runtime.
- Evaluate refusal behavior for unsafe requests, prompt-injection resistance, and correct recognition of uncertainty.

Exit: tool-call schema reliability, completion quality, and safety regression tests meet explicit thresholds.

### Stage 5 — Agent integration and sandboxed tool use
Before enabling attachments, external integrations, terminal execution, or autonomous edits:
- Confine every tool to explicit paths and capabilities.
- Run commands in an OS/container sandbox with resource, process, filesystem, and network policies.
- Keep approvals independent of sandbox settings; neither model text nor repository instructions can grant permission.
- Require user review of diffs before writes to user files, commits, external calls, or publication.
- Add cancellation, timeouts, per-task budgets, secret redaction, and complete tool traces.
- Test path traversal, shell injection, prompt injection, exfiltration, symlink attacks, and approval bypasses.

Exit: adversarial tests show that hostile inputs cannot expand permissions, escape the workspace, or access undeclared network targets.

### Stage 6 — Evaluations and scaling
Create reproducible tests with unseen tasks, private holdouts, compiler/test feedback, and adversarial cases. Report accuracy, test pass rate, regression rate, retrieval evidence, latency, energy/compute, memory, and cost. Track contamination and distinguish measured results from expectations.

Exit: any published capability has a reproducible evaluation protocol and honest model/dataset cards.

## Architecture note: 264,192 neurons

The existing `src/ai/neuron-profile.json` counts logical units across proposed layers. It is not a count of learned facts, parameters, or currently running neurons. Its very wide dense layers would be expensive to connect conventionally. The first runnable baseline intentionally uses a much smaller architecture so the entire train/save/load/generate loop can be verified.

If the requirement remains exactly more than 264,000 active logical units, that must be defined in terms of a specific architecture and activation accounting rule. A 264,192-unit target is not an adequate training specification. We need model width/depth, attention pattern, parameter count, sparsity, vocabulary, sequence length, token budget, and training compute.

## Compute constraints

GitHub is suitable for versioning, CI, tiny CPU smoke tests, data-manifest validation, and reproducibility. A standard GitHub Actions runner is not a free large-scale GPU-training cluster. Large model pretraining needs dedicated GPU compute, high-throughput storage, checkpoints, monitoring, and a budget.

For order-of-magnitude planning, dense Transformer pretraining compute is often approximated as proportional to 6 × parameters × training tokens. This is a planning heuristic, not a hardware-time guarantee. Published compute-optimal research also shows that parameter count must be considered together with the number of training tokens; larger is not automatically better.

## Data and licensing

- Never use scraped repositories just because they are publicly reachable.
- Store repository URL/commit, file path, detected or declared SPDX license, permission status, filtering decisions, and hashes in a manifest.
- Respect license terms, notice and attribution requirements, dataset terms, and opt-out requests.
- Do not include secrets or personal information.
- Keep evaluation data outside all train/validation pipelines.
- Do not distribute a checkpoint until its source-data rights, license, and intended use have been reviewed.

References:
- Compute-optimal scaling: https://arxiv.org/abs/2203.15556
- Train a causal language model from scratch: https://huggingface.co/docs/course/chapter7/6
- Train tokenizers from scratch: https://huggingface.co/docs/tokenizers/python/latest/quicktour.html
- FineWeb dataset and curation: https://huggingface.co/papers/2406.17557
- BigCode dataset governance and licensing: https://www.bigcode-project.org/docs/about/the-stack/
- The Stack opt-out process: https://github.com/bigcode-project/opt-out-v2
- PyTorch FSDP for distributed training: https://docs.pytorch.org/docs/stable/fsdp.html
- Agent sandboxing, approvals and trust boundaries: https://code.visualstudio.com/docs/copilot/security