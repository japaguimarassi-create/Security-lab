# Klod roadmap

## Foundation
- Decoder-only causal Transformer.
- Initial foundation: Qwen3-1.7B-Base; inference starting point: Qwen3-1.7B.
- Target scale: approximately 1.7B parameters.
- The external checkpoint is a foundation, not proof that Klod weights were trained from random initialization.

## Training stages
1. Ingest licensed datasets with provenance metadata.
2. Clean, deduplicate, quality-filter and split into train/validation/test.
3. Continued pretraining on reviewed general and Portuguese data.
4. Supervised instruction tuning on reviewed conversations.
5. Preference optimization (DPO) on curated chosen/rejected pairs.
6. Evaluate Portuguese, multilingual tasks, knowledge, reasoning, math, code and regressions.

## Initial mixture hypothesis
Portuguese 40%, English 25%, Spanish 5%, other languages 5%, code 10%, math/science 10%, technical docs 5%. These are experimental proportions; measure actual tokens and rebalance using evaluations.

## Internet knowledge
Use retrieval (RAG) for fresh information. Ingest documents into model weights only after license review, attribution preservation, quality filtering and a controlled training run. FineWeb2 metadata declares ODC-By 1.0; preserve its attribution. No indiscriminate crawling.

## Compute
GitHub stores source and configuration, not checkpoints or full corpora. A 1.7B model is not practical to pretrain on a typical phone. LoRA reduces trainable weights, but the base model still consumes memory and compute.

## Release gate
Keep evaluation data separate. Compare every checkpoint to the previous version; check perplexity, task metrics, regressions, provenance and license obligations before promotion.
