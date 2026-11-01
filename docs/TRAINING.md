# KLOD training pipeline

## Dataset formats

Pretraining JSONL: one object per line with text, source_url, license, language and attribution.

SFT JSONL: one object per line with messages, an array of role/content messages. The final message must be from the assistant. Assistant-only loss is used for conversational instruction data.

DPO JSONL: one object per line with prompt, chosen and rejected. Each preference pair must be reviewed for correctness and quality.

## Build a broad corpus

Prepare separate, licensed and quality-filtered corpora for Portuguese, English, Spanish, other languages, code, mathematics/science, humanities, general instruction/conversation and technical documents. Conversation and instruction data should cover varied subjects, question types, writing styles and levels of difficulty. Do not let one specialist domain dominate the mixture.

The initial mixture is an experiment: Portuguese 30%, English 25%, Spanish 5%, other languages 5%, code 10%, mathematics/science 10%, humanities 5%, instruction/conversation 5% and technical documents 5%. These weights are starting hypotheses. Check actual token counts, duplicates, language balance and held-out domain metrics before adjusting them.

Use scripts/prepare_data.py to clean and normalize each source, then run:

```bash
python scripts/build_mixture.py --config configs/data_mixture.yaml --output data/processed/mixture.jsonl --max-documents 500000
```

## Training stages

```bash
pip install -e ".[data,training]"
python scripts/training_preflight.py --stage pretrain
python scripts/train_pretrain.py
python scripts/training_preflight.py --stage sft
python scripts/train_sft.py
python scripts/training_preflight.py --stage dpo
python scripts/train_dpo.py
python scripts/evaluate.py --model Qwen/Qwen3-1.7B-Base --adapter outputs/klod-dpo --dataset data/eval/heldout.jsonl
```

The training scripts use 4-bit NF4 QLoRA by default and require an NVIDIA CUDA GPU with bitsandbytes support. The continued-pretraining adapter is loaded by SFT; the SFT adapter is loaded by DPO. A GPU with 16 GiB or more is a practical starting point, not a guarantee. Reduce sequence lengths and batch size if memory is insufficient.

For inference after DPO, set KLOD_MODEL_ID=Qwen/Qwen3-1.7B-Base and KLOD_ADAPTER_PATH=outputs/klod-dpo.

## Colab

Open the KLOD QLoRA notebook in the repository and select a GPU runtime. Its capped first run validates the training path; it is not enough to claim a finished general-purpose model.

## Release gate

The source code and training pipeline are not trained model weights. No KLOD-specific adapter should be claimed until an actual GPU run produces it and held-out evaluations pass. Record the base revision, adapter hash, datasets, licenses, configuration, Git commit and domain-specific evaluation results before promoting any checkpoint.
