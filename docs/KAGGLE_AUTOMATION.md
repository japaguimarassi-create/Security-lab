# Treinamento KLOD via GitHub Actions + Kaggle

## Fluxo

O GitHub Actions coordena o processo e o Kaggle fornece a GPU. O treinamento não usa a GPU do telefone nem a máquina de execução do GitHub Actions para carregar o modelo.

O fluxo é dividido intencionalmente em duas execuções:

1. **generate:** o Actions envia um notebook privado ao Kaggle, gera respostas com o professor Qwen3-1.7B e disponibiliza teacher_candidates.jsonl como artefato do GitHub Actions.
2. **train:** depois da revisão humana, o Actions recupera o artefato da primeira execução, confere os IDs aprovados e envia o notebook de treinamento QLoRA do aluno Qwen3-1.7B-Base ao Kaggle.

O processo não aprova automaticamente respostas do professor.

## Configuração única do repositório

Na página do repositório, abra **Settings → Secrets and variables → Actions**.

Crie:

- **Repository secret** KAGGLE_API_TOKEN: token de API do Kaggle.
- **Repository variable** KAGGLE_USERNAME: nome de usuário exato da conta Kaggle.

Não coloque tokens em arquivos, commits, mensagens, artefatos ou no chat. O token deve ser configurado diretamente na área de Secrets do GitHub. A CLI oficial do Kaggle aceita KAGGLE_API_TOKEN como forma de autenticação não interativa.

Para usuários de 13 a 16 anos, o Kaggle exige consentimento parental verificável. O responsável deve concluir a configuração da conta e autorizar seu uso antes de adicionar a credencial.

## Iniciar a geração do professor

Edite data/kaggle/run-request.json na branch development e deixe:

    {
      "phase": "generate"
    }

Salve o commit na branch development. A alteração do arquivo dispara o workflow. A execução remota leva o notebook ao Kaggle e aguarda a geração dos candidatos.

Quando terminar, abra **Actions**, entre na execução mais recente de **KLOD Kaggle remote training** e baixe o artefato klod-teacher-candidates. Ele contém:

- teacher_candidates.jsonl
- teacher_run.json

O campo teacher_run.json contém o identificador do kernel Kaggle e a quantidade de respostas geradas. O ID da execução do GitHub aparece no resumo da execução; guarde-o para a etapa seguinte.

## Revisar e iniciar o aluno

Leia todas as respostas em teacher_candidates.jsonl. Só aprove respostas corretas, úteis e relevantes. O filtro automático não verifica a veracidade.

Depois edite data/kaggle/run-request.json na branch development com o ID da execução geradora e uma lista JSON dos IDs que você revisou:

    {
      "phase": "train",
      "source_run_id": 12345678901,
      "approved_ids": [
        "pt-001",
        "en-004"
      ]
    }

O exemplo acima é apenas a estrutura. Use IDs reais do seu artefato. São necessárias pelo menos 20 aprovações. IDs duplicados, inexistentes ou reprovados pelo filtro automático fazem a execução parar antes do treinamento.

A alteração do arquivo dispara a segunda execução. O Actions recupera o artefato da execução indicada, cria o notebook de treinamento, envia-o ao Kaggle e acompanha treinamento e avaliação.

## Entrega

Ao terminar, baixe o artefato klod-trained-model-and-report na execução de treinamento. Ele contém:

- klod-teacher-distilled-adapter.zip
- klod-teacher-distillation-results.zip
- RELATORIO_KLOD.txt
- Metadados da execução.

O relatório apresenta o identificador do kernel, número de exemplos aprovados, métricas disponíveis, tamanho e hashes SHA-256. A chave da avaliação cega não é baixada.

## Limites operacionais

- A branch padrão main não é modificada. O fluxo por push em development permanece disponível sem mesclar o workflow à branch padrão.
- O GitHub workflow_dispatch só pode ser usado quando o arquivo de workflow existe na branch padrão. Enquanto main permanecer intocada, use o arquivo data/kaggle/run-request.json como gatilho controlado por commit.
- O runner hospedado pelo GitHub tem limite de seis horas neste workflow. A espera pelo Kaggle é limitada a cinco horas e meia; uma execução que ultrapasse esse período pode exigir verificação manual no Kaggle.
- A GPU do Kaggle, a cota disponível, os downloads de pesos e o espaço em disco dependem da conta e do estado do serviço.
- O checkpoint não é promovido automaticamente. A avaliação cega deve ser analisada antes de concluir que houve melhora.
