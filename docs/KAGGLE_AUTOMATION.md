# Automação remota do treinamento KLOD com Kaggle

## O que o script automatiza

O arquivo scripts/kaggle_remote_train.py coordena duas execuções privadas no Kaggle usando o Kaggle CLI oficial. O processamento do modelo acontece nas GPUs do Kaggle; o Android apenas envia notebooks, acompanha o estado, apresenta as respostas para revisão e baixa os arquivos finais.

1. Envia um notebook privado para gerar as respostas candidatas do professor Qwen3-1.7B.
2. Aguarda a conclusão e baixa apenas o ZIP que contém os candidatos.
3. Exibe cada pergunta e resposta no Termux para revisão humana.
4. Impede a continuação se menos de 20 exemplos forem aprovados.
5. Cria um segundo notebook privado com os exemplos aprovados incorporados.
6. Envia o treinamento QLoRA do aluno Qwen3-1.7B-Base e a avaliação cega.
7. Aguarda a execução, baixa os dois ZIPs finais e gera um relatório com métricas, tamanhos e hashes SHA-256.

O script não baixa a chave privada da avaliação cega e não envia credenciais para o GitHub.

## Requisitos e autenticação

- Python 3.11 ou mais recente.
- Git.
- Kaggle CLI instalado: python -m pip install --upgrade kaggle.
- Uma conta Kaggle habilitada e com acesso à cota de GPU.
- Token/API authentication configurado para o Kaggle CLI.

A autenticação pode ser feita com kaggle auth login ou com o arquivo kaggle.json no diretório ~/.kaggle/. Proteja esse arquivo com permissões restritas (chmod 600). Nunca cole o token no chat, no código ou no GitHub.

**Idade:** a política do Kaggle exige consentimento parental verificável para usuários de 13 a 16 anos. O responsável deve concluir o processo oficial antes do uso da conta. Consulte https://www.kaggle.com/privacy/pt.

## Execução pelo Android/Termux

Instale os requisitos no Termux:

    pkg update
    pkg install python git -y
    python -m pip install --upgrade kaggle

Clone a branch de desenvolvimento:

    git clone -b development https://github.com/japaguimarassi-create/Security-lab.git
    cd Security-lab

Configure a autenticação oficial do Kaggle e execute:

    python scripts/kaggle_remote_train.py

O programa solicitará o nome de usuário do Kaggle. Também aceita:

    python scripts/kaggle_remote_train.py --username SEU_USUARIO

Mantenha o Termux aberto enquanto o programa estiver aguardando as execuções remotas. O script usa o acelerador NvidiaTeslaT4 (T4x2) e habilita Internet no notebook; a disponibilidade da GPU depende da cota e da disponibilidade atual da conta.

## Revisão obrigatória

Cada resposta candidata aparece no terminal. Use y para aprovar, n para rejeitar ou q para interromper. A opção padrão é rejeitar. Os filtros automáticos verificam estrutura e qualidade superficial, mas não confirmam se uma resposta é factualmente correta.

O treinamento só começa após pelo menos 20 aprovações explícitas. O conjunto inicial de 48 prompts é um teste do pipeline, não uma base suficiente para afirmar inteligência geral ampla.

## Arquivos entregues

Quando as duas execuções terminam com sucesso, o script salva em ~/storage/downloads/KLOD-Kaggle-AAAAmmdd-HHMMSS/ (quando o diretório de Downloads do Termux está disponível) ou no diretório pessoal:

- klod-teacher-distilled-adapter.zip: adaptador LoRA para inferência.
- klod-teacher-distillation-results.zip: adaptador, métricas, exemplos aprovados, configurações e avaliação cega.
- RELATORIO_KLOD.txt: identificadores das execuções, contagem dos exemplos, arquivos, hashes e métricas disponíveis.

O relatório registra o que a execução realmente produziu. Um job concluído não prova que o aluno superou o professor; a avaliação cega ainda precisa ser analisada separadamente.

## Falhas e limites

- A automação não cria contas nem contorna consentimento, cotas ou regras do Kaggle.
- Não é possível garantir que uma T4x2 esteja disponível ou que todos os pacotes e pesos caibam na memória.
- Se um job falhar, o script interrompe o fluxo e tenta mostrar os logs disponíveis. Não inicia o treino com dados não revisados.
- A execução permanece associada à conta Kaggle autenticada pelo usuário; não existe uma conta pertencente ao assistente.
