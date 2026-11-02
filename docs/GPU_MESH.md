# GPU Mesh Core 0.8

## Objetivo e estado

GPU Mesh é o plano de controle do KLOD para inventariar hardware autorizado, executar workloads internos permitidos, acompanhar resultados e cotas semanais e redistribuir tarefas pendentes quando novos workers entram na rede.

O runtime de execução já existe. Ele envia tarefas para workers registrados, reserva CPU/RAM/VRAM por dispositivo, usa manifesto HMAC e lease temporário, acompanha execução, coleta resultado e oferece cancelamento cooperativo. Ainda não é uma plataforma de contêineres genéricos nem um serviço de VMs.

## Branches e histórico

- `main`: integração estável do KLOD e GPU Mesh.
- `development`: linha de desenvolvimento do KLOD preservada.
- `gpu-mesh/core`: integração base do GPU Mesh.
- `gpu-mesh/relativity-math`: corpus matemático canônico da relatividade geral.
- `gpu-mesh/crypto`: derivação Argon2id, AES-256-GCM e pacotes criptografados.
- `gpu-mesh/resources`: inventário, autenticação de workers e scheduler.
- `gpu-mesh/quotas-auth`: contas, sessões e cotas.
- `gpu-mesh/site-api-integration`: painel, API e integração do produto.
- `gpu-mesh/execution-runtime`: execução distribuída e adaptadores de provedores.

As branches de Kodex, Enturma, Stevebo, Voxelforge e as etapas antigas de treinamento foram preservadas como históricos de projetos independentes.

## Arquitetura funcional

- Contas com senha Argon2id, sessões bearer aleatórias e revogáveis e limitação de tentativas persistida.
- Workers com token aleatório exclusivo por nó; o banco guarda apenas o hash SHA-256 do token.
- Heartbeat separado da sessão da conta, para o worker não precisar de login contínuo.
- Inventário de CPU, RAM e GPUs físicas individualizadas.
- VRAM nunca é somada entre placas diferentes.
- Limites por GPU incluem VRAM disponível e duração máxima por tarefa (`max_task_seconds`).
- Tarefas não alocadas são persistidas e podem ser redistribuídas pelo endpoint de reequilíbrio.
- Reservas de hardware e cotas são feitas antes da entrega ao worker; uma falha na reserva faz rollback.
- Manifests são assinados com HMAC-SHA256 usando o segredo individual do worker.
- Leases temporários reduzem duplicação; um token antigo deixa de funcionar quando um lease novo é emitido.
- Resultados CPU SHA-256 são recalculados pelo servidor; resultados CUDA continuam identificados como relatório do worker.

## Workloads executáveis

O endpoint `POST /v1/mesh/jobs` aceita somente estes workloads:

| Workload | Processamento | Payload principal | Validação |
|---|---|---|---|
| `cpu-sha256` | CPU | texto e iterações | Digest recalculado no servidor |
| `gpu-matmul` | CUDA | tamanho de matriz e semente | Digest informado pelo worker |
| `gpu-mandelbrot` | CUDA | largura, altura e iterações | Digest informado pelo worker |

Os limites de payload, dimensão, memória e tempo são validados antes da alocação. Não existe endpoint para enviar Python, shell, scripts ou comandos arbitrários.

### Processo de execução

1. O scheduler escolhe workers online e, para workloads GPU, uma GPU física com VRAM suficiente e duração suportada.
2. A API reserva CPU, RAM, VRAM e cota semanal em transações.
3. A fila entrega uma tarefa ao worker, que recebe um manifesto assinado e um lease secreto temporário.
4. O worker valida a assinatura e inicia a tarefa em processo filho separado.
5. O processo filho recebe limites de CPU, tamanho de arquivo, quantidade de descritores e tempo no Linux quando o sistema operacional oferece esses limites.
6. O worker mantém heartbeat e renova lease/reserva durante a tarefa.
7. A API valida o resultado, marca estado e libera a reserva física no encerramento.
8. Tarefas pendentes sem capacidade podem ser reequilibradas quando outro worker fica online.

**Limite de isolamento:** o processo filho e a allowlist reduzem a superfície de execução, mas não substituem um container rootless, seccomp, cgroups ou microVM. Não aceite código de terceiros como workload, não execute workers com privilégios administrativos e mantenha o servidor atrás de HTTPS. Não há atestado criptográfico de GPU remota; resultados CUDA são informados pelo worker.

## Adaptadores de provedores

### Worker próprio

É a opção mais direta. O usuário instala `klod-ai[worker]` em uma máquina que controla, autentica uma vez e o agente anuncia recursos via heartbeat.

### Kaggle Notebooks

O adaptador usa o CLI oficial para enviar kernels privados, selecionar acelerador, consultar status e baixar outputs. O notebook é por tarefa, não um worker persistente. O usuário precisa de uma conta Kaggle, `KAGGLE_USERNAME` e `KAGGLE_API_TOKEN`; disponibilidade, aceleradores e limites permanecem controlados pelo Kaggle.

Instalação e execução:

```bash
pip install -e ".[kaggle]"
export GPU_MESH_API_URL="https://SEU-DOMINIO"
export GPU_MESH_ACCESS_TOKEN="TOKEN_DA_CONTA_GPU_MESH"
export KAGGLE_USERNAME="SEU_USUARIO"
export KAGGLE_API_TOKEN="TOKEN_KAGGLE"
export GPU_MESH_KAGGLE_ACCELERATOR="NvidiaTeslaT4"
export GPU_MESH_KAGGLE_GPU_COUNT="1"
export GPU_MESH_KAGGLE_GPU_VRAM_GIB="16"
export GPU_MESH_KAGGLE_GPU_COUNT="2"
export GPU_MESH_SHARE="true"
gpu-mesh-kaggle-worker
```

CPU, RAM, quantidade de GPUs, VRAM e duração máxima são declarações locais de capacidade. Configure esses números de acordo com o acelerador que sua conta realmente pode usar. O adaptador não concede acesso a GPUs bloqueadas por competição ou restrição de conta.

O adapter cria kernels privados com código fixo gerado a partir de `workloads.py`; o token do worker e o lease não são enviados no código do kernel. O kernel privado é removido depois do download por padrão. Defina `GPU_MESH_KAGGLE_KEEP_KERNELS=true` para preservar o histórico.

### Hugging Face ZeroGPU

O projeto inclui uma aplicação Gradio em `examples/huggingface_zerogpu`. Publique essa pasta como um Space próprio; o bridge local chama os endpoints Gradio, verifica a cota ZeroGPU e devolve o resultado ao Mesh.

Instalação e execução do bridge:

```bash
pip install -e ".[huggingface]"
export GPU_MESH_API_URL="https://SEU-DOMINIO"
export GPU_MESH_ACCESS_TOKEN="TOKEN_DA_CONTA_GPU_MESH"
export HF_TOKEN="TOKEN_HUGGING_FACE"
export GPU_MESH_HF_SPACE_ID="usuario/nome-do-space"
export GPU_MESH_HF_ZEROGPU_SIZE="large"
export GPU_MESH_SHARE="true"
gpu-mesh-hf-worker
```

O perfil `large` anuncia 48 GiB e `xlarge` 96 GiB; a duração máxima de uma tarefa é configurada por `GPU_MESH_HF_MAX_TASK_SECONDS` (1–120 segundos). O scheduler não envia uma tarefa que exceda a duração cadastrada para aquela GPU. A quota ZeroGPU é por conta Hugging Face e é consultada pelo bridge antes do pedido; o token precisa da permissão de leitura de uso/faturamento. Quota gratuita não equivale a capacidade contínua ou garantida.

### Google Colab

O notebook `examples/colab/GPU_Mesh_Worker.ipynb` conecta manualmente a sessão Colab atual ao Mesh. Selecione GPU nas configurações do Colab, execute as células, informe a URL e o token da conta e deixe o agente ativo.

Esse caminho é interativo e efêmero: quando a sessão Colab termina, o worker fica offline. O projeto não cria runtimes Colab por OAuth automaticamente nesta versão. Não trate o notebook gratuito como VM persistente.

## Cotas semanais internas

| Métrica | Limite inicial |
|---|---:|
| GPU | 1.800 segundos |
| VRAM | 7.200 GiB·segundos |
| CPU | 36.000 core·segundos |
| RAM | 43.200 GiB·segundos |
| Armazenamento | 1.680 GiB·horas |
| Banda | 2 GiB |

Os limites são configuráveis e pertencem ao GPU Mesh. Não são a quota de Kaggle, Hugging Face, Colab ou outro provedor. O consumo externo é controlado separadamente por cada fornecedor.

## Relatividade geral como componente da chave criptográfica

O módulo `src/klod/mesh/relativity.py` contém o corpus matemático canônico `GR-CANONICAL-CORE-1.0.0`, com convenções de sinal e unidades explícitas. Ele abrange:

1. variedade espaço-temporal, métrica lorentziana e volume;
2. conexão de Levi-Civita, símbolos de Christoffel e derivadas covariantes;
3. tensores de Riemann, Ricci, Weyl e Einstein;
4. identidades de Bianchi e conservação covariante;
5. equações de Einstein, forma com traço reverso e ação Einstein–Hilbert;
6. termo de fronteira Gibbons–Hawking–York;
7. fluido perfeito, campo escalar e eletromagnetismo;
8. geodésicas, desvio geodésico, Raychaudhuri e marés;
9. gravitação linearizada, limite newtoniano e quadrupolo;
10. soluções Schwarzschild, Kerr e Reissner–Nordström;
11. FLRW, Friedmann e conservação cosmológica;
12. formulação ADM 3+1, restrições Hamiltoniana e de momento;
13. equilíbrio Tolman–Oppenheimer–Volkoff;
14. constante cosmológica, simetrias de Killing e quantidades conservadas.

Os bytes normalizados em UTF-8/NFC entram como componente obrigatório da derivação Argon2id; o fingerprint SHA-256 do corpus também é autenticado no pacote. Uma mudança no corpus impede a abertura de um pacote antigo sem migração explícita.

**A teoria publicada não é uma senha secreta.** Por isso a derivação também exige `GPU_MESH_MASTER_SECRET`, segredo aleatório privado de pelo menos 32 bytes. Argon2id (64 MiB, três iterações, paralelismo dois) deriva 32 bytes usados no AES-256-GCM, com salt de 16 bytes e nonce de 12 bytes.

O cofre cifra pacotes exportados; não cifra os blobs nem o histórico Git automaticamente. Este repositório continua público. Para ocultar o código no GitHub, a visibilidade do repositório deve ser alterada para privada separadamente.

## Empacotar e restaurar código

```bash
export GPU_MESH_MASTER_SECRET='SEGREDO_ALEATORIO_PRIVADO_COM_32_BYTES_OU_MAIS'
gpu-mesh-vault seal --source . --output ./dist/gpu-mesh-source.grmesh
gpu-mesh-vault open --input ./dist/gpu-mesh-source.grmesh --destination ./restored-source
```

O pacote exclui `.git`, `.env`, credenciais, bancos locais, modelos, pesos e outputs. A extração rejeita caminhos absolutos, traversal e entradas especiais. O original não é apagado nem modificado.

## Rotas principais

Todas as rotas abaixo usam prefixo `/v1/mesh`, exceto `/mesh`.

- `GET /providers`
- `POST /auth/register`, `POST /auth/login`, `POST /auth/logout`
- `GET /account`, `GET /quota`
- `POST /workers`, `GET /workers`, `DELETE /workers/{node_id}`
- `POST /workers/{node_id}/heartbeat`
- `GET /resources`
- `POST /jobs`, `GET /jobs`, `GET /jobs/{job_id}`
- `POST /jobs/{job_id}/reschedule`
- `DELETE /jobs/{job_id}` (cancelamento cooperativo)
- `GET /jobs/{job_id}/results`
- `POST /workers/{node_id}/tasks/claim`
- `POST /workers/{node_id}/tasks/{task_id}/start`
- `POST /workers/{node_id}/tasks/{task_id}/renew`
- `POST /workers/{node_id}/tasks/{task_id}/complete`
- `POST /workers/{node_id}/tasks/{task_id}/fail`

## Configuração segura de produção

- HTTPS obrigatório para API e workers.
- `KLOD_API_KEY` deve ser um segredo aleatório antes de expor rotas legadas.
- Guarde `GPU_MESH_MASTER_SECRET`, `KAGGLE_API_TOKEN` e `HF_TOKEN` fora do GitHub.
- O token HF deve ter apenas as permissões necessárias; leitura de quota ZeroGPU exige permissão de uso/faturamento.
- Use banco SQLite persistente, backup protegido e reverse proxy com rate limits.
- Compartilhamento de capacidade começa desligado; o dono precisa definir explicitamente `GPU_MESH_SHARE=true`.
- Cada recurso de provedor deve ser declarado pelo dono da conta e permanece sujeito a quotas e políticas externas.
