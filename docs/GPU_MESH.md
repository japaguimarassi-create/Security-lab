# GPU Mesh Core 0.7

## Objetivo

GPU Mesh é o plano de controle para inventariar hardware autorizado, acompanhar cotas semanais e criar planos de distribuição de tarefas independentes. Ele foi integrado à base KLOD 0.6.0 e elevado para o pacote 0.7.0.

## Arquitetura de branches

- `main`: versão estável publicada.
- `development`: linha de desenvolvimento preexistente do KLOD.
- `gpu-mesh/core`: integração que parte da linha completa `development`.
- `gpu-mesh/relativity-math`: corpus matemático canônico da relatividade geral.
- `gpu-mesh/crypto`: derivação Argon2id, AES-256-GCM e empacotamento criptografado.
- `gpu-mesh/resources`: registro de workers, inventário de hardware e escalonador.
- `gpu-mesh/quotas-auth`: contas, sessões e cotas semanais.
- `gpu-mesh/site-api-integration`: API HTTP, painel web, agente e integração final.

As branches históricas de Kodex, Enturma, Stevebo, Voxelforge e etapas de treinamento são independentes. Permanecem intactas; não foram transferidas para repositórios sem destino confirmado. A integração não reescreve nem apaga esses históricos.

## Estado funcional

- API de conta: registro, login, logout e sessão bearer opaca.
- Senhas: Argon2id com 64 MiB, três iterações e paralelismo dois.
- Sessões: token aleatório de alta entropia; somente o hash SHA-256 é persistido.
- Workers: registro autenticado e opt-in explícito de compartilhamento.
- Heartbeat: token aleatório individual por nó, armazenado como hash; não depende da sessão de conta depois do registro.
- Inventário: CPU, RAM e cada GPU/VRAM individualmente.
- Escalonador: aloca tarefas independentes somente em dispositivos que atendem à VRAM mínima individual.
- Cotas: reservas atômicas por usuário, com semana UTC iniciada na segunda-feira.
- Painel: inventário, cotas, workers e histórico de planos.
- Provedores: catálogo de capacidades e estados de integração; somente o worker voluntário próprio está integrado nesta fase.

### Limite deliberado da primeira versão

O sistema registra hardware e produz planos de alocação. Ele ainda **não inicia código remoto** nos workers. O protocolo de execução precisa de identidade do artefato, assinatura, sandbox, limites de CPU/RAM/VRAM, rede restrita, política de arquivos, timeout, cancelamento, logs auditáveis e verificação de saída. A API retorna explicitamente `execution_status=planning_only`; não deve ser interpretada como VM ou GPU já provisionada.

Colab permanece somente como ambiente interativo. Sessões gratuitas de notebook não são tratadas como workers persistentes ou como uma API de execução distribuída. Kaggle e ZeroGPU aparecem como adaptadores futuros, sujeitos às interfaces, cotas e termos de cada provedor.

## Política de recursos

A VRAM não é somada entre placas. Duas GPUs de 8 GiB continuam sendo dois dispositivos de 8 GiB; uma tarefa que exige 12 GiB numa única placa não será alocada nessas GPUs. O escalonador pode distribuir quadros de renderização, lotes e avaliações independentes, desde que cada tarefa caiba em um dispositivo.

Cotas semanais padrão:

| Métrica | Limite inicial |
|---|---:|
| GPU | 1.800 segundos |
| VRAM | 7.200 GiB·segundos |
| CPU | 36.000 core·segundos |
| RAM | 43.200 GiB·segundos |
| Armazenamento | 1.680 GiB·horas |
| Banda | 2 GiB |

Esses valores são limites internos iniciais configuráveis, não promessas de capacidade grátis dos provedores. Os limites externos permanecem separados e podem mudar.

## Relatividade geral como componente obrigatório da chave

O módulo `src/klod/mesh/relativity.py` contém uma representação canônica versionada, `GR-CANONICAL-CORE-1.0.0`. O corpus registra convenções de sinal e unidades e inclui:

1. variedade espaço-temporal, métrica lorentziana e elemento de volume;
2. conexão de Levi-Civita, símbolos de Christoffel e derivadas covariantes;
3. tensores de Riemann, Ricci e Einstein, identidades de Bianchi;
4. equações de campo de Einstein, traço reverso e ação de Einstein–Hilbert;
5. matéria perfeita, campo escalar e eletromagnetismo;
6. geodésicas, desvio geodésico e aceleração de maré;
7. gravitação linearizada, limite newtoniano e quadrupolo;
8. soluções de Schwarzschild, Kerr e Reissner–Nordström;
9. métrica FLRW e equações de Friedmann;
10. decomposição ADM 3+1 e restrições hamiltoniana e de momento;
11. equilíbrio TOV;
12. constante cosmológica, simetrias de Killing e conservação.

O corpus completo é normalizado em UTF-8/NFC e recebe SHA-256. Seus bytes entram como componente obrigatório da entrada Argon2id e seu fingerprint integra os dados autenticados (AAD) do pacote. Uma versão diferente do corpus impede a abertura do pacote, salvo migração explícita com a chave original.

**O corpus público de fórmulas não é segredo.** Uma teoria conhecida não pode funcionar sozinha como senha resistente. Por isso a chave usa também `GPU_MESH_MASTER_SECRET`, um segredo aleatório privado com no mínimo 32 bytes. Argon2id (64 MiB, três iterações, paralelismo dois) deriva 32 bytes; AES-256-GCM cifra e autentica o pacote com salt aleatório de 16 bytes e nonce aleatório de 12 bytes.

O arquivo fonte no repositório GitHub continua em texto claro enquanto o repositório estiver público. O módulo cifra um pacote de distribuição exportado; ele não transforma retroativamente os blobs nem o histórico Git em ciphertext. Para manter o código do próprio repositório inacessível ao público, a visibilidade do repositório precisa ser privada e o acesso deve ser controlado separadamente.

## Configuração de secrets

Configure `GPU_MESH_MASTER_SECRET` em um cofre de secrets do ambiente de deploy e, para o workflow de pacote, como GitHub Actions repository secret com esse nome. Gere um valor aleatório localmente e guarde uma cópia segura fora do repositório. Nunca o escreva em `.env.example`, código, issue, commit ou log.

Para criar um pacote:
```bash
export GPU_MESH_MASTER_SECRET='SEU_SEGREDO_ALEATORIO_DE_32_BYTES_OU_MAIS'
gpu-mesh-vault seal --source . --output ./gpu-mesh-source.grmesh
```

Para restaurar:
```bash
export GPU_MESH_MASTER_SECRET='O_MESMO_SEGREDO_PRIVADO'
gpu-mesh-vault open --input ./gpu-mesh-source.grmesh --destination ./restored-source
```

O empacotador exclui segredos `.env`, repositório `.git`, bancos locais, modelos e pesos, outputs e caches. Não apaga nada da pasta original. A extração rejeita caminhos absolutos, traversal e entradas especiais.

## Worker voluntário

Instale o projeto com o extra de worker, defina a URL HTTPS e o token temporário obtido ao entrar na conta. Para compartilhar capacidade, defina explicitamente `GPU_MESH_SHARE=true`. O agente guarda o token dedicado do nó em arquivo local com permissão restrita e, depois do primeiro registro, envia heartbeats somente com esse token.

O agente atual anuncia CPU, RAM e GPUs CUDA detectáveis. Ele não executa tarefas nem recebe código remoto. Storage permanece indisponível nesta fase.

## Execução e segurança de produção

- Sirva a API somente atrás de HTTPS.
- Configure `KLOD_API_KEY` com um valor aleatório quando usar as rotas legadas da API KLOD.
- Mantenha `GPU_MESH_MASTER_SECRET` apenas em secrets de deploy.
- Use volumes persistentes e backups protegidos para o SQLite.
- Limite tentativas de login e registro no reverse proxy; use limites de requisição por IP e por conta.
- Nunca disponibilize workers de terceiros sem consentimento verificável.
- Não use o painel ou o plano de alocação como prova de que um trabalho foi executado.

## Rotas principais

Todas as rotas usam o prefixo `/v1/mesh`, exceto o painel `/mesh`.

- `GET /providers`
- `POST /auth/register`, `POST /auth/login`, `POST /auth/logout`
- `GET /account`, `GET /quota`
- `POST /workers`, `GET /workers`, `DELETE /workers/{node_id}`
- `POST /workers/{node_id}/heartbeat` (token individual no cabeçalho `X-Worker-Token`)
- `GET /resources`
- `POST /jobs`, `GET /jobs`, `GET /jobs/{job_id}`
