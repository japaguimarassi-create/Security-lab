# KLOD 0.6 architecture

- **General assistant:** open-domain system prompt and general fallback.
- **Domain router:** deterministic, conservative routing; ambiguous and unfamiliar requests remain general.
- **Optional specialists:** programming, science, mathematics, research, writing, education, creative work, business and Minecraft.
- **Teacher:** frozen Qwen3-1.7B instruct checkpoint generates demonstrations with recorded model/config provenance.
- **Student:** Qwen3-1.7B-Base receives supervised QLoRA fine-tuning from reviewed demonstrations; its adapter is stored separately.
- **Teacher data gate:** automated format/repetition checks followed by explicit human approval before distillation SFT.
- **Inference:** shared language-model runtime with optional PEFT adapter.
- **Embeddings:** multilingual E5, loaded lazily and locally.
- **Memory:** namespace-isolated SQLite records with optional semantic recall.
- **Knowledge:** source-attributed documents, overlapping passages, FTS5 and vector similarity.
- **Rank fusion:** reciprocal-rank fusion combines lexical and semantic candidates.
- **Planner:** JSON proposals checked against caller allowlists; no action is executed by the API.
- **API:** authenticated REST endpoints; callers can inspect or override domain routing.
- **Training:** continued pretraining, teacher-student SFT, DPO and held-out evaluation.

All specialists share the same active language model. The teacher is frozen during data generation; the student receives gradients only during the SFT training run. The routing utility is not a separate neural model.

The 48-row curriculum is a starter experiment, not a broad capability dataset. SQLite's brute-force vector scan is suitable for small and medium collections; use a vector database for very large indexes.


## GPU Mesh Core 0.7

- **Resource registry:** stores authorized worker nodes, owner identity, heartbeat, CPU/RAM availability and each physical GPU's own VRAM.
- **Worker identity:** node-scoped random token with only SHA-256 hash persisted; heartbeat does not depend on the account session after enrollment.
- **Scheduler:** plans independent tasks and selects an individual device only when its VRAM threshold is satisfied.
- **Quota ledger:** atomic SQLite reservations per account and UTC week; cancellation releases planning reservations.
- **Account security:** Argon2id password hashes, random opaque bearer sessions and database-backed login/registration throttles.
- **Source vault:** canonical general-relativity corpus is a mandatory Argon2id derivation input; AES-256-GCM authenticates and encrypts exported bundles.
- **Web control plane:** packaged self-hosted dashboard at `/mesh`, strict content security policy and no-store responses.

The first GPU Mesh milestone intentionally stops at inventory and allocation planning. Workers do not execute arbitrary remote commands, and an allocation plan is not a virtual machine. A later execution runtime must introduce signed job artifacts, isolated containers, resource cgroups, restricted networking, short-lived capabilities, cancellation, and output verification.
