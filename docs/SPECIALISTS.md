# KLOD domain modules

KLOD is a general-purpose multilingual assistant. The general module handles open-domain and unfamiliar requests. The domain modules are optional helpers, not restrictions on what KLOD can discuss.

Available modules: general, programming, science, mathematics, research, writing, education, creative, business and minecraft.

The default chat route uses conservative automatic domain selection. Clear subject signals can select an optional module; vague, mixed or unfamiliar requests remain general. Set auto_route=false to force general mode, or set specialist to a module ID for explicit selection. POST /v1/route lets clients inspect the router decision.

All modules share one foundation language model. They are prompt and retrieval configurations, not separately trained model weights. Minecraft is a single optional domain among the available modules.
