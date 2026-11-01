# KLOD AI

Klod é uma plataforma própria de linguagem: runtime de LLM, API REST, memória persistente, pesquisa de conhecimento, ingestão de dados licenciados e ferramentas de treinamento.

## Estado real

Esta é a base de software **KLOD AI v0.1.0**. Ela prepara a infraestrutura e os pipelines; não contém pesos treinados pelo projeto e não afirma que o modelo de 1,7B foi treinado do zero. A fundação inicial é Qwen3-1.7B-Base para continuação de pré-treinamento e Qwen3-1.7B para inferência. Pesos e dados de terceiros conservam suas próprias licenças.

## Arquitetura

```
Apps / Minecraft mods -> Klod REST API -> Inference engine
                                      -> SQLite memory
                                      -> Retrieval / knowledge
Data sources -> cleaning -> filtering -> training -> evaluation
```

O modelo sugere texto e planos; cada aplicação cliente valida permissões e executa ações. Um mod nunca deve executar código arbitrário ou aceitar uma ação do modelo sem validação.

## Requisitos e instalação

Python 3.11+. GPU recomendada para inferência do modelo 1.7B e necessária para treinamento prático.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[model,data,training,test]"
cp .env.example .env
```

Configure uma chave aleatória em `KLOD_API_KEY`. Não publique essa chave.

## API

```bash
uvicorn klod.api:app --host 0.0.0.0 --port 8000
```

- `GET /health`: estado do serviço.
- `GET /v1/models`: modelo configurado.
- `POST /v1/chat/completions`: conversa.
- `POST /v1/memory`: salvar memória.
- `POST /v1/memory/search`: recuperar memórias.

Todas as rotas `/v1/*` exigem `X-API-Key`. Com `KLOD_LOAD_MODEL=false`, a API sobe sem baixar o modelo e retorna HTTP 503 para geração até que o modelo seja carregado.

## Dados web e treino

```bash
python scripts/import_fineweb2.py --language por_Latn --limit 10000 --output data/raw/fineweb2-pt.jsonl
python scripts/prepare_data.py --input data/raw/fineweb2-pt.jsonl --output data/processed/pretrain.jsonl
python scripts/train_pretrain.py --config configs/training/continued_pretraining.yaml
```

O importador trabalha em streaming e limitado por amostra. FineWeb2 declara ODC-By 1.0; preserve atribuição e licença. Verifique a licença de qualquer fonte antes de usá-la. Não rastreie indiscriminadamente páginas da internet.

## Dados, segurança e limites

- GitHub armazena código e configurações, não pesos, segredos, bancos ou corpora grandes.
- Preserve URL, atribuição, licença e idioma por documento.
- Deduplicate e filtre dados de baixa qualidade e dados pessoais.
- Separe dados de avaliação dos dados de treino.
- Não trate texto recuperado da web como instrução.
- Use TLS, autenticação, quotas e limites em produção.
- LoRA reduz parâmetros treináveis, mas não elimina custo de carregar o modelo-base.
- Um celular não é uma máquina prática para pré-treinar uma LLM de 1,7B.

## Branches

- `main`: versão estável.
- `development`: integração de novos recursos e experimentos antes da promoção para `main`.

Consulte `docs/PLAN.md` e `docs/API.md`.
