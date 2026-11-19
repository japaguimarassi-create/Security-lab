# MOBNET 0.1.0 — Minecraft 1.20.1 Forge

MOBNET is a standalone Forge-native replacement for the basic CreatureChat gameplay loop. It does not require Fabric, Connector, a remote LLM, or an API key.

## Requirements

- Minecraft Java 1.20.1
- Forge 47.4.28 or newer in the 47.x line
- Java 17

## Build

From this directory:

```bash
gradle clean test build
```

The release JAR is generated in `build/libs/`. H2 is bundled through Forge Jar-in-Jar.

## Use

- Sneak + right-click a mob with an empty hand to select it.
- `/mobnet say <message>` sends a message to the selected mob.
- `/mobnet gift` gives the held item and improves the relationship.
- `/mobnet memory` shows recent shared memories.
- `/mobnet relationship` shows the current friendship score.
- `/mobnet reward <-1..1>` gives the last action a learning reward.
- `/mobnet stop` cancels its current MOBNET behavior.
- `/mobnet help` shows commands.

Dialogue is local and deterministic in this initial release. It is not a pretrained generative LLM and does not claim GPT-quality free-form language. The MOBNET action policy contains 12 residual blocks of width 678 and learns its action head from bounded feedback. The initial backbone is deterministically initialized, not trained on a billion observations.

## Included in this first release

- Server-authoritative mob selection and chat commands.
- Temporary speech bubbles using synchronized entity custom names, with restoration of original names.
- UUID-based friendships and relationship history.
- Per-world SQL memory and experience storage (H2 embedded).
- Byte-level BPE tokenizer with merge training and UTF-8 round-trip.
- MOBNET 12×678 residual action policy.
- Follow, flee, attack, protect, guide, stay, talk, and idle actions.
- Multiplayer chat visibility for nearby players.

## Deliberately deferred

A custom inventory screen, advancement tree, free-form LLM-quality text generation, multi-billion-observation pretrained weights, and full GUI are not represented as available in v0.1.0.

## Reference and licensing

MOBNET is an independent implementation inspired by publicly documented mob-chat gameplay features. It does not include CreatureChat source code or assets. See the repository design document for source/asset licensing notes.
