package io.github.japaguimarassi.mobnet;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonNull;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.mojang.brigadier.arguments.BoolArgumentType;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import net.minecraft.commands.Commands;
import net.minecraft.network.chat.Component;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.level.storage.LevelResource;
import net.minecraftforge.event.RegisterCommandsEvent;
import net.minecraftforge.event.server.ServerStartedEvent;
import net.minecraftforge.event.server.ServerStoppingEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

import java.io.IOException;
import java.io.InputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

@Mod.EventBusSubscriber(modid = MobnetMod.MODID, bus = Mod.EventBusSubscriber.Bus.FORGE)
public final class MobnetCreatureChatBridge {
    private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final int MAX_REQUEST_BYTES = 1_048_576;
    private static final String CREATURECHAT_PATH = "/v1/chat/completions";
    private static volatile HttpServer apiServer;
    private static volatile ExecutorService apiExecutor;
    private static volatile String activeKey = "";

    private MobnetCreatureChatBridge() {}

    @SubscribeEvent
    public static void registerCommands(RegisterCommandsEvent event) {
        event.getDispatcher().register(Commands.literal("mobnet")
                .then(keyCommand("key"))
                .then(keyCommand("Key")));
    }

    private static com.mojang.brigadier.builder.LiteralArgumentBuilder<net.minecraft.commands.CommandSourceStack> keyCommand(String literal) {
        return Commands.literal(literal)
                .requires(source -> source.hasPermission(2))
                .then(Commands.literal("active")
                        .then(Commands.argument("enabled", BoolArgumentType.bool())
                                .executes(context -> {
                                    boolean enabled = BoolArgumentType.getBool(context, "enabled");
                                    try {
                                        setActive(context.getSource().getServer(), enabled);
                                        context.getSource().sendSuccess(
                                                () -> Component.literal(enabled
                                                        ? "MOBNET conectado ao CreatureChat."
                                                        : "Conexão MOBNET removida; configuração anterior restaurada."),
                                                true
                                        );
                                        return 1;
                                    } catch (Exception exception) {
                                        context.getSource().sendFailure(Component.literal(
                                                "MOBNET: " + safeMessage(exception)
                                        ));
                                        return 0;
                                    }
                                })))
                .then(Commands.literal("status")
                        .executes(context -> {
                            boolean enabled = isActive(context.getSource().getServer());
                            context.getSource().sendSuccess(
                                    () -> Component.literal(enabled
                                            ? "MOBNET está ativo como provedor do CreatureChat."
                                            : "MOBNET está desativado."),
                                    false
                            );
                            return 1;
                        }));
    }

    @SubscribeEvent
    public static void onServerStarted(ServerStartedEvent event) {
        MinecraftServer server = event.getServer();
        Path stateFile = statePath(server);
        if (!Files.isRegularFile(stateFile)) return;

        try {
            JsonObject state = readJson(stateFile);
            if (!state.has("active") || !state.get("active").getAsBoolean()) return;
            if (!MobnetDialogueClient.isConfigured() || !isAllowedProviderUrl(MobnetConfig.API_URL.get())) {
                throw new IllegalStateException("Configure conversation.apiUrl em config/mobnet-common.toml antes de ativar o bridge.");
            }
            String key = requiredString(state, "key");
            Path target = Paths.get(requiredString(state, "configPath"));
            startApiServer(key);
            patchCreatureChatConfig(target, key);
            MobnetRuntime.LOGGER.info("MOBNET CreatureChat bridge restored for world {}", server.getWorldData().getLevelName());
        } catch (Exception exception) {
            stopApiServer();
            MobnetRuntime.LOGGER.error("Could not restore MOBNET CreatureChat bridge: {}", safeMessage(exception));
            server.getPlayerList().getPlayers().forEach(player ->
                    player.sendSystemMessage(Component.literal("§cMOBNET não conseguiu restaurar a conexão com CreatureChat: "
                            + safeMessage(exception))));
        }
    }

    @SubscribeEvent
    public static void onServerStopping(ServerStoppingEvent event) {
        stopApiServer();
    }

    private static synchronized void setActive(MinecraftServer server, boolean enabled) throws Exception {
        Path stateFile = statePath(server);
        JsonObject state = Files.isRegularFile(stateFile) ? readJson(stateFile) : new JsonObject();
        boolean active = state.has("active") && state.get("active").getAsBoolean();

        if (enabled) {
            if (!MobnetDialogueClient.isConfigured()) {
                throw new IllegalStateException("A API MOBNET ainda não foi configurada. Defina conversation.apiUrl e conversation.model em config/mobnet-common.toml.");
            }
            if (!isAllowedProviderUrl(MobnetConfig.API_URL.get())) {
                throw new IllegalStateException("A API MOBNET deve usar HTTPS. HTTP só é permitido em localhost.");
            }

            String key = active ? requiredString(state, "key") : generateKey();
            Path target = active
                    ? Paths.get(requiredString(state, "configPath"))
                    : chooseCreatureChatConfig(server);

            if (!active) {
                boolean existed = Files.isRegularFile(target);
                JsonObject current = existed ? readJson(target) : new JsonObject();
                JsonObject backup = new JsonObject();
                for (String field : List.of("apiKey", "url", "model", "timeout")) {
                    backup.add(field, current.has(field) ? current.get(field).deepCopy() : JsonNull.INSTANCE);
                }
                state = new JsonObject();
                state.addProperty("active", true);
                state.addProperty("key", key);
                state.addProperty("configPath", target.toAbsolutePath().normalize().toString());
                state.addProperty("fileExisted", existed);
                state.add("backup", backup);
            }

            startApiServer(key);
            boolean configPatched = false;
            try {
                patchCreatureChatConfig(target, key);
                configPatched = true;
                writeJsonAtomic(stateFile, state);
            } catch (Exception exception) {
                if (!active && configPatched) {
                    try {
                        restoreCreatureChatConfig(target, state);
                    } catch (Exception rollbackError) {
                        exception.addSuppressed(rollbackError);
                    }
                }
                if (!active) {
                    try {
                        Files.deleteIfExists(stateFile);
                    } catch (Exception cleanupError) {
                        exception.addSuppressed(cleanupError);
                    }
                }
                stopApiServer();
                throw exception;
            }
            return;
        }

        if (!active) {
            stopApiServer();
            return;
        }

        Path target = Paths.get(requiredString(state, "configPath"));
        restoreCreatureChatConfig(target, state);
        Files.deleteIfExists(stateFile);
        stopApiServer();
    }

    private static boolean isActive(MinecraftServer server) {
        Path file = statePath(server);
        if (!Files.isRegularFile(file)) return false;
        try {
            JsonObject state = readJson(file);
            return state.has("active") && state.get("active").getAsBoolean();
        } catch (Exception ignored) {
            return false;
        }
    }

    private static Path statePath(MinecraftServer server) {
        return server.getWorldPath(LevelResource.ROOT)
                .resolve("mobnet")
                .resolve("creaturechat-bridge.json");
    }

    private static Path chooseCreatureChatConfig(MinecraftServer server) {
        Path serverConfig = server.getWorldPath(LevelResource.ROOT).resolve("creaturechat.json");
        if (Files.isRegularFile(serverConfig)) return serverConfig;
        return Paths.get(".", "creaturechat.json").toAbsolutePath().normalize();
    }

    private static String generateKey() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        StringBuilder output = new StringBuilder("mobnet_");
        for (byte value : bytes) output.append(String.format("%02x", value & 0xff));
        return output.toString();
    }

    private static void startApiServer(String key) throws IOException {
        if (apiServer != null && apiServer.getAddress().getPort() == MobnetConfig.LOCAL_API_PORT.get()
                && MessageDigest.isEqual(activeKey.getBytes(StandardCharsets.UTF_8), key.getBytes(StandardCharsets.UTF_8))) {
            return;
        }
        stopApiServer();

        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getByName("127.0.0.1"), MobnetConfig.LOCAL_API_PORT.get()), 0
        );
        ExecutorService executor = Executors.newFixedThreadPool(3, runnable -> {
            Thread thread = new Thread(runnable, "MOBNET-CreatureChat-API");
            thread.setDaemon(true);
            return thread;
        });
        server.createContext(CREATURECHAT_PATH, exchange -> handleApiRequest(exchange, key));
        server.setExecutor(executor);
        server.start();

        activeKey = key;
        apiExecutor = executor;
        apiServer = server;
        MobnetRuntime.LOGGER.info("MOBNET local CreatureChat API listening on 127.0.0.1:{}",
                MobnetConfig.LOCAL_API_PORT.get());
    }

    private static synchronized void stopApiServer() {
        HttpServer server = apiServer;
        ExecutorService executor = apiExecutor;
        apiServer = null;
        apiExecutor = null;
        activeKey = "";
        if (server != null) server.stop(0);
        if (executor != null) executor.shutdownNow();
    }

    private static void patchCreatureChatConfig(Path target, String key) throws IOException {
        JsonObject config = Files.isRegularFile(target) ? readJson(target) : new JsonObject();
        config.addProperty("apiKey", key);
        config.addProperty("url", "http://127.0.0.1:" + MobnetConfig.LOCAL_API_PORT.get() + CREATURECHAT_PATH);
        config.addProperty("model", "mobnet");
        config.addProperty("timeout", Math.min(120, Math.max(30, MobnetConfig.TIMEOUT_SECONDS.get() + 10)));
        writeJsonAtomic(target, config);
    }

    private static void restoreCreatureChatConfig(Path target, JsonObject state) throws IOException {
        if (!Files.isRegularFile(target)) return;
        JsonObject config = readJson(target);
        JsonObject backup = state.has("backup") && state.get("backup").isJsonObject()
                ? state.getAsJsonObject("backup") : new JsonObject();

        for (String field : List.of("apiKey", "url", "model", "timeout")) {
            JsonElement original = backup.has(field) ? backup.get(field) : JsonNull.INSTANCE;
            if (original == null || original.isJsonNull()) config.remove(field);
            else config.add(field, original.deepCopy());
        }

        boolean existed = state.has("fileExisted") && state.get("fileExisted").getAsBoolean();
        if (!existed && config.size() == 0) {
            Files.deleteIfExists(target);
        } else {
            writeJsonAtomic(target, config);
        }
    }

    private static void handleApiRequest(HttpExchange exchange, String expectedKey) throws IOException {
        try {
            if (!"POST".equalsIgnoreCase(exchange.getRequestMethod())
                    || !CREATURECHAT_PATH.equals(exchange.getRequestURI().getPath())) {
                sendError(exchange, 405, "method_not_allowed", "Only POST /v1/chat/completions is supported.");
                return;
            }

            String authorization = exchange.getRequestHeaders().getFirst("Authorization");
            String expectedAuthorization = "Bearer " + expectedKey;
            if (authorization == null || !MessageDigest.isEqual(
                    authorization.getBytes(StandardCharsets.UTF_8),
                    expectedAuthorization.getBytes(StandardCharsets.UTF_8))) {
                sendError(exchange, 401, "invalid_api_key", "Invalid MOBNET bridge key.");
                return;
            }

            byte[] body;
            try (InputStream input = exchange.getRequestBody()) {
                body = input.readNBytes(MAX_REQUEST_BYTES + 1);
            }
            if (body.length > MAX_REQUEST_BYTES) {
                sendError(exchange, 413, "request_too_large", "Request body exceeds 1 MiB.");
                return;
            }

            JsonElement parsed = JsonParser.parseString(new String(body, StandardCharsets.UTF_8));
            if (!parsed.isJsonObject()) {
                sendError(exchange, 400, "invalid_request", "Expected a JSON object.");
                return;
            }

            JsonObject payload = parsed.getAsJsonObject();
            JsonArray messages = payload.has("messages") && payload.get("messages").isJsonArray()
                    ? payload.getAsJsonArray("messages") : new JsonArray();
            StringBuilder system = new StringBuilder();
            List<MobnetChatLine> history = new ArrayList<>();

            for (int i = 0; i < messages.size(); i++) {
                JsonElement element = messages.get(i);
                if (!element.isJsonObject()) continue;
                JsonObject message = element.getAsJsonObject();
                if (!"system".equalsIgnoreCase(stringValue(message, "role"))) continue;
                String content = stringValue(message, "content");
                if (content.isBlank()) continue;
                if (system.length() > 0) system.append("\\n\\n");
                system.append(limit(content, 16000));
            }

            int start = Math.max(0, messages.size() - 32);
            for (int i = start; i < messages.size(); i++) {
                JsonElement element = messages.get(i);
                if (!element.isJsonObject()) continue;
                JsonObject message = element.getAsJsonObject();
                String role = stringValue(message, "role");
                String content = stringValue(message, "content");
                if (content.isBlank()) continue;

                if ("user".equalsIgnoreCase(role)) {
                    history.add(new MobnetChatLine("PLAYER", limit(content, 2048), System.currentTimeMillis()));
                } else if ("assistant".equalsIgnoreCase(role)) {
                    history.add(new MobnetChatLine("MOB", limit(content, 2048), System.currentTimeMillis()));
                }
            }

            if (system.length() == 0) {
                sendError(exchange, 400, "missing_system_prompt", "CreatureChat did not provide a system prompt.");
                return;
            }
            if (!MobnetDialogueClient.isConfigured()) {
                sendError(exchange, 503, "mobnet_not_configured", "The MOBNET inference endpoint is not configured.");
                return;
            }

            CompletableFuture<String> completion = MobnetDialogueClient.complete(system.toString(), history, null);
            String answer;
            try {
                answer = completion.get(MobnetConfig.TIMEOUT_SECONDS.get() + 8L, TimeUnit.SECONDS);
            } catch (TimeoutException exception) {
                completion.cancel(true);
                sendError(exchange, 504, "mobnet_timeout", "The MOBNET inference endpoint timed out.");
                return;
            } catch (Exception exception) {
                sendError(exchange, 502, "mobnet_upstream_error", "The MOBNET inference endpoint could not complete the request.");
                return;
            }

            if (answer == null || answer.isBlank()) {
                sendError(exchange, 502, "empty_mobnet_response", "The MOBNET inference endpoint returned no message.");
                return;
            }

            JsonObject response = new JsonObject();
            response.addProperty("id", "chatcmpl-mobnet-" + UUID.randomUUID());
            response.addProperty("object", "chat.completion");
            response.addProperty("created", System.currentTimeMillis() / 1000L);
            response.addProperty("model", "mobnet");

            JsonObject resultMessage = new JsonObject();
            resultMessage.addProperty("role", "assistant");
            resultMessage.addProperty("content", limit(answer, 12000));

            JsonObject choice = new JsonObject();
            choice.addProperty("index", 0);
            choice.add("message", resultMessage);
            choice.addProperty("finish_reason", "stop");
            JsonArray choices = new JsonArray();
            choices.add(choice);
            response.add("choices", choices);

            JsonObject usage = new JsonObject();
            usage.addProperty("prompt_tokens", 0);
            usage.addProperty("completion_tokens", 0);
            usage.addProperty("total_tokens", 0);
            response.add("usage", usage);
            sendJson(exchange, 200, response);
        } catch (Exception exception) {
            sendError(exchange, 500, "mobnet_bridge_error", "MOBNET bridge could not process the request.");
            MobnetRuntime.LOGGER.warn("MOBNET CreatureChat bridge request failed: {}",
                    exception.getClass().getSimpleName());
        } finally {
            exchange.close();
        }
    }

    private static void sendError(HttpExchange exchange, int status, String code, String message) throws IOException {
        JsonObject error = new JsonObject();
        error.addProperty("message", message);
        error.addProperty("type", "mobnet_error");
        error.addProperty("code", code);
        JsonObject response = new JsonObject();
        response.add("error", error);
        sendJson(exchange, status, response);
    }

    private static void sendJson(HttpExchange exchange, int status, JsonObject response) throws IOException {
        byte[] bytes = GSON.toJson(response).getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json; charset=utf-8");
        exchange.getResponseHeaders().set("Cache-Control", "no-store");
        exchange.getResponseHeaders().set("X-Content-Type-Options", "nosniff");
        exchange.sendResponseHeaders(status, bytes.length);
        exchange.getResponseBody().write(bytes);
        exchange.getResponseBody().flush();
    }

    private static boolean isAllowedProviderUrl(String rawUrl) {
        if (rawUrl == null || rawUrl.isBlank()) return false;
        try {
            URI uri = URI.create(rawUrl.trim());
            String scheme = uri.getScheme();
            if ("https".equalsIgnoreCase(scheme)) return uri.getHost() != null;
            if (!"http".equalsIgnoreCase(scheme) || uri.getHost() == null) return false;
            String host = uri.getHost();
            return host.equalsIgnoreCase("localhost") || host.equals("127.0.0.1") || host.equals("::1");
        } catch (IllegalArgumentException exception) {
            return false;
        }
    }

    private static JsonObject readJson(Path path) throws IOException {
        JsonElement element = JsonParser.parseString(Files.readString(path, StandardCharsets.UTF_8));
        if (!element.isJsonObject()) throw new IOException("Invalid JSON object in " + path.getFileName());
        return element.getAsJsonObject();
    }

    private static void writeJsonAtomic(Path path, JsonObject value) throws IOException {
        Path absolute = path.toAbsolutePath().normalize();
        Path parent = absolute.getParent();
        if (parent != null) Files.createDirectories(parent);
        Path temporary = absolute.resolveSibling(absolute.getFileName() + ".tmp");
        Files.writeString(temporary, GSON.toJson(value) + System.lineSeparator(), StandardCharsets.UTF_8);
        try {
            Files.move(temporary, absolute, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
        } catch (AtomicMoveNotSupportedException ignored) {
            Files.move(temporary, absolute, StandardCopyOption.REPLACE_EXISTING);
        }
    }

    private static String requiredString(JsonObject object, String field) {
        if (!object.has(field) || object.get(field).isJsonNull()) {
            throw new IllegalStateException("Missing " + field + " in MOBNET bridge state.");
        }
        return object.get(field).getAsString();
    }

    private static String stringValue(JsonObject object, String field) {
        if (!object.has(field) || object.get(field).isJsonNull()) return "";
        JsonElement value = object.get(field);
        return value.isJsonPrimitive() ? value.getAsString() : "";
    }

    private static String limit(String value, int maximum) {
        if (value == null) return "";
        return value.length() <= maximum ? value : value.substring(0, maximum);
    }

    private static String safeMessage(Throwable throwable) {
        String message = throwable.getMessage();
        if (message == null || message.isBlank()) return throwable.getClass().getSimpleName();
        return message.length() > 220 ? message.substring(0, 217) + "..." : message;
    }
}
