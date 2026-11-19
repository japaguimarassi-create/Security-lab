package io.github.japaguimarassi.mobnet;

import net.minecraftforge.common.ForgeConfigSpec;

public final class MobnetConfig {
    private static final ForgeConfigSpec.Builder BUILDER = new ForgeConfigSpec.Builder();

    public static final ForgeConfigSpec.ConfigValue<String> API_URL;
    public static final ForgeConfigSpec.ConfigValue<String> API_KEY;
    public static final ForgeConfigSpec.ConfigValue<String> MODEL;
    public static final ForgeConfigSpec.IntValue TIMEOUT_SECONDS;
    public static final ForgeConfigSpec.IntValue MAX_OUTPUT_TOKENS;
    public static final ForgeConfigSpec SPEC;

    static {
        BUILDER.push("conversation");
        API_URL = BUILDER.comment("Optional OpenAI-compatible chat-completions endpoint. Leave empty to use local MOBNET dialogue.")
                .define("apiUrl", "");
        API_KEY = BUILDER.comment("Optional API token. Never share this file or commit it to Git.")
                .define("apiKey", "");
        MODEL = BUILDER.comment("Model identifier required by the configured endpoint.")
                .define("model", "");
        TIMEOUT_SECONDS = BUILDER.comment("Maximum time for one dialogue request.")
                .defineInRange("timeoutSeconds", 30, 5, 120);
        MAX_OUTPUT_TOKENS = BUILDER.comment("Maximum tokens requested from the dialogue provider.")
                .defineInRange("maxOutputTokens", 180, 32, 1024);
        BUILDER.pop();
        SPEC = BUILDER.build();
    }

    private MobnetConfig() {}

    public static boolean externalDialogueEnabled() {
        return API_URL.get() != null && !API_URL.get().isBlank()
                && MODEL.get() != null && !MODEL.get().isBlank();
    }
}
