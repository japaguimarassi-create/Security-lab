# KLOD AI

Klod é uma plataforma modular de linguagem: motor de inferência, API REST, memória, recuperação de conhecimento, planejamento estruturado e pipelines de treinamento.

## Estado honesto do projeto

O repositório contém o software e os pipelines. O checkpoint de fundação é Qwen3-1.7B; os pesos próprios/LoRA do Klod ainda dependem de execução de treinamento em GPU. Não confunda código de treinamento com pesos treinados. O protótipo atual não é um modelo pré-treinado do zero.

## Módulos

- `core/engine`: inferência Qwen3 e carregamento opcional de adaptador PEFT.
- `memory`: memória SQLite isolada por namespace.
- `knowledge`: FTS5 com documentos, fonte, licença e atribuição.
- `planner`: gera planos JSON e valida ações por allowlist; não executa ações.
- `api`: chat, memória, conhecimento, status e carregamento.
- `training`: continuação de pré-treino, SFT, DPO e avaliação.

## Instalação

Python 3.11+, PyTorch 2.6+ e Transformers 4.51+ para Qwen3.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[model,data,training,test]"
cp .env.example .env
```

Defina uma chave real em `.env`. Não publique segredos.

## API

```bash
uvicorn klod.api:app --host 127.0.0.1 --port 8000
```

Com `KLOD_LOAD_MODEL=false`, API e memória funcionam sem descarregar pesos; geração retorna 503 até o modelo ser carregado. Para geração real, configure `KLOD_LOAD_MODEL=true`, o modelo Qwen3 e, opcionalmente, `KLOD_ADAPTER_PATH`.

Leia `docs/API.md`, `docs/ARCHITECTURE.md` e `docs/TRAINING.md`.

## Treinamento

FineWeb2 em streaming, filtragem por licença e deduplicação:

```bash
python scripts/import_fineweb2.py --language por_Latn --limit 10000 --output data/raw/fineweb2-pt.jsonl
python scripts/prepare_data.py --input data/raw/fineweb2-pt.jsonl --output data/processed/pretrain.jsonl
python scripts/train_pretrain.py
python scripts/train_sft.py
python scripts/train_dpo.py
python scripts/evaluate.py --model outputs/klod-sft --dataset data/eval/heldout.jsonl
```

O importador limita a amostra. FineWeb2 declara ODC-By 1.0: preserve atribuição. Verifique a licença de cada outra fonte e respeite privacidade e termos. Use RAG para atualizar conhecimento atual sem modificar os pesos.

## Limites de computação

O treinamento do modelo 1.7B requer GPU e armazenamento apropriados. Um telefone Android ou os executores gratuitos padrão do GitHub não são ambiente realista para pré-treinar 1.7B. GitHub armazena código, configs e testes, não checkpoints nem corpora grandes. Os scripts verificam a existência e tamanho mínimo dos dados, mas os resultados dependem de hardware, dados e avaliação.
