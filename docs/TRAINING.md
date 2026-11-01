# Klod training pipeline

## Dataset formats

Pretraining JSONL: one object per line with `text`, `source_url`, `license`, `language`, and `attribution`.

SFT JSONL: one object per line with `messages`, an array of role/content messages. The final message must be from the assistant. SFT uses assistant-only loss: user/system tokens provide context, while assistant messages are prediction targets. Current TRL supports this for Qwen3 conversational data.

DPO JSONL: one object per line with `prompt`, `chosen`, and `rejected`. Each pair must be human-reviewed.

## Corpus construction

Import each FineWeb2 language separately, then clean each source:

```bash
python scripts/import_fineweb2.py --language por_Latn --limit 200000 --output data/raw/pt.jsonl
python scripts/prepare_data.py --input data/raw/pt.jsonl --output data/processed/pt.jsonl
python scripts/import_fineweb2.py --language eng_Latn --limit 200000 --output data/raw/en.jsonl
python scripts/prepare_data.py --input data/raw/en.jsonl --output data/processed/en.jsonl
python scripts/import_fineweb2.py --language spa_Latn --limit 50000 --output data/raw/es.jsonl
python scripts/prepare_data.py --input data/raw/es.jsonl --output data/processed/es.jsonl
```

Prepare `multilingual.jsonl`, `code.jsonl`, `science.jsonl` and `technical.jsonl` from separately licensed sources. The mixture config assigns initial weights 40/25/5/5/10/10/5 percent. These are hypotheses; measure token counts and revise based on held-out evaluations.

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

The training scripts use 4-bit NF4 QLoRA by default, requiring an NVIDIA CUDA GPU and bitsandbytes. The continued-pretraining adapter is loaded by SFT; the SFT adapter is loaded by DPO. A GPU with 16 GiB or more is a practical starting target, not a guarantee. Reduce sequence lengths and batch size if memory is insufficient.

For inference after DPO, set `KLOD_MODEL_ID=Qwen/Qwen3-1.7B-Base` and `KLOD_ADAPTER_PATH=outputs/klod-dpo`.

## Colab

Open the [KLOD QLoRA notebook](https://colab.research.google.com/github/japaguimarassi-create/Security-lab/blob/development/notebooks/KLOD_QLoRA_Pretraining.ipynb) and select a GPU runtime. It performs a small first continuation-pretraining run on a capped Portuguese FineWeb2 sample and saves the adapter to Google Drive. This short run validates the training path; it is not enough to claim a finished general-purpose model.

## Release

The development environment used for this work has CPU-only PyTorch, no CUDA and three logical CPU cores. Full 1.7B QLoRA training could not be run here. The scripts and tests are present, but resulting adapters must be trained on external GPU hardware. Record base revision, adapter hash, datasets, licenses, configuration, Git commit and held-out results. Never promote a checkpoint without regression testing.
