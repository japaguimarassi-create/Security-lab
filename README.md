# KLOD AI

Klod é uma plataforma modular de linguagem: motor de inferência, API REST, memória, recuperação de conhecimento, planejamento estruturado e pipelines de treinamento.

## Estado

O repositório contém o software e os pipelines. A fundação é Qwen3-1.7B-Base (~1,7B parâmetros). Os pesos/adaptadores do Klod ainda dependem de treinamento real em GPU; o código não é apresentado como um modelo pré-treinado do zero.

## Módulos

- Motor Qwen3 com adaptador PEFT opcional.
- Memória SQLite por namespace.
- Conhecimento com pesquisa lexical FTS5 e proveniência.
- Planejador JSON com lista permitida de ações; não executa ações.
- API autenticada para chat, memória, conhecimento, planos e carga do modelo.
- Pipeline de pré-treino contínuo, SFT com perda somente nas respostas, DPO e avaliação.
- Mistura de corpus por pesos para equilibrar português, inglês, espanhol, código, ciências e documentação.
- QLoRA 4-bit para reduzir memória de treino.

## Instalação

Python 3.11+, PyTorch 2.6+, Transformers 4.51+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[model,data,training,test]"
cp .env.example .env
uvicorn klod.api:app --host 127.0.0.1 --port 8000
```

Configure uma chave forte em `.env`. Com `KLOD_LOAD_MODEL=false`, a API inicia sem carregar pesos; a geração retorna HTTP 503 até carregar o modelo. Consulte `docs/API.md`.

## Treinamento

Siga `docs/TRAINING.md` na ordem: importar e filtrar dados, construir mistura, pré-treinar LoRA, continuar no SFT, refinar no DPO e avaliar em dados separados. Checkpoints e corpora grandes ficam fora do Git.

## Limites de hardware

O ambiente desta sessão tem PyTorch somente em CPU, sem CUDA e três CPUs lógicas. Não há GPU para treinar o modelo 1.7B aqui. QLoRA precisa de GPU NVIDIA e bitsandbytes; um smartphone não é uma máquina de treinamento adequada para esse modelo.
