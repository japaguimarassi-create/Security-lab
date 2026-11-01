# Klod training pipeline

## Dataset formats

Pretraining JSONL: one object per line with `text`, `source_url`, `license`, `language`, and `attribution`.

SFT JSONL: one object per line with `messages`, an array of role/content messages. Include a system message only where needed; the final message should be assistant.

DPO JSONL: one object per line with `prompt`, `chosen`, and `rejected`. Each pair must be reviewed; do not generate preference labels from unverified model guesses.

## Stages

1. Import a capped streaming sample from FineWeb2.
2. Run `scripts/prepare_data.py` and review rejection/acceptance statistics.
3. Run `scripts/train_pretrain.py` for continued causal-language-model training with LoRA and a held-out split.
4. Run `scripts/train_sft.py` with approved conversations.
5. Run `scripts/train_dpo.py` only after human-reviewed preference pairs are available.
6. Run `scripts/evaluate.py` on a held-out evaluation set that was never used in training.

## Commands

```bash
pip install -e ".[data,training]"
python scripts/import_fineweb2.py --language por_Latn --limit 10000 --output data/raw/fineweb2-pt.jsonl
python scripts/prepare_data.py --input data/raw/fineweb2-pt.jsonl --output data/processed/pretrain.jsonl
python scripts/train_pretrain.py
python scripts/train_sft.py
python scripts/train_dpo.py
python scripts/evaluate.py --model outputs/klod-sft --dataset data/eval/heldout.jsonl
```

Training scripts are GPU-oriented. They do not silently claim success if datasets are missing or too small. BF16/FP16 are enabled only when a compatible CUDA device is available. For 1.7B weights, estimate GPU memory before starting; LoRA does not make loading the base model free.

## Model release

Store checkpoints outside Git (Hugging Face Hub private repo, object storage, or attached disk). Record the exact base revision, adapter hash, datasets and licenses, training config, git commit, evaluation results, and known limitations for every candidate release.
