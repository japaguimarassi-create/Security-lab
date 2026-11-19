package io.github.japaguimarassi.mobnet;

import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

public final class MobnetClientState {
    private static final Map<UUID, Conversation> CONVERSATIONS = new ConcurrentHashMap<>();
    private static final Map<UUID, Bubble> BUBBLES = new ConcurrentHashMap<>();

    private MobnetClientState() {}

    public static void setConversation(UUID mobId, String mobName, int friendship, List<MobnetChatLine> lines) {
        CONVERSATIONS.put(mobId, new Conversation(mobName, friendship, List.copyOf(lines)));
    }

    public static Conversation conversation(UUID mobId) {
        return CONVERSATIONS.getOrDefault(mobId, new Conversation("Mob", 0, List.of()));
    }

    public static void setBubble(UUID mobId, String mobName, String message, int friendship, long durationMillis) {
        BUBBLES.put(mobId, new Bubble(mobName, message, friendship, System.currentTimeMillis() + durationMillis));
    }

    public static Bubble bubble(UUID mobId) {
        Bubble bubble = BUBBLES.get(mobId);
        if (bubble != null && bubble.expiresAt() < System.currentTimeMillis()) {
            BUBBLES.remove(mobId, bubble);
            return null;
        }
        return bubble;
    }

    public static void clear() {
        CONVERSATIONS.clear();
        BUBBLES.clear();
    }

    public record Conversation(String mobName, int friendship, List<MobnetChatLine> lines) {}
    public record Bubble(String mobName, String message, int friendship, long expiresAt) {}
}
