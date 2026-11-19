# MOBNET Forge 1.20.1 Implementation Plan

> **For agentic workers:** Use this plan task-by-task. Steps use checkbox syntax.

**Goal:** Build a standalone Forge-native mob conversation and behavior mod powered by a local MOBNET action policy.

**Architecture:** Server-authoritative Forge event and command layer; H2 persistence; 12 residual neural blocks of width 678 for action selection; local byte-level BPE tokenizer; deterministic local dialogue; bounded mob goals and saved speech bubbles.

**Tech Stack:** Java 17, Minecraft 1.20.1, Forge 47.4.28, ForgeGradle 6.x, H2 2.2.224 via Jar-in-Jar, JUnit 5, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-11-19-mobnet-forge-1.20.1-design.md`

## Global Constraints

- Target Minecraft 1.20.1 and Forge 47.4.28.
- Compile with Java 17.
- Package one JAR; do not require Connector or Fabric API.
- All world mutations execute on the server thread.
- No external LLM/API dependency.
- Do not copy CreatureChat assets, prompts, branding, or source into this independent implementation.
- Do not claim the initial neural policy is pretrained or that one billion observations are already available.

## Review Focus

- Unknown or malformed action phrases must resolve to TALK/IDLE safely, never an invalid enum.
- Expired or missing player/entity UUID references must stop navigation and restore vanilla behavior.
- An entity's pre-existing custom name and visibility must be restored after a bubble expires.
- Corrupted/incompatible policy files must be rejected without preventing server startup.
- H2 open/close and SQL failures must not crash the server tick or lose the world save.

---

### Task 1: Forge build and release pipeline

**Files:** `build.gradle`, `settings.gradle`, `gradle.properties`, `src/main/resources/META-INF/mods.toml`, GitHub Actions workflow.

- [ ] Add ForgeGradle 6 and Java 17 configuration.
- [ ] Add H2 Jar-in-Jar and JUnit dependencies.
- [ ] Add a push/PR workflow that runs tests and build, then uploads the resulting JAR.
- [ ] Verify the workflow path and artifact glob.

### Task 2: Behavior vocabulary and tokenizer

**Files:** `MobnetAction.java`, `MobnetIntentParser.java`, `MobnetTokenizer.java`, corresponding JUnit tests.

Interfaces:
- `MobnetIntentParser.parse(String) -> MobnetAction`
- `MobnetTokenizer.encode(String) -> List<Integer>`
- `MobnetTokenizer.decode(List<Integer>) -> String`

- [ ] Write failing tests for Portuguese follow/protect/flee/attack intents and unknown phrases.
- [ ] Write a failing UTF-8 tokenizer round-trip test.
- [ ] Implement deterministic intent parsing and byte-level BPE merge training/encoding.
- [ ] Run the tests and verify round-trip fidelity.

### Task 3: Neural policy and state encoder

**Files:** `MobnetNeuralCore.java`, `MobnetStateEncoder.java`, corresponding JUnit tests.

Interfaces:
- `MobnetNeuralCore.chooseAction(float[]) -> MobnetAction`
- `MobnetNeuralCore.learn(float[], MobnetAction, float) -> void`
- `MobnetNeuralCore.save(Path) -> void`
- `MobnetNeuralCore.load(Path) -> boolean`

- [ ] Write failing tests for width validation, intent-feature selection, bounded reward updates, and malformed model rejection.
- [ ] Implement 12 residual bottleneck blocks of width 678, 64-unit bottlenecks, and a trainable action head.
- [ ] Implement finite-value checks and versioned atomic persistence for the policy head.
- [ ] Run the neural tests.

### Task 4: SQL memory and profile store

**Files:** `MobnetMemoryStore.java`, SQL store tests.

Interfaces:
- `open(Path) -> void`
- `getOrCreateProfile(UUID, String, String) -> MobnetProfile`
- `addMemory(UUID, UUID, String, String, List<Integer>) -> void`
- `recentMemories(UUID, UUID, int) -> List<String>`
- `friendship(UUID, UUID) -> int`
- `adjustFriendship(UUID, UUID, int) -> int`
- `recordExperience(UUID, UUID, float[], MobnetAction, float) -> void`

- [ ] Write failing tests for profile creation, relationship isolation by UUID, memory order/retention, and reopen persistence.
- [ ] Implement H2 schema with prepared statements and bounded per-pair memory retention.
- [ ] Run SQL integration tests using a temporary directory.

### Task 5: Conversation, bubbles, and mob goals

**Files:** `MobnetConversationEngine.java`, `MobnetBehaviorGoal.java`, `MobnetRuntime.java`, `MobnetEvents.java`.

- [ ] Implement local Portuguese replies using profile, relationship, and recent context.
- [ ] Implement temporary synchronized name bubbles that preserve and restore original name state.
- [ ] Implement bounded FOLLOW/FLEE/ATTACK/PROTECT/GUIDE/STAY goals using vanilla navigation and target eligibility.
- [ ] Ensure goals attach once per loaded mob and detach from tracking on unload.

### Task 6: Commands, server lifecycle, and integration

**Files:** `MobnetCommands.java`, `MobnetMod.java`, lifecycle/event integration, README.

- [ ] Implement sneak-right-click selection for an empty-handed mob interaction.
- [ ] Implement `/mobnet say`, `gift`, `memory`, `relationship`, `reward`, `stop`, and `help`.
- [ ] Validate distance, dimension, alive state, input length, permissions, and reward range.
- [ ] Open/close H2 on server lifecycle and atomically save the model.
- [ ] Run complete test suite and Forge build; inspect the produced JAR metadata and contents.

### Task 7: Final review and artifact

- [ ] Review all source and generated metadata for common crash paths.
- [ ] Inspect GitHub Actions build/test results.
- [ ] Download and verify the JAR artifact when a successful workflow run is available.
- [ ] Report implemented, tested, and deferred features separately.
