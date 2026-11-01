# Treinamento da KLOD no Kaggle

## O que este fluxo faz

O pipeline usa o checkpoint instrucional `Qwen/Qwen3-1.7B` como professor congelado. Ele gera respostas candidatas para um currículo geral. Depois de revisão humana, o projeto treina um adaptador LoRA separado sobre `Qwen/Qwen3-1.7B-Base`.

O professor não é atualizado. O aluno não recebe os pesos do professor: aprende com demonstrações aprovadas por SFT/QLoRA. O resultado é um adaptador, não um novo modelo-base completo.

## Preparação do notebook

1. Abra um notebook no Kaggle e importe `notebooks/KLOD_Kaggle_Teacher_Distillation.ipynb` da branch `development`.
2. Nas configurações do notebook, selecione `GPU T4x2`.
3. Ative `Internet: On`. O repositório e os pesos do Hugging Face são baixados durante a execução.
4. Execute as células em ordem.

A primeira célula de GPU limita a visibilidade a uma única T4 (GPU 0). As duas T4 não são tratadas como uma única GPU de 32 GB; o pipeline não inicia DDP nem treinamento distribuído. Ele dimensiona a execução para uma GPU com 16 GB.

O notebook atualiza o clone existente com `git pull --ff-only`. Ele não remove a pasta do projeto quando é reexecutado, preservando dados e checkpoints gerados naquela sessão.

## Revisão humana obrigatória

A célula de geração cria candidatos em `data/generated/teacher_candidates.jsonl`. Os filtros automáticos verificam formato, tamanho, eco da pergunta e repetição. Eles não verificam se uma resposta é verdadeira.

Na célula de revisão, leia cada resposta e preencha `approved_ids` somente com identificadores que você verificou. O pipeline exige no mínimo 20 exemplos aprovados para o primeiro ensaio. Não aprove automaticamente todo o conjunto.

A exportação gera `data/processed/teacher_approved.jsonl`. Tanto o pré-teste quanto o treinador verificam a aprovação e a qualidade dos registros. Também verificam os papéis das mensagens e exigem uma resposta final do assistente.

## Treinamento e avaliação

O aluno usa QLoRA NF4, rank 16, alpha 32, dropout 0.05, learning rate 2e-5, sequência de até 2048 tokens, batch por dispositivo 1, acumulação de gradiente 16 e cinco épocas.

A precisão é selecionada pela GPU: FP16 quando BF16 não é suportado (caso da T4) e BF16 apenas quando o dispositivo declara suporte. O treinador grava `training_metrics.json` junto ao adaptador.

Após o treinamento, a avaliação gera respostas do professor e do aluno para perguntas separadas do currículo de geração, alterna aleatoriamente a posição A/B e grava o mapeamento em um arquivo separado. Faça a revisão cega antes de abrir a chave.

## Arquivos de saída

O notebook prepara dois arquivos:

- `klod-teacher-distilled-adapter.zip`: somente o adaptador para inferência.
- `klod-teacher-distillation-results.zip`: adaptador, métricas, dados aprovados, configurações e avaliação cega, sem a chave que identifica professor/aluno.

A chave `evaluation/distillation_answer_key.json` deve permanecer privada até o fim da revisão. Não envie dados de revisão, chaves ou arquivos de saída para repositórios públicos.

No Kaggle, use **Save Version** depois que a execução terminar para preservar os arquivos de saída da sessão.

## Limites conhecidos

As 48 perguntas iniciais são apenas um teste de funcionamento do pipeline, não um currículo suficiente para criar capacidade geral ampla. As oito perguntas de avaliação também são pequenas demais para provar superioridade. Expanda os dados com exemplos diversos e revisados, mantenha uma avaliação isolada maior e acompanhe regressões por domínio.

A T4 é um ponto de partida, não uma garantia de que toda execução caiba em memória. Em caso de falta de memória, reduza `max_sequence_length` no arquivo `configs/training/distillation_sft.yaml` antes de repetir o treinamento e preserve a mesma configuração registrada nos resultados.

O Kaggle exige que contas de usuários de 13 a 16 anos tenham consentimento parental verificável. Consulte a [política de privacidade do Kaggle](https://www.kaggle.com/privacy/pt) e faça a configuração da conta com um responsável.
