package io.github.japaguimarassi.mobnet;

import net.minecraftforge.common.ForgeConfigSpec;

public final class MobnetConfig {
    private static final ForgeConfigSpec.Builder BUILDER = new ForgeConfigSpec.Builder();

    public static final ForgeConfigSpec.ConfigValue<String> API_URL;
    public static final ForgeConfigSpec.ConfigValue<String> API_KEY;
    public static final ForgeConfigSpec.ConfigValue<String> MODEL;
    public static final ForgeConfigSpec.IntValue TIMEOUT_SECONDS;
    public static final ForgeConfigSpec.IntValue MAX_OUTPUT_TOKENS;
    public static final ForgeConfigSpec.IntValue LOCAL_API_PORT;
    public static final ForgeConfigSpec SPEC;

    static {
        BUILDER.push("conversation");
        API_URL = BUILDER.comment("Trained MOBNET OpenAI-compatible inference endpoint. Use the full /v1/chat/completions URL.")
                .define("apiUrl", "");
        API_KEY = BUILDER.comment("Optional credential required by the upstream MOBNET inference endpoint. Never commit this value.")
                .define("apiKey", "");
        MODEL = BUILDER.comment("Model identifier accepted by the upstream MOBNET inference endpoint.")
                .define("model", "mobnet");
        TIMEOUT_SECONDS = BUILDER.comment("Maximum time for one upstream inference request.")
                .defineInRange("timeoutSeconds", 30, 5, 120);
        MAX_OUTPUT_TOKENS = BUILDER.comment("Maximum output tokens requested from the upstream MOBNET inference endpoint.")
                .defineInRange("maxOutputTokens", 180, 32, 1024);
        LOCAL_API_PORT = BUILDER.comment("Loopback-only OpenAI-compatible bridge port used by CreatureChat.")
                .defineInRange("localApiPort", 18765, 1024, 65535);
        BUILDER.pop();
        SPEC = BUILDER.build();
    }

    private MobnetConfig() {}

    public static boolean externalDialogueEnabled() {
        return API_URL.get() != null && !API_URL.get().isBlank()
                && MODEL.get() != null && !MODEL.get().isBlank();
    }
}
