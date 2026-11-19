package io.github.japaguimarassi.mobnet;

import net.minecraft.nbt.CompoundTag;
import net.minecraft.network.chat.Component;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.storage.LevelResource;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.nio.file.Path;
import java.sql.SQLException;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.Set;

public final class MobnetRuntime {
    public static final Logger LOGGER = LoggerFactory.getLogger(MobnetMod.MODID);
    public static final String NBT_ACTION = "mobnet_action";
    public static final String NBT_OWNER = "mobnet_owner";
    public static final String NBT_EXPIRES = "mobnet_expires";
    private static final String ACTIVE_MOB = "mobnet_active_mob";
    private static final String BUBBLE_ACTIVE = "mobnet_bubble_active";
    private static final String BUBBLE_TICKS = "mobnet_bubble_ticks";
    private static final String OLD_NAME_JSON = "mobnet_old_name_json";
    private static final String OLD_HAS_NAME = "mobnet_old_has_name";
    private static final String OLD_NAME_VISIBLE = "mobnet_old_name_visible";

    private static final MobnetTokenizer TOKENIZER = new MobnetTokenizer();
    private static MobnetNeuralCore neural = new MobnetNeuralCore();
    private static MobnetMemoryStore memory;
    private static Path modelPath;
    private static final Set<UUID> ATTACHED_GOALS = ConcurrentHashMap.newKeySet();
    private static final Set<String> OPENING_CHATS = ConcurrentHashMap.newKeySet();
    private static final Map<String, Decision> LAST_DECISIONS = new ConcurrentHashMap<>();

    private MobnetRuntime() {}

    public static void start(MinecraftServer server) {
        Path root = server.getWorldPath(LevelResource.ROOT).resolve("mobnet");
        modelPath = root.resolve("policy-head.bin");
        neural = new MobnetNeuralCore();
        if (neural.load(modelPath)) {
            LOGGER.info("Loaded MOBNET policy head from {}", modelPath);
        } else if (java.nio.file.Files.exists(modelPath)) {
            LOGGER.warn("MOBNET policy file is invalid or incompatible; using safe initialized policy");
        }
        memory = new MobnetMemoryStore();
        try {
            memory.open(root.resolve("database"));
            LOGGER.info("MOBNET SQL memory opened at {}", root.resolve("database"));
        } catch (IOException | SQLException exception) {
            LOGGER.error("MOBNET SQL memory could not be opened; chat remains available without persistence", exception);
            memory = null;
        }
        ATTACHED_GOALS.clear();
        LAST_DECISIONS.clear();
    }

    public static void stop() {
        if (modelPath != null) {
            try {
                neural.save(modelPath);
            } catch (IOException exception) {
                LOGGER.error("Could not save MOBNET policy head", exception);
            }
        }
        if (memory != null) {
            try {
                memory.close();
            } catch (SQLException exception) {
                LOGGER.error("Could not close MOBNET SQL memory cleanly", exception);
            }
            memory = null;
        }
        ATTACHED_GOALS.clear();
        LAST_DECISIONS.clear();
    }

    public static void select(ServerPlayer player, Mob mob) {
        if (mob.level() != player.level() || !mob.isAlive()) {
            player.sendSystemMessage(Component.literal("§cEsse mob não está disponível neste mundo."));
            return;
        }
        if (player.distanceToSqr(mob) > 32.0 * 32.0) {
            player.sendSystemMessage(Component.literal("§cAproxime-se do mob para conversar."));
            return;
        }
        player.getPersistentData().putUUID(ACTIVE_MOB, mob.getUUID());
        profile(mob);
        attachGoal(mob);
        player.sendSystemMessage(Component.literal("§b[MOBNET] §fVocê selecionou §e" + mob.getName().getString()
                + "§f. Use §a/mobnet say <mensagem>§f para conversar."));
    }

    public static void openChat(ServerPlayer player, UUID mobId) {
        Mob mob = findMob(player, mobId);
        if (mob == null) return;

        player.getPersistentData().putUUID(ACTIVE_MOB, mob.getUUID());
        attachGoal(mob);
        MobnetProfile profile = profile(mob);
        List<MobnetChatLine> lines = recentChat(mob.getUUID(), player.getUUID(), 40);
        int currentFriendship = friendship(mob.getUUID(), player.getUUID());

        if (!lines.isEmpty()) {
            MobnetNetwork.sendConversation(player, mob.getUUID(), mob.getName().getString(), currentFriendship, lines);
            MobnetChatLine latest = lines.get(lines.size() - 1);
            if ("MOB".equalsIgnoreCase(latest.speaker())) {
                MobnetNetwork.sendBubble(mob, latest.message(), currentFriendship);
            }
            return;
        }

        if (MobnetDialogueClient.isConfigured()) {
            String initializationKey = decisionKey(mob.getUUID(), player.getUUID());
            MobnetNetwork.sendConversation(player, mob.getUUID(), mob.getName().getString(), currentFriendship, List.of());
            if (!OPENING_CHATS.add(initializationKey)) return;

            String characterPrompt = MobnetConversationEngine.characterPrompt(
                    profile.entityType(), profile.displayName(), profile.personality());
            MinecraftServer server = player.getServer();
            if (server == null) {
                OPENING_CHATS.remove(initializationKey);
                return;
            }
            MobnetDialogueClient.complete(characterPrompt, List.of(), "Crie a ficha completa do personagem.")
                    .whenComplete((generatedSheet, error) -> server.execute(() -> {
                        OPENING_CHATS.remove(initializationKey);
                        if (!isValidConversationTarget(player, mob)) return;

                        MobnetCharacterSheet sheet = generatedSheet == null || generatedSheet.isBlank()
                                ? MobnetCharacterSheet.defaultFor(profile.entityType(), profile.displayName(), profile.personality())
                                : MobnetCharacterSheet.parse(generatedSheet, profile.displayName(), profile.personality());
                        persistCharacterSheet(mob.getUUID(), sheet);
                        MobnetProfile updatedProfile = new MobnetProfile(profile.mobId(), profile.entityType(),
                                profile.displayName(), profile.personality(), sheet.toPromptText());
                        publishFirstGreeting(player, mob, updatedProfile, sheet);
                    }));
            return;
        }

        MobnetCharacterSheet sheet = MobnetCharacterSheet.parse(
                profile.characterSheet(), profile.displayName(), profile.personality());
        publishFirstGreeting(player, mob, profile, sheet);
    }

    private static boolean isValidConversationTarget(ServerPlayer player, Mob mob) {
        return player != null && !player.isRemoved() && player.isAlive()
                && mob != null && !mob.isRemoved() && mob.isAlive()
                && player.level() == mob.level() && player.distanceToSqr(mob) <= 32.0 * 32.0;
    }

    private static void persistCharacterSheet(UUID mobId, MobnetCharacterSheet sheet) {
        if (memory == null) return;
        try {
            memory.saveCharacterSheet(mobId, sheet.toPromptText());
        } catch (SQLException exception) {
            LOGGER.error("Could not save MOBNET character sheet", exception);
        }
    }

    private static void publishFirstGreeting(ServerPlayer player, Mob mob,
                                             MobnetProfile profile, MobnetCharacterSheet sheet) {
        if (!isValidConversationTarget(player, mob)) return;
        String greeting = sheet.shortGreeting();
        storeMemory(mob, player, "MOB", greeting);
        int currentFriendship = friendship(mob.getUUID(), player.getUUID());
        List<MobnetChatLine> lines = recentChat(mob.getUUID(), player.getUUID(), 40);
        MobnetNetwork.sendConversation(player, mob.getUUID(), mob.getName().getString(), currentFriendship, lines);
        MobnetNetwork.sendBubble(mob, greeting, currentFriendship);
    }

    public static void say(ServerPlayer player, String rawMessage) {
        Mob mob = selectedMob(player);
        if (mob != null) say(player, mob.getUUID(), rawMessage);
    }

    public static void say(ServerPlayer player, UUID mobId, String rawMessage) {
        String message = rawMessage == null ? "" : rawMessage.trim();
        if (message.isEmpty() || message.length() > 512) {
            player.sendSystemMessage(Component.literal("§cA mensagem precisa ter entre 1 e 512 caracteres."));
            return;
        }
        Mob mob = findMob(player, mobId);
        if (mob == null) return;

        player.getPersistentData().putUUID(ACTIVE_MOB, mob.getUUID());
        MobnetProfile profile = profile(mob);
        int friendship = friendship(mob.getUUID(), player.getUUID());
        MobnetAction intent = MobnetIntentParser.parse(message);
        float[] state = MobnetStateEncoder.encode(mob, player, intent, friendship);
        MobnetAction action = MobnetActionMask.validate(neural.chooseAction(state),
                mob.canAttack(player), player.isCreative(), player.isSpectator());
        LAST_DECISIONS.put(decisionKey(mob.getUUID(), player.getUUID()), new Decision(state, action));

        storeMemory(mob, player, "PLAYER", message);
        List<MobnetChatLine> history = recentChat(mob.getUUID(), player.getUUID(), 40);
        String systemPrompt = buildSystemPrompt(profile, mob, player, friendship);
        MinecraftServer server = player.getServer();
        if (server == null) return;

        if (MobnetDialogueClient.isConfigured()) {
            MobnetDialogueClient.complete(systemPrompt, history, null).whenComplete((response, error) -> {
                String resolved = error == null ? response : null;
                server.execute(() -> finishResponse(player, mob, message, profile, friendship, state, action, resolved));
            });
        } else {
            String fallback = MobnetConversationEngine.reply(profile, player.getName().getString(),
                    message, action, friendship, recentMemories(mob.getUUID(), player.getUUID(), 8));
            finishResponse(player, mob, message, profile, friendship, state, action, fallback);
        }
    }

    private static void finishResponse(ServerPlayer player, Mob mob, String userMessage, MobnetProfile profile,
                                       int oldFriendship, float[] originalState, MobnetAction inputAction,
                                       String rawResponse) {
        if (player.isRemoved() || mob.isRemoved() || !mob.isAlive()
                || player.level() != mob.level() || player.distanceToSqr(mob) > 32.0 * 32.0) return;

        String response = rawResponse == null || rawResponse.isBlank()
                ? MobnetConversationEngine.reply(profile, player.getName().getString(), userMessage,
                    inputAction, oldFriendship, recentMemories(mob.getUUID(), player.getUUID(), 8))
                : rawResponse;

        ParsedMessage parsed = MessageParser.parseMessage(response);
        MobnetAction suggestion = actionFromBehaviors(parsed.getBehaviors(), MobnetIntentParser.parse(userMessage));
        int currentFriendship = oldFriendship;
        for (Behavior behavior : parsed.getBehaviors()) {
            if ("FRIENDSHIP".equals(behavior.getName()) && behavior.getArgument() != null) {
                currentFriendship = Math.max(-3, Math.min(3, behavior.getArgument()));
                break;
            }
        }
        if (currentFriendship != oldFriendship && memory != null) {
            try {
                memory.setFriendship(mob.getUUID(), player.getUUID(), currentFriendship);
            } catch (SQLException exception) {
                LOGGER.error("Could not persist MOBNET friendship update", exception);
            }
        }

        float[] decisionState = MobnetStateEncoder.encode(mob, player, suggestion, currentFriendship);
        MobnetAction finalAction = MobnetActionMask.validate(neural.chooseAction(decisionState),
                mob.canAttack(player), player.isCreative(), player.isSpectator());
        LAST_DECISIONS.put(decisionKey(mob.getUUID(), player.getUUID()), new Decision(decisionState, finalAction));
        if (isBehavior(finalAction)) applyBehavior(mob, player, finalAction);
        else if (finalAction == MobnetAction.STAY || finalAction == MobnetAction.IDLE) clearBehavior(mob);

        String cleanReply = parsed.getCleanedMessage();
        if (cleanReply.isBlank()) cleanReply = "Estou aqui. Pode continuar.";
        storeMemory(mob, player, "MOB", cleanReply);
        recordExperience(mob, player, decisionState, finalAction, 0.0f);

        int finalFriendship = friendship(mob.getUUID(), player.getUUID());
        List<MobnetChatLine> lines = recentChat(mob.getUUID(), player.getUUID(), 40);
        MobnetNetwork.sendConversation(player, mob.getUUID(), mob.getName().getString(), finalFriendship, lines);
        MobnetNetwork.sendBubble(mob, cleanReply, finalFriendship);
        broadcastNearby((ServerLevel) mob.level(), mob, cleanReply);
    }

    private static MobnetAction actionFromBehaviors(List<Behavior> behaviors, MobnetAction fallback) {
        for (Behavior behavior : behaviors) {
            switch (behavior.getName()) {
                case "FOLLOW": return MobnetAction.FOLLOW;
                case "LEAD": return MobnetAction.GUIDE;
                case "FLEE": return MobnetAction.FLEE;
                case "ATTACK": return MobnetAction.ATTACK;
                case "PROTECT": return MobnetAction.PROTECT;
                case "UNFOLLOW", "UNLEAD", "UNPROTECT", "UNFLEE": return MobnetAction.STAY;
                default: break;
            }
        }
        return fallback == null ? MobnetAction.TALK : fallback;
    }

    private static String buildSystemPrompt(MobnetProfile profile, Mob mob, ServerPlayer player, int friendship) {
        String biome = player.level().getBiome(player.blockPosition()).unwrapKey()
                .map(key -> key.location().toString()).orElse("desconhecido");
        long dayTime = player.level().getDayTime() % 24000L;
        String worldTime = String.format(java.util.Locale.ROOT, "%02d:%02d",
                (int) (((dayTime / 1000L + 6L) % 24L)), (int) (((dayTime % 1000L) * 60L) / 1000L));
        String heldItem = player.getMainHandItem().isEmpty()
                ? "mãos vazias" : player.getMainHandItem().getHoverName().getString();
        MobnetConversationEngine.Mob mobContext = new MobnetConversationEngine.Mob(
                mob.getType().toString(), mob.getHealth(), mob.getMaxHealth());
        MobnetConversationEngine.ServerPlayerContext playerContext =
                new MobnetConversationEngine.ServerPlayerContext(player.getName().getString(), player.getHealth(),
                        heldItem, biome, worldTime, player.level().isRaining(), mob.distanceTo(player));
        return MobnetConversationEngine.systemPrompt(profile, mobContext, playerContext, friendship, List.of());
    }

    private static Mob findMob(ServerPlayer player, UUID mobId) {
        if (mobId == null || player.serverLevel() == null) return null;
        Entity entity = player.serverLevel().getEntity(mobId);
        if (!(entity instanceof Mob mob) || mob.isRemoved() || !mob.isAlive()) {
            player.sendSystemMessage(Component.literal("§cEssa criatura não está mais disponível."));
            return null;
        }
        if (mob.level() != player.level() || player.distanceToSqr(mob) > 32.0 * 32.0) {
            player.sendSystemMessage(Component.literal("§cAproxime-se até 32 blocos da criatura."));
            return null;
        }
        return mob;
    }

    public static void gift(ServerPlayer player) {
        Mob mob = selectedMob(player);
        if (mob == null) return;
        ItemStack held = player.getMainHandItem();
        if (held.isEmpty()) {
            player.sendSystemMessage(Component.literal("§cSegure um item para oferecer ao mob."));
            return;
        }
        String itemName = held.getHoverName().getString();
        if (!player.getAbilities().instabuild) held.shrink(1);
        int friendship = adjustFriendship(mob.getUUID(), player.getUUID(), 1);
        String reply = "Obrigado pelo presente, " + player.getName().getString() + "! Agora nossa amizade está em " + friendship + ".";
        storeMemory(mob, player, "PLAYER", "Deu um presente: " + itemName);
        storeMemory(mob, player, "MOB", reply);
        MobnetNetwork.sendConversation(player, mob.getUUID(), mob.getName().getString(), friendship,
                recentChat(mob.getUUID(), player.getUUID(), 40));
        MobnetNetwork.sendBubble(mob, reply, friendship);
        broadcastNearby((ServerLevel) mob.level(), mob, reply);
    }

    public static void showMemory(ServerPlayer player) {
        Mob mob = selectedMob(player);
        if (mob == null) return;
        List<String> rows = recentMemories(mob.getUUID(), player.getUUID(), 10);
        player.sendSystemMessage(Component.literal("§b[MOBNET] §fMemórias recentes de " + mob.getName().getString() + ":"));
        if (rows.isEmpty()) {
            player.sendSystemMessage(Component.literal("§7Nenhuma memória registrada ainda."));
            return;
        }
        for (String row : rows) player.sendSystemMessage(Component.literal("§7• §f" + row));
    }

    public static void showRelationship(ServerPlayer player) {
        Mob mob = selectedMob(player);
        if (mob == null) return;
        int value = friendship(mob.getUUID(), player.getUUID());
        player.sendSystemMessage(Component.literal("§b[MOBNET] §fRelação com " + mob.getName().getString() + ": §e" + value + "§f/3"));
    }

    public static void reward(ServerPlayer player, float reward) {
        Mob mob = selectedMob(player);
        if (mob == null) return;
        if (!Float.isFinite(reward) || reward < -1.0f || reward > 1.0f) {
            player.sendSystemMessage(Component.literal("§cA recompensa precisa estar entre -1 e 1."));
            return;
        }
        Decision decision = LAST_DECISIONS.get(decisionKey(mob.getUUID(), player.getUUID()));
        if (decision == null) {
            player.sendSystemMessage(Component.literal("§cAinda não há uma decisão recente para avaliar."));
            return;
        }
        neural.learn(decision.state(), decision.action(), reward);
        recordExperience(mob, player, decision.state(), decision.action(), reward);
        if (modelPath != null) {
            try {
                neural.save(modelPath);
            } catch (IOException exception) {
                LOGGER.error("Could not persist MOBNET feedback update", exception);
            }
        }
        player.sendSystemMessage(Component.literal("§b[MOBNET] §fFeedback registrado para a ação §e" + decision.action().name() + "§f."));
    }

    public static void stopBehavior(ServerPlayer player) {
        Mob mob = selectedMob(player);
        if (mob == null) return;
        clearBehavior(mob);
        mob.getNavigation().stop();
        mob.setTarget(null);
        player.sendSystemMessage(Component.literal("§b[MOBNET] §fComportamento neural interrompido."));
    }

    public static void attachGoal(Mob mob) {
        if (mob.level().isClientSide() || mob.isRemoved()) return;
        if (ATTACHED_GOALS.add(mob.getUUID())) {
            mob.goalSelector.addGoal(2, new MobnetBehaviorGoal(mob));
        }
    }

    public static void detachGoal(Mob mob) {
        ATTACHED_GOALS.remove(mob.getUUID());
    }

    public static void applyBehavior(Mob mob, ServerPlayer owner, MobnetAction action) {
        if (!isBehavior(action)) return;
        CompoundTag data = mob.getPersistentData();
        data.putString(NBT_ACTION, action.name());
        data.putUUID(NBT_OWNER, owner.getUUID());
        data.putLong(NBT_EXPIRES, mob.level().getGameTime() + 20L * 300L);
        attachGoal(mob);
    }

    public static void clearBehavior(Mob mob) {
        CompoundTag data = mob.getPersistentData();
        data.putString(NBT_ACTION, MobnetAction.IDLE.name());
        data.remove(NBT_OWNER);
        data.remove(NBT_EXPIRES);
    }

    public static void tickBubble(Mob mob) {
        CompoundTag data = mob.getPersistentData();
        if (!data.getBoolean(BUBBLE_ACTIVE)) return;
        int remaining = data.getInt(BUBBLE_TICKS) - 1;
        if (remaining > 0) {
            data.putInt(BUBBLE_TICKS, remaining);
            return;
        }

        try {
            if (data.getBoolean(OLD_HAS_NAME)) {
                String json = data.getString(OLD_NAME_JSON);
                Component oldName = null;
                try {
                    oldName = Component.Serializer.fromJson(json);
                } catch (RuntimeException exception) {
                    LOGGER.warn("Discarding corrupted saved MOBNET bubble name for entity {}", mob.getUUID());
                }
                mob.setCustomName(oldName == null ? Component.literal("") : oldName);
            } else {
                mob.setCustomName(null);
            }
            mob.setCustomNameVisible(data.getBoolean(OLD_NAME_VISIBLE));
        } finally {
            data.remove(BUBBLE_ACTIVE);
            data.remove(BUBBLE_TICKS);
            data.remove(OLD_NAME_JSON);
            data.remove(OLD_HAS_NAME);
            data.remove(OLD_NAME_VISIBLE);
        }
    }

    private static void showBubble(Mob mob, String text) {
        CompoundTag data = mob.getPersistentData();
        if (!data.getBoolean(BUBBLE_ACTIVE)) {
            Component old = mob.getCustomName();
            data.putBoolean(OLD_HAS_NAME, old != null);
            data.putString(OLD_NAME_JSON, old == null ? "" : Component.Serializer.toJson(old));
            data.putBoolean(OLD_NAME_VISIBLE, mob.isCustomNameVisible());
            data.putBoolean(BUBBLE_ACTIVE, true);
        }
        data.putInt(BUBBLE_TICKS, 80);
        String message = text.length() > 72 ? text.substring(0, 69) + "..." : text;
        mob.setCustomName(Component.literal("§8[§f" + message + "§8]"));
        mob.setCustomNameVisible(true);
    }

    private static Mob selectedMob(ServerPlayer player) {
        CompoundTag data = player.getPersistentData();
        if (!data.hasUUID(ACTIVE_MOB)) {
            player.sendSystemMessage(Component.literal("§cNenhum mob selecionado. Agache e clique com a mão vazia em um mob."));
            return null;
        }
        Entity entity = player.serverLevel().getEntity(data.getUUID(ACTIVE_MOB));
        if (!(entity instanceof Mob mob) || !mob.isAlive()) {
            data.remove(ACTIVE_MOB);
            player.sendSystemMessage(Component.literal("§cO mob selecionado não está mais disponível. Selecione outro."));
            return null;
        }
        if (mob.level() != player.level() || player.distanceToSqr(mob) > 32.0 * 32.0) {
            player.sendSystemMessage(Component.literal("§cVocê precisa estar no mesmo mundo e a até 32 blocos do mob."));
            return null;
        }
        return mob;
    }

    private static MobnetProfile profile(Mob mob) {
        if (memory != null) {
            try {
                return memory.getOrCreateProfile(mob.getUUID(), mob.getType().toString(), mob.getName().getString());
            } catch (SQLException exception) {
                LOGGER.error("Could not load mob profile", exception);
            }
        }
        String type = mob.getType().toString();
        String name = mob.getName().getString();
        MobnetCharacterSheet sheet = MobnetCharacterSheet.defaultFor(type, name, "observador");
        return new MobnetProfile(mob.getUUID(), type, name, "observador", sheet.toPromptText());
    }

    private static int friendship(UUID mob, UUID player) {
        if (memory == null) return 0;
        try {
            return memory.friendship(mob, player);
        } catch (SQLException exception) {
            LOGGER.error("Could not read MOBNET relationship", exception);
            return 0;
        }
    }

    private static int adjustFriendship(UUID mob, UUID player, int delta) {
        if (memory == null) return Math.max(-3, Math.min(3, delta));
        try {
            return memory.adjustFriendship(mob, player, delta);
        } catch (SQLException exception) {
            LOGGER.error("Could not update MOBNET relationship", exception);
            return friendship(mob, player);
        }
    }

    private static List<String> recentMemories(UUID mob, UUID player, int limit) {
        if (memory == null) return List.of();
        try {
            return memory.recentMemories(mob, player, limit);
        } catch (SQLException exception) {
            LOGGER.error("Could not read MOBNET memories", exception);
            return List.of();
        }
    }

    private static List<MobnetChatLine> recentChat(UUID mob, UUID player, int limit) {
        if (memory == null) return List.of();
        try {
            return memory.recentChat(mob, player, limit);
        } catch (SQLException exception) {
            LOGGER.error("Could not read MOBNET conversation history", exception);
            return List.of();
        }
    }

    private static void storeMemory(Mob mob, ServerPlayer player, String speaker, String text) {
        if (memory == null) return;
        try {
            memory.addMemory(mob.getUUID(), player.getUUID(), speaker, text, TOKENIZER.encode(text));
        } catch (SQLException | RuntimeException exception) {
            LOGGER.error("Could not persist MOBNET memory", exception);
        }
    }

    private static void recordExperience(Mob mob, ServerPlayer player, float[] state, MobnetAction action, float reward) {
        if (memory == null) return;
        try {
            memory.recordExperience(mob.getUUID(), player.getUUID(), state, action, reward);
        } catch (SQLException | RuntimeException exception) {
            LOGGER.error("Could not record MOBNET experience", exception);
        }
    }

    private static void broadcastNearby(ServerLevel level, Mob mob, String reply) {
        String name = mob.getName().getString();
        Component component = Component.literal("§b[" + name + "] §f" + reply);
        for (ServerPlayer viewer : level.players()) {
            if (viewer.distanceToSqr(mob) <= 48.0 * 48.0) viewer.sendSystemMessage(component);
        }
    }

    private static boolean isBehavior(MobnetAction action) {
        return action == MobnetAction.FOLLOW || action == MobnetAction.FLEE || action == MobnetAction.ATTACK
                || action == MobnetAction.PROTECT || action == MobnetAction.GUIDE || action == MobnetAction.STAY;
    }

    private static String decisionKey(UUID mob, UUID player) {
        return mob + "/" + player;
    }

    private record Decision(float[] state, MobnetAction action) {}
}
