# Treinamento KLOD em cinco etapas no GitHub Actions + Kaggle

## Como o treinamento foi dividido

O plano original de cinco épocas de SFT foi dividido em cinco etapas cumulativas. Cada branch representa 20 pontos percentuais do plano:

| Branch | Etapa | Trabalho desta etapa | Origem dos pesos |
|---|---:|---|---|
| training/20-percent | 20% | 1 época | Qwen3-1.7B-Base |
| training/40-percent | 40% | 1 época adicional | adaptador 20% |
| training/60-percent | 60% | 1 época adicional | adaptador 40% |
| training/80-percent | 80% | 1 época adicional | adaptador 60% |
| training/100-percent | 100% | 1 época adicional | adaptador 80% |

Os percentuais indicam a fração do plano original de cinco épocas, não uma porcentagem de qualidade, perda ou tempo restante. O número real de passos depende da quantidade e do comprimento dos exemplos aprovados.

Cada etapa reabre os pesos do adaptador anterior e executa mais uma época. O estado do otimizador é reiniciado em cada etapa; os pesos aprendidos são preservados. Portanto, é um fine-tuning incremental em cinco execuções, não uma única sessão ininterrupta de Trainer.

O GitHub Actions coordena as etapas e armazena os artefatos temporários. O Kaggle é quem fornece a GPU para carregar e treinar o Qwen. Os pesos dos adaptadores não são commitados no Git.

## Configuração única do repositório

Na página do repositório, abra **Settings → Secrets and variables → Actions** e crie:

- **Repository secret** KAGGLE_API_TOKEN: token de API do Kaggle.
- **Repository variable** KAGGLE_USERNAME: nome de usuário da conta Kaggle.

O token só deve existir no campo de Secret do GitHub. Não o coloque em arquivos, commits, artefatos ou mensagens. A CLI oficial do Kaggle recebe o token pela variável de ambiente KAGGLE_API_TOKEN.

Para usuários de 13 a 16 anos, o Kaggle exige consentimento parental verificável. Um responsável deve concluir o processo oficial de consentimento antes da utilização da conta e da credencial.

## Etapa inicial: gerar e revisar dados

Primeiro, altere data/kaggle/run-request.json na branch development para:

    {
      "phase": "generate"
    }

Faça commit em development. O workflow envia um notebook privado ao Kaggle, gera as respostas do professor Qwen3-1.7B e publica o artefato klod-teacher-candidates.

Abra **Actions**, entre na execução de **KLOD Kaggle staged training** e baixe o artefato. Ele contém teacher_candidates.jsonl e teacher_run.json.

Leia cada resposta. O filtro automático não verifica se a resposta é verdadeira. Escolha pelo menos 20 IDs corretos, úteis e relevantes. Guarde o ID numérico da execução do GitHub que gerou o artefato.

## Executar as cinco etapas

Cada branch já tem um arquivo data/kaggle/run-request.json em modo setup. Para iniciar uma etapa, edite esse arquivo na própria branch da etapa.

### Primeira etapa: 20%

Na branch training/20-percent, use esta estrutura:

    {
      "phase": "train_stage",
      "stage_percent": 20,
      "teacher_run_id": 12345678901,
      "previous_stage_run_id": null,
      "approved_ids": [
        "pt-001",
        "en-004"
      ]
    }

Substitua o ID de execução e a lista pelos valores reais. São necessárias pelo menos 20 aprovações. Faça commit em training/20-percent.

Quando terminar, baixe o artefato klod-stage-20-adapter da execução. Guarde também o ID numérico dessa execução do GitHub.

### Etapas seguintes

Repita o mesmo processo nas branches seguintes. Mantenha o mesmo teacher_run_id e a mesma lista de IDs revisados. Atualize stage_percent e informe o ID da execução anterior em previous_stage_run_id.

| Branch | stage_percent | previous_stage_run_id |
|---|---:|---|
| training/40-percent | 40 | ID da execução concluída em 20% |
| training/60-percent | 60 | ID da execução concluída em 40% |
| training/80-percent | 80 | ID da execução concluída em 60% |
| training/100-percent | 100 | ID da execução concluída em 80% |

Cada execução baixa o adaptador da etapa anterior, valida o arquivo e só então solicita a GPU do Kaggle. Se o artefato anterior estiver ausente, inválido ou for de uma execução errada, o processo para antes de treinar.

## Artefatos gerados em cada etapa

Cada execução de treinamento publica:

- klod-stage-N-adapter: adaptador LoRA que a próxima etapa deve usar.
- klod-stage-N-report: pacote com resultados, avaliação cega, métricas e relatório.

O número N corresponde a 20, 40, 60, 80 ou 100. O arquivo RELATORIO_KLOD_Npct.txt registra o resultado observado. A chave que identifica professor/aluno na avaliação cega não é enviada como artefato.

O artefato da etapa anterior precisa estar disponível no GitHub Actions. A configuração atual retém os artefatos por 30 dias; execute a próxima etapa dentro desse período.

## Limites e segurança

- main não é modificada. As branches de treinamento são encadeadas, começando em development.
- O gatilho por commit funciona em development e training/**, porque o workflow está presente nessas branches.
- Uma T4x2 tem duas GPUs independentes de 16 GB; este pipeline treina em uma GPU e não soma a VRAM.
- Cada etapa reinicia o otimizador, embora preserve os pesos do adaptador anterior.
- A disponibilidade de GPU, a cota Kaggle, os downloads dos modelos e o espaço de armazenamento dependem da conta e do serviço.
- Concluir 100% significa concluir as cinco épocas planejadas. Isso não prova capacidade geral ampla nem que o aluno superou o professor; analise as avaliações cegas antes de qualquer conclusão.
