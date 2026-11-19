package io.github.japaguimarassi.mobnet;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;
import java.util.List;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

class MobnetMemoryStoreTest {
    @Test
    void profilesRelationshipsAndMemoriesPersistByUuid(@TempDir Path tempDir) throws Exception {
        UUID mob = UUID.randomUUID();
        UUID player = UUID.randomUUID();
        try (MobnetMemoryStore store = new MobnetMemoryStore()) {
            store.open(tempDir);
            MobnetProfile profile = store.getOrCreateProfile(mob, "minecraft:villager", "Aldeão");
            assertEquals(mob, profile.mobId());
            store.adjustFriendship(mob, player, 2);
            store.addMemory(mob, player, "PLAYER", "Olá!", List.of(1, 2, 3));
        }

        try (MobnetMemoryStore reopened = new MobnetMemoryStore()) {
            reopened.open(tempDir);
            assertEquals(2, reopened.friendship(mob, player));
            assertEquals(List.of("PLAYER: Olá!"), reopened.recentMemories(mob, player, 5));
        }
    }
}
