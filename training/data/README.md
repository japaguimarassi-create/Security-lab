# Kodex training data

## Current starter corpus

`mobile_dialogue.jsonl` is a small, curated Portuguese-oriented set for testing the training/inference path, conversation/build routing, and basic programming explanations. It is not a broad web-scale dataset and is not expected to train a capable assistant on its own. Keep test examples held out; do not add the test split to training after reading its metrics.

## Adding dialogue examples

Use JSON Lines (one JSON object per non-empty line). A dialogue record uses:

```json
{"mode":"chat","prompt":"O que é uma variável?","answer":"Uma variável é um nome associado a um valor."}
```

A raw text record may use `{"text":"..."}`. Use original, reviewed examples that you are permitted to use for model training. Avoid private conversations, personal data, confidential code, credentials, copied proprietary material, or text without a documented source/license basis.

Validate and normalize dialogue data before training:

```sh
python training/normalize_dialogue_corpus.py --input training/data/mobile_dialogue.jsonl --output /tmp/kodex-dialogue-clean.jsonl --report /tmp/kodex-dialogue-report.json
```

The report includes duplicate counts, output SHA-256, record counts, and warnings. The script does not establish that a dataset is legally authorized or factually good; the person contributing the data remains responsible for that review.

## Adding source code from repositories

Use `training/prepare_corpus.py` with a JSONL manifest, a local checkout of the source files, and a separate output corpus. Each manifest row must contain:
- `path`: relative path within the supplied source root;
- `source_url`: URL identifying the upstream file/project;
- `commit`: a specific upstream commit reference;
- `license`: one of the script's explicit allowlisted licenses;
- `training_permitted`: the boolean value `true`.

The preparer deliberately excludes other licenses unless the allowlist and policy are reviewed and updated. It also rejects likely secrets and path escapes. A successful scan is not legal advice and does not guarantee the corpus is free from secrets, personal data, generated junk, duplicates across differently formatted files, or license ambiguity.

Before increasing corpus volume, prefer lawful, traceable data with deduplication, language/license metadata, quality filtering, and held-out benchmarks. Millions of low-quality or unauthorized rows do not substitute for good training data.
