package io.github.japaguimarassi.mobnet;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class MobnetDialogueClientTest {
    @Test
    void forwardsCreatureChatJsonResponseMode() {
        JsonObject payload = MobnetDialogueClient.buildPayload(
                "mobnet", "Create a character sheet", List.of(), null, true, 200);

        assertEquals("mobnet", payload.get("model").getAsString());
        assertEquals("json_object",
                payload.getAsJsonObject("response_format").get("type").getAsString());
        assertEquals(200, payload.get("max_tokens").getAsInt());
    }

    @Test
    void textConversationDoesNotForceJsonMode() {
        JsonObject payload = MobnetDialogueClient.buildPayload(
                "mobnet", "Answer naturally", List.of(), "Olá", false, 180);

        assertFalse(payload.has("response_format"));
        assertEquals("Olá",
                payload.getAsJsonArray("messages").get(1).getAsJsonObject().get("content").getAsString());
    }

    @Test
    void preservesCreatureChatHistoryRolesAndBoundsOutputTokens() {
        List<MobnetChatLine> history = List.of(
                new MobnetChatLine("PLAYER", "Olá", 1L),
                new MobnetChatLine("MOB", "Oi", 2L));
        JsonObject payload = MobnetDialogueClient.buildPayload(
                "mobnet", "System", history, null, false, 5000);

        JsonArray messages = payload.getAsJsonArray("messages");
        assertEquals(3, messages.size());
        assertEquals("system", messages.get(0).getAsJsonObject().get("role").getAsString());
        assertEquals("user", messages.get(1).getAsJsonObject().get("role").getAsString());
        assertEquals("assistant", messages.get(2).getAsJsonObject().get("role").getAsString());
        assertEquals(1024, payload.get("max_tokens").getAsInt());
    }
}
