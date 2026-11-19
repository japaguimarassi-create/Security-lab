# MOBNET CreatureChat Bridge 0.3.0 — Minecraft 1.20.1 Forge

MOBNET is an add-on provider bridge for the original CreatureChat. CreatureChat remains responsible for its own chat screen, character sheets, conversation history, friendship system, behavior tags and in-game presentation. MOBNET supplies an OpenAI-compatible local endpoint and forwards dialogue requests to the configured MOBNET inference service.

## Requirements

- Minecraft Java 1.20.1
- Minecraft Forge 47.x
- Java 17
- The original CreatureChat 1.20.1 build, loaded on Forge through the compatible Sinytra Connector setup (including the required Forgified Fabric API)
- A running MOBNET language-inference API that implements OpenAI Chat Completions

## Install

1. Install Forge 1.20.1 and the compatible Connector/Forgified Fabric API setup required by CreatureChat.
2. Install the original CreatureChat 1.20.1 mod.
3. Put `mobnet-0.3.0.jar` in the same `mods` folder.
4. Start the world once so Forge creates `config/mobnet-common.toml`.
5. Configure the upstream MOBNET inference endpoint as described below.
6. Run `/mobnet Key active true` as an operator.

MOBNET does not replace or reimplement CreatureChat's user interface or gameplay. It only changes the API provider configuration used by CreatureChat.

## Configure the trained MOBNET model endpoint

Open `config/mobnet-common.toml` and configure:

```toml
[conversation]
apiUrl = "https://YOUR-MOBNET-HOST/v1/chat/completions"
apiKey = ""
model = "mobnet"
timeoutSeconds = 30
maxOutputTokens = 180
localApiPort = 18765
```

- `apiUrl` must point to the actual running MOBNET text-generation service and must include the full `/v1/chat/completions` path.
- `apiKey` is only the credential for that upstream inference service. Leave it empty if the service does not require authentication.
- `model` is the model identifier accepted by that service.
- HTTPS is required for remote endpoints. Plain HTTP is accepted only for loopback endpoints.
- `localApiPort` is the port used by the local CreatureChat bridge. It binds only to `127.0.0.1`.

The generated local CreatureChat key is separate from the upstream API key. It is generated with a cryptographically secure random generator, saved in the active world's `mobnet/creaturechat-bridge.json`, and sent only over loopback between the Minecraft server and its own local bridge. It is not sent to the remote inference service.

## Commands

```text
/mobnet Key active true
/mobnet Key active false
/mobnet Key status
```

The lowercase alias is also accepted:

```text
/mobnet key active true
```

When activated, MOBNET:

1. Generates a random 256-bit bridge key.
2. Starts an OpenAI-compatible endpoint at `http://127.0.0.1:18765/v1/chat/completions`.
3. Saves the previous `apiKey`, `url`, `model` and `timeout` values from CreatureChat's JSON configuration.
4. Sets CreatureChat's API URL to the local MOBNET endpoint, sets the generated bearer key and selects model `mobnet`.
5. Forwards CreatureChat's system prompt and recent player/mob messages to the configured upstream MOBNET inference endpoint.
6. Returns the generated answer in the response schema that CreatureChat already understands.

Deactivation restores the previous CreatureChat settings and stops the local HTTP server. The active state and generated key persist across world/server restarts.

## Response contract

The upstream model must return OpenAI-compatible JSON containing:

```json
{
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": "A natural mob reply, optionally followed by CreatureChat behavior markers."
      }
    }
  ]
}
```

CreatureChat interprets behavior markers in the returned text, including `<FOLLOW>`, `<UNFOLLOW>`, `<LEAD>`, `<UNLEAD>`, `<FLEE>`, `<UNFLEE>`, `<ATTACK>`, `<PROTECT>`, `<UNPROTECT>` and `<FRIENDSHIP -3..3>`. The upstream model should preserve these markers exactly when a behavior is requested.

## Important model limitation

The MOBNET neural core currently included in this repository is an action-classification policy, not a trained autoregressive language model. Its residual backbone is deterministically initialized and its feedback mechanism updates an action head; it does not generate free-form Portuguese dialogue. The bridge therefore requires the actual trained MOBNET language model to be available through the configured `apiUrl`. The random key activates and authenticates the local bridge; it does not create or train model weights.

Compilation and unit tests do not replace in-game testing with the exact CreatureChat, Connector and Forge versions being used.

## Source and licensing

MOBNET is licensed under GPL-3.0-or-later. See `LICENSE` and `NOTICE.md` for attribution and scope. CreatureChat's original assets and trademark are not bundled by this add-on.
