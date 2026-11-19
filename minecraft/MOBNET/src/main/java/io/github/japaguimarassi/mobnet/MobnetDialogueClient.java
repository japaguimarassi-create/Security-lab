package io.github.japaguimarassi.mobnet;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class MobnetDialogueClient {
    private static final AtomicInteger THREAD_ID = new AtomicInteger();
    private static final ThreadFactory THREAD_FACTORY = task -> {
        Thread thread = new Thread(task, "MOBNET-Dialogue-" + THREAD_ID.incrementAndGet());
        thread.setDaemon(true);
        return thread;
    };
    private static final ThreadPoolExecutor EXECUTOR = new ThreadPoolExecutor(
            2, 2, 0L, TimeUnit.MILLISECONDS, new ArrayBlockingQueue<>(48), THREAD_FACTORY,
            new ThreadPoolExecutor.AbortPolicy()
    );
    private static final HttpClient HTTP = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(8))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

    private MobnetDialogueClient() {}

    public static boolean isConfigured() {
        return MobnetConfig.externalDialogueEnabled();
    }

    public static CompletableFuture<String> complete(String systemPrompt, List<MobnetChatLine> history,
                                                      String currentUserMessage) {
        if (!isConfigured()) return CompletableFuture.completedFuture(null);
        try {
            return CompletableFuture.supplyAsync(() -> request(systemPrompt, history, currentUserMessage), EXECUTOR);
        } catch (RuntimeException exception) {
            return CompletableFuture.completedFuture(null);
        }
    }

    private static String request(String systemPrompt, List<MobnetChatLine> history, String currentUserMessage) {
        String endpoint = MobnetConfig.API_URL.get().trim();
        String model = MobnetConfig.MODEL.get().trim();
        try {
            URI uri = URI.create(endpoint);
            String scheme = uri.getScheme();
            if (!("https".equalsIgnoreCase(scheme)
                    || ("http".equalsIgnoreCase(scheme) && isLoopback(uri.getHost())))) {
                MobnetRuntime.LOGGER.warn("MOBNET dialogue endpoint rejected: use HTTPS or a loopback HTTP endpoint");
                return null;
            }

            JsonObject payload = new JsonObject();
            payload.addProperty("model", model);
            payload.addProperty("temperature", 0.85);
            payload.addProperty("max_tokens", MobnetConfig.MAX_OUTPUT_TOKENS.get());
            JsonArray messages = new JsonArray();
            JsonObject system = new JsonObject();
            system.addProperty("role", "system");
            system.addProperty("content", limit(systemPrompt, 12000));
            messages.add(system);

            if (history != null) {
                int start = Math.max(0, history.size() - 12);
                for (int i = start; i < history.size(); i++) {
                    MobnetChatLine line = history.get(i);
                    JsonObject item = new JsonObject();
                    item.addProperty("role", "MOB".equalsIgnoreCase(line.speaker()) ? "assistant" : "user");
                    item.addProperty("content", limit(line.message(), 1024));
                    messages.add(item);
                }
            }

            if (currentUserMessage != null && !currentUserMessage.isBlank()) {
                JsonObject latest = new JsonObject();
                latest.addProperty("role", "user");
                latest.addProperty("content", limit(currentUserMessage, 512));
                messages.add(latest);
            }
            payload.add("messages", messages);

            HttpRequest.Builder request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(MobnetConfig.TIMEOUT_SECONDS.get()))
                    .header("Content-Type", "application/json")
                    .header("Accept", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(payload.toString()));
            String key = MobnetConfig.API_KEY.get();
            if (key != null && !key.isBlank()) request.header("Authorization", "Bearer " + key.trim());

            HttpResponse<String> response = HTTP.send(request.build(), HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                MobnetRuntime.LOGGER.warn("MOBNET dialogue provider returned HTTP {}", response.statusCode());
                return null;
            }

            JsonObject root = JsonParser.parseString(response.body()).getAsJsonObject();
            JsonArray choices = root.getAsJsonArray("choices");
            if (choices == null || choices.isEmpty()) return null;
            JsonObject message = choices.get(0).getAsJsonObject().getAsJsonObject("message");
            if (message == null || !message.has("content") || message.get("content").isJsonNull()) return null;
            String content = message.get("content").getAsString();
            return content == null || content.isBlank() ? null : limit(content.trim(), 1500);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            return null;
        } catch (Exception exception) {
            MobnetRuntime.LOGGER.warn("MOBNET dialogue request failed: {}", exception.getClass().getSimpleName());
            return null;
        }
    }

    private static boolean isLoopback(String host) {
        if (host == null) return false;
        return host.equalsIgnoreCase("localhost") || host.equals("127.0.0.1") || host.equals("::1");
    }

    private static String limit(String text, int max) {
        if (text == null) return "";
        return text.length() <= max ? text : text.substring(0, max);
    }
}
