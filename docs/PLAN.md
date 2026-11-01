# KLOD roadmap and current state

## Product definition

KLOD is a general-purpose multilingual assistant for open-domain questions and practical work across many fields. Specialists are optional helpers, never limits on the assistant. Minecraft is one integration domain among many.

## Foundation

- Decoder-only causal Transformer.
- Teacher: current instruct checkpoint Qwen3-1.7B.
- Student base: Qwen3-1.7B-Base.
- Target scale: approximately 1.7B parameters.
- The external checkpoints are foundations, not evidence that KLOD weights were trained from random initialization.

## Platform modules (0.6)

- General-purpose assistant prompt and fallback.
- Conservative automatic domain routing and force-general option.
- Optional programming, science, mathematics, research, writing, education, creative, business and Minecraft modules.
- Persistent memory and hybrid semantic/lexical knowledge retrieval.
- Teacher-student self-distillation: frozen teacher generates answers; approved examples train a student LoRA adapter.
- Structured action plans validated against caller-provided allowlists.

## Teacher-student pipeline

The current instruct checkpoint generates demonstrations from a broad starter curriculum. Candidates have provenance and automated quality checks, then require explicit human approval. A student begins from the base checkpoint and learns through QLoRA SFT. The starter set has 48 prompts and is only a pipeline validation set. Build thousands of diverse, reviewed examples and a separate held-out evaluation set before calling the model broadly capable.

## Further training

1. Continue pretraining on reviewed multilingual and domain-balanced licensed text.
2. Supervised instruction tuning across general and specialist domains.
3. Teacher-student distillation from reviewed demonstrations.
4. Preference optimization (DPO) on curated chosen/rejected pairs.
5. Evaluate Portuguese and multilingual quality, reasoning, mathematics, code, science, writing and out-of-domain regressions.

## Initial mixture hypothesis

Portuguese 30%, English 25%, Spanish 5%, other languages 5%, code 10%, mathematics/science 10%, humanities 5%, instruction/conversation 5%, technical documents 5%. These are experimental proportions, not guarantees of competence. Measure token counts, source quality and held-out performance before rebalancing.

## Internet knowledge

Use retrieval for fresh information. Ingest documents into model weights only after license review, attribution preservation, quality filtering and a controlled training run. Do not crawl indiscriminately.

## Compute and release gate

GitHub stores source and configuration, not checkpoints or full corpora. A 1.7B model is not practical to pretrain on a typical phone. LoRA reduces trainable weights, but the base model still consumes memory and compute. Keep evaluation data separate; compare every checkpoint with the teacher and previous student versions, and verify metrics, regressions, provenance and license obligations before promotion.
