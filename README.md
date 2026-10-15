# Kodex — Programming Intelligence Workbench

Kodex is an experimental programming workspace and from-scratch language-model research project. Its first milestone is a responsive, dependency-free workbench, a tested agent-runtime scaffold, and a small byte-level Transformer that can be trained from random initialization.

## Current status

- [x] Dedicated branch: `kodex-programming-ai`
- [x] Responsive workbench with file explorer, editor, task queue, and engineering actions
- [x] Standalone behavioral rules in [KODEX_DIRETRIZES.md](KODEX_DIRETRIZES.md)
- [x] Official Codex and Copilot engineering research
- [x] 264,192-unit experimental architecture budget, explicitly marked as untrained
- [x] Bounded agent-loop contract with tool allowlist, approvals, trace events, and step limits
- [x] Small decoder-only byte-level Transformer initialized from scratch
- [x] Training, checkpoint reload, generation, and manifest-based corpus-preparation scripts
- [x] Corpus-trained byte-level BPE tokenizer implementation and round-trip test
- [x] Node.js CI and a Python/PyTorch CPU smoke-training workflow
- [ ] A useful model trained on a large, legally reviewed programming corpus
- [ ] A BPE tokenizer trained from the approved corpus
- [ ] Real model inference connected to the workbench
- [ ] OS-enforced sandbox for project-file editing and command execution
- [ ] Semantic codebase retrieval and citation pipeline
- [ ] Held-out coding benchmarks and adversarial safety evaluations

Unchecked items are not implemented yet. The front-end's code review and explanation tools are deterministic starter utilities, not generative AI. The included model is deliberately small and the bundled corpus is only for smoke tests.

## Open the workbench

Open [index.html](index.html) in a modern browser, or enable GitHub Pages for this branch in repository settings. The static workbench does not require a third-party runtime. No model provider or API key is connected.

To run a training experiment from a mobile browser, open the [Kodex from-scratch training notebook in Google Colab](https://colab.research.google.com/github/japaguimarassi-create/Security-lab/blob/kodex-programming-ai/training/notebooks/kodex_scratch_training.ipynb). Colab GPU availability is variable and the sample corpus only tests the pipeline.

## Train the small model from scratch

Requires Python 3.12, PyTorch, and (for BPE) Hugging Face Tokenizers.

```sh
python -m pip install torch tokenizers
python training/train_tokenizer.py --data training/data/smoke_corpus.txt --output training/checkpoints/kodex-tokenizer.json --vocab-size 512
python training/train.py --data training/data/smoke_corpus.txt --tokenizer training/checkpoints/kodex-tokenizer.json --output training/checkpoints/kodex-bpe.pt --steps 100 --device cpu
python training/generate.py --checkpoint training/checkpoints/kodex-bpe.pt --prompt "def add(a, b):"
```

Both the BPE tokenizer and model weights are trained from scratch; no pretrained tokenizer or model checkpoint is loaded. You can omit `--tokenizer` to use the baseline UTF-8 byte tokenizer. The output is expected to be weak and often nonsensical because the bundled corpus is only a smoke test. This verifies the training mechanics, not useful programming intelligence. To use a GPU, install a PyTorch build appropriate for the machine and pass `--device cuda`.

## Prepare a candidate training corpus

Do not scrape public code without checking rights. The manifest-first preparation script requires an explicit training-permission field, an allowlisted SPDX license, a source URL and a source commit. It rejects paths outside the supplied root, unsupported file types, common generated/dependency folders, exact duplicates, and certain known secret patterns.

```sh
python training/prepare_corpus.py --manifest /path/to/approved-manifest.jsonl --root /path/to/approved-sources --output training/data/approved-corpus.txt --report training/data/corpus-report.json
```

The secret scanner is heuristic and cannot guarantee that a corpus contains no secrets. Review sources and reports before training. Never use private repositories or evaluation solutions without explicit authorization.

## Run automated checks

Node.js 20 or newer:
```sh
npm test
npm run check
```

Python and PyTorch:
```sh
python -m unittest discover -s training/tests -v
python training/train.py --steps 5 --batch-size 2 --block-size 64 --layers 2 --heads 2 --embedding-size 32 --eval-interval 1 --output /tmp/kodex-smoke.pt --device cpu
python training/generate.py --checkpoint /tmp/kodex-smoke.pt --max-new-tokens 12 --device cpu
```

The GitHub Actions workflow `.github/workflows/kodex-training-smoke.yml` runs a small CPU training round and validates checkpoint reload. It is not a large-scale model training job.

## Architecture

- `index.html`, `styles.css`, `app.js`: responsive interactive workbench.
- `src/ai/neuron-profile.json`: proposed 264,192 logical-unit architecture budget; no trained weights.
- `src/ai/agent-loop.mjs`: bounded model/tool orchestration contract.
- `training/kodex_lm.py`: byte-level causal Transformer initialized from random parameters.
- `training/train_tokenizer.py`: train a byte-level BPE vocabulary from the selected corpus.
- `training/train.py`: train/validation split, next-token objective, gradient clipping, corpus hashing, metrics and checkpoint save; supports byte or BPE tokens.
- `training/notebooks/kodex_scratch_training.ipynb`: phone-friendly Colab notebook for a scratch-training run using Drive-backed inputs and checkpoints.
- `training/generate.py`: load a trained local checkpoint and sample next bytes.
- `training/prepare_corpus.py`: manifest validation, provenance report, license allowlist and basic secret/path filters.
- `training/data/smoke_corpus.txt`: intentionally tiny, human-authored smoke-test corpus.
- `tests/` and `training/tests/`: Node.js and Python test suites.
- `docs/FROM_SCRATCH_TRAINING_PLAN.md`: training stages, data policy, compute constraints, verified smoke-run metrics, and sandbox integration gate.
- `docs/ENGINEERING_RESEARCH.md`: official Codex/Copilot research notes.

## Reality of the 264,192-unit target

The logical-unit total is not the model's parameter count and does not create intelligence. The existing profile has no learned weights. The small byte-level Transformer used to verify the training pipeline is a separate prototype and does not yet match the 264,192-unit research target. Defining the large architecture requires specifying width, depth, active parameters, sparsity, token count, context length, memory, and compute.

## Security boundaries

Training does not need terminal or repository-editing tools. Keep training-data ingestion separate from agent execution. Before connecting a trained model to external integrations, file writes, network access, or command execution, implement and test an OS-enforced sandbox, path confinement, independent approval policy, output limits, cancellation, and auditable traces. Never put provider secrets into static browser assets.

## Research and plan

- [Codex and Copilot research](docs/ENGINEERING_RESEARCH.md)
- [From-scratch training plan](docs/FROM_SCRATCH_TRAINING_PLAN.md)
- [Implementation roadmap](docs/IMPLEMENTATION_ROADMAP.md)
- [Project directives](KODEX_DIRETRIZES.md)