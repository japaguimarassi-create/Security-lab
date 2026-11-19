# MOBNET 0.2.0 — Minecraft 1.20.1 Forge

MOBNET is a Forge-native mob conversation and behavior mod with a local neural action policy. It reimplements selected conversational gameplay patterns from CreatureChat and adds MOBNET memory and action selection. It does not require Fabric, Connector, or Fabric API.

## Requirements

- Minecraft Java 1.20.1
- Forge 47.4.28 (47.x)
- Java 17

## Install

Place `mobnet-0.2.0.jar` in the instance's `mods` folder and launch Forge 1.20.1. H2 is bundled inside the mod JAR using Forge Jar-in-Jar.

## Talk to a mob

1. Hold an empty hand.
2. Sneak and right-click a mob.
3. The MOBNET chat window opens. Type a message and press Enter or click **Enviar**.
4. The conversation is stored per mob UUID and player UUID. Nearby players can see the mob's speech bubble.

The first interaction creates a character sheet (name, personality, tone, class, skills, likes, dislikes, alignment, background and greeting). Without a configured dialogue provider, the sheet and dialogue use local Portuguese fallbacks.

## Optional natural-language provider

By default MOBNET is fully offline. To enable free-form dialogue, configure the server's `config/mobnet-common.toml`:

```toml
[conversation]
apiUrl = "https://YOUR_OPENAI_COMPATIBLE_ENDPOINT/v1/chat/completions"
apiKey = "YOUR_KEY"
model = "YOUR_MODEL"
timeoutSeconds = 30
maxOutputTokens = 180
```

The endpoint must use HTTPS. Plain HTTP is accepted only for loopback endpoints such as localhost, 127.0.0.1 or ::1. The provider is used only for character-sheet/dialogue text. It never executes actions: the response is parsed for recognized behavior markers, and the MOBNET policy plus action validation decides what the mob may do. If a request fails, a bounded local response is used.

Do not commit `mobnet-common.toml` or share API keys. The key is sent only in the Authorization header to the endpoint configured by the server owner.

## Commands

- `/mobnet say <message>` — chat with the selected mob.
- `/mobnet gift` — offer the item in your hand and increase friendship.
- `/mobnet memory` — show recent memories.
- `/mobnet relationship` — show friendship (-3 to +3).
- `/mobnet reward <-1..1>` — give feedback on the last neural decision.
- `/mobnet stop` — stop the current MOBNET behavior.
- `/mobnet help` — show help.

## Included systems

- CreatureChat-style character sheets, per-player conversation history, chat window and synchronized speech bubbles.
- Behavior marker parser for FOLLOW, UNFOLLOW, LEAD, UNLEAD, FLEE, UNFLEE, ATTACK, PROTECT, UNPROTECT and FRIENDSHIP.
- Friendship on the original -3 to +3 scale.
- UUID-based profiles, relationships and memories in per-world H2 storage.
- Byte-level BPE tokenizer.
- MOBNET 12 residual blocks × 678 width and a feedback-adjustable action head.
- Follow, flee, attack, protect, guide and stay behavior execution with server-side validation.
- Optional OpenAI-compatible dialogue provider; no provider is required.

## Important limitations of 0.2.0

- The initial neural backbone is deterministically initialized and has not been pretrained on a billion observations. The feedback-adjustable action head is not a pretrained language model.
- Local fallback dialogue is rule-based and deliberately concise; natural free-form dialogue requires a configured compatible provider.
- The chat interface and speech bubbles are independent MOBNET artwork/code, not a pixel-identical copy of CreatureChat.
- A dedicated mob inventory screen, full advancement set, click-to-page bubble navigation, voice input and the full set of CreatureChat reactions are not yet included.
- Compilation and unit tests do not replace in-game client, dedicated-server and multiplayer testing.

## Source and licensing

MOBNET is licensed under GPL-3.0-or-later because it incorporates an adapted behavior-marker parser from CreatureChat. See `LICENSE` and `NOTICE.md` for attribution and scope. CreatureChat's non-code assets, prompts, UI artwork, icons, textures, sounds and trademark are not included; MOBNET's presentation and prompts are independently authored.
