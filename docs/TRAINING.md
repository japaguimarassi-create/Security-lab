# Klod training pipeline

## Dataset formats

Pretraining JSONL: one object per line with `text`, `source_url`, `license`, `language`, and `attribution`.

SFT JSONL: one object per line with `messages`, an array of role/content messages. The final message must be from the assistant. The SFT stage uses assistant-only loss so user/system prompt tokens are context rather than targets.

DPO JSONL: one object per line with `prompt`, `chosen`, and `rejected`. Each pair must be reviewed by a human; do not label model outputs as preferences automatically.

## Pipeline

1. Import a capped streaming sample from FineWeb2.
2. Filter for provenance, license, document quality and duplicates.
3. Run continued pretraining with LoRA and a held-out split.
4. Continue the same LoRA adapter through supervised fine-tuning.
5. Continue the SFT adapter through DPO using reviewed preference pairs.
6. Evaluate on a separate held-out set and compare with the previous checkpoint.

## Commands

```bash
pip install -e ".[data,training]"
python scripts/import_fineweb2.py --language por_Latn --limit 10000 --output data/raw/fineweb2-pt.jsonl
python scripts/prepare_data.py --input data/raw/fineweb2-pt.jsonl --output data/processed/pretrain.jsonl
python scripts/training_preflight.py --stage pretrain --require-gpu
python scripts/train_pretrain.py
python scripts/training_preflight.py --stage sft --require-gpu
python scripts/train_sft.py
python scripts/training_preflight.py --stage dpo --require-gpu
python scripts/train_dpo.py
python scripts/evaluate.py --model Qwen/Qwen3-1.7B-Base --adapter outputs/klod-dpo --dataset data/eval/heldout.jsonl
```

The SFT config loads the continued-pretraining adapter; DPO loads the SFT adapter. Both adapters must be present at their configured paths. For inference, set `KLOD_MODEL_ID=Qwen/Qwen3-1.7B-Base` and `KLOD_ADAPTER_PATH=outputs/klod-dpo`.

## Hardware and release

The preflight command checks data schemas/counts and CUDA availability. The 1.7B base weights alone need multiple GiB; actual training needs additional memory for activations, batches and optimizer state. A GPU with around 16 GiB or more is a practical starting target for LoRA experiments, not a guarantee. This project environment currently has CPU-only PyTorch, so full 1.7B training cannot be honestly reported as complete here.

Keep checkpoints outside GitHub. Record exact model revision, adapter hash, datasets, licenses, configuration, Git commit and evaluation results. Never promote a checkpoint without held-out evaluation and regression checks.
