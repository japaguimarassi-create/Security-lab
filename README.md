# KLOD AI

Klod é uma plataforma modular de linguagem: motor de inferência, API REST, memória, recuperação de conhecimento, planejamento estruturado e pipelines de treinamento.

## Estado real

O repositório contém o software e os pipelines. A fundação inicial é Qwen3-1.7B-Base (~1,7B parâmetros). Os pesos e adaptadores próprios do Klod só passam a existir depois da execução dos estágios de treinamento em GPU. O código não é apresentado como um modelo que já foi treinado do zero.

## Módulos

- Inferência Qwen3 com carregamento opcional de adaptador PEFT.
- Memória SQLite isolada por namespace.
- Recuperação lexical FTS5 com URL, licença e atribuição preservadas.
- Planejador JSON que valida ações por allowlist e não executa ações.
- API REST autenticada para chat, memória, conhecimento e planos.
- Treino em sequência: continuação de pré-treino, SFT apenas nas respostas do assistente, DPO e avaliação.

## Instalação e API

Python 3.11+, PyTorch 2.6+ e Transformers 4.51+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[model,data,training,test]"
cp .env.example .env
uvicorn klod.api:app --host 127.0.0.1 --port 8000
```

Configure uma chave forte em `.env`. Com `KLOD_LOAD_MODEL=false`, a API sobe sem carregar os pesos; a geração responde 503 até o modelo ser carregado. Consulte `docs/API.md`.

## Treinamento

Consulte `docs/TRAINING.md`. A sequência é importante: cada estágio reaproveita o adaptador gerado pelo anterior. O pipeline de dados seleciona documentos com proveniência e licença; FineWeb2 é importado em streaming com limite.

## Limites

A máquina desta sessão tem PyTorch somente em CPU e três CPUs lógicas; não há CUDA nem Transformers instalados. Portanto, os módulos e scripts podem ser desenvolvidos e testados, mas o ajuste dos pesos 1.7B exige GPU externa. GitHub armazena código e configs, não pesos e corpora grandes. Um telefone Android não é uma plataforma prática para treinar esta LLM.
