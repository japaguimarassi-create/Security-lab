# MOBNET Forge 1.20.1 — Design

## Intent

Create a standalone Forge-native Minecraft 1.20.1 mod that replaces the user-facing gameplay loop of CreatureChat while adding the MOBNET neural action policy, per-mob memory, relationships, local dialogue, behavior control, and a SQL persistence layer.

## Goals

- Let a player select any ordinary Mob by sneaking and right-clicking it with an empty hand.
- Provide a server-authoritative conversation command, `/mobnet say <message>`.
- Display replies in nearby players' chat and temporarily above the mob as a synchronized custom-name bubble.
- Persist per-mob profiles, per-player UUID relationships, conversation memories, and learning experiences in an embedded SQL database inside the world save.
- Provide local neural policy selection with exactly 12 residual blocks and width 678, plus action feedback updates.
- Support FOLLOW, FLEE, ATTACK, PROTECT, GUIDE, STAY, TALK, and IDLE.
- Add gift, relationship, memory, reward, stop, and help commands.
- Work without external AI APIs, Connector, Fabric Loader, or Fabric API.

## Non-goals for this first release

- Claiming a trained generative LLM or human-level dialogue.
- Claiming that one billion observations already exist.
- Runtime training of the complete neural backbone on the Minecraft server thread.
- Replacing vanilla physics, navigation, combat rules, or entity goals wholesale.
- Copying CreatureChat source code, prompts, images, sounds, textures, or trademarks.

## Architecture

The mod is a single Forge 1.20.1 mod. A small residual neural policy network (12 blocks, width 678, bottleneck 64) chooses among valid high-level actions from a 678-value state vector. A local intent encoder provides language/context features; procedural analyzers add world features but never execute actions. A separate local conversation layer produces deterministic Portuguese dialogue and uses SQL-backed history. This v0.1 policy is not a pretrained language model.

H2 is packaged using Forge Jar-in-Jar so the user receives one mod JAR. The server owns all profile, memory, relationship, neural-feedback, and behavior state. Player interaction and commands are validated on the server. Temporary speech text is synchronized through vanilla entity custom-name data and restored after its timer expires.

## Data

- `mob_profiles`: entity UUID, registry type, display name, personality.
- `relationships`: mob UUID + player UUID, friendship and interaction count.
- `memories`: speaker, message, timestamp, tokenizer IDs.
- `experiences`: encoded state vector, selected action, reward, timestamp.
- Model policy head: versioned binary file inside the world save, atomically replaced.

## Safety and stability

- Never execute neural or database work from a client-side world.
- Keep all entity/world mutations on the logical server thread.
- Validate selected mob existence, dimension, liveness, distance, input length, action validity, and reward bounds.
- Reuse vanilla navigation and attack eligibility.
- Expire behaviors and speech bubbles; restore original custom names.
- Bound retained dialogue memory and command input.
- Fall back to vanilla goals if MOBNET has no valid command.
- Close SQL resources and save policy weights at server shutdown.

## Prior-art feature mapping

The supplied CreatureChat JAR documents conversations, personality/character sheets, follow/flee/attack/protect/lead behaviors, friendship, reactions, mob inventories, advancements, and multiplayer synchronization. This project reimplements selected features independently. The first release includes conversation, memories, relationships, behavior actions, gifts, bubbles, and multiplayer chat visibility. A generic GUI inventory and advancement system are deferred rather than faked.

## Licensing

CreatureChat identifies its code as GPL-3.0 and its non-code assets as CC-BY-NC-SA-4.0. This implementation is written independently and does not vendor the reference JAR, source, prompts, assets, or branding. Any future incorporation of GPL source must preserve GPL obligations; non-code assets require separate permission/license compliance.

## Acceptance criteria

- ForgeGradle builds a single `mobnet-0.1.0-forge-1.20.1.jar` with H2 embedded.
- Unit tests verify intent parsing, byte-BPE round-trip, neural action selection/feedback, and SQL persistence.
- The mod loads on Forge 1.20.1 / Java 17 and exposes the documented commands.
- No external API key, Fabric API, or Connector is required.
- Limitations of the local dialogue and untrained initial policy are documented.
