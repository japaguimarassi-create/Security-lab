# KLOD roadmap and current state

## Product definition

KLOD is a general-purpose multilingual assistant for open-domain questions and practical work across many fields. Specialists are optional helpers, never limits on the assistant. Minecraft is one integration domain among many.

## Foundation

- Decoder-only causal Transformer.
- Initial foundation: Qwen3-1.7B-Base; inference starting point: Qwen3-1.7B.
- Target scale: approximately 1.7B parameters.
- The external checkpoint is a foundation, not evidence that KLOD weights were trained from random initialization.

## Platform modules (0.5)

- General-purpose assistant prompt and fallback.
- Conservative automatic domain routing and force-general option.
- Optional programming, science, mathematics, research, writing, education, creative, business and Minecraft modules.
- Persistent memory with optional semantic recall.
- Hybrid knowledge retrieval using FTS5 and multilingual E5 embeddings.
- Source/license/attribution metadata returned with answers.
- Structured action plans validated against caller-provided allowlists.

## Training stages

1. Ingest licensed datasets with provenance metadata.
2. Clean, deduplicate, quality-filter and split into train/validation/test.
3. Continue pretraining on reviewed multilingual and domain-balanced text.
4. Supervised instruction tuning on broad, reviewed conversations and tasks.
5. Preference optimization (DPO) on curated chosen/rejected pairs.
6. Evaluate Portuguese and multilingual quality, reasoning, mathematics, code, science, writing and out-of-domain regressions.

## Initial mixture hypothesis

Portuguese 30%, English 25%, Spanish 5%, other languages 5%, code 10%, mathematics/science 10%, humanities 5%, instruction/conversation 5%, technical documents 5%. These are experimental proportions, not guarantees of competence. Measure token counts, source quality and held-out performance before rebalancing.

## Internet knowledge

Use retrieval for fresh information. Ingest documents into model weights only after license review, attribution preservation, quality filtering and a controlled training run. Do not crawl indiscriminately.

## Compute and release gate

GitHub stores source and configuration, not checkpoints or full corpora. A 1.7B model is not practical to pretrain on a typical phone. LoRA reduces trainable weights, but the base model still consumes memory and compute. Keep evaluation data separate; compare every checkpoint with the previous version and verify metrics, regressions, provenance and license obligations before promotion.
