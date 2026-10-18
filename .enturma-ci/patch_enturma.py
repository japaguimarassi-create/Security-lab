from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()

def replace_once(path, old, new):
    p = root / path
    text = p.read_text(encoding="utf-8")
    n = text.count(old)
    if n != 1:
        raise SystemExit(f"{path}: expected one patch match, found {n}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")

replace_once("gradle.properties", "mod_version=0.3.0", "mod_version=0.3.1")
replace_once("src/main/java/com/enturma/mod/AIClient.java",
    "public static boolean request(Mob mob, ServerPlayer player, String message, List<Turn> history) {",
    "public static boolean request(Mob mob, ServerPlayer player, String message, List<Turn> history, boolean notifyQueueFull) {")
replace_once("src/main/java/com/enturma/mod/AIClient.java",
    """        } catch (RejectedExecutionException exception) {
            MobConversationHandler.releaseRequest(mobId);
            player.sendSystemMessage(Component.literal("[Enturma AI] Muitas requisições simultâneas; aguarde alguns segundos e tente novamente."));
            return false;
        }""",
    """        } catch (RejectedExecutionException exception) {
            MobConversationHandler.releaseRequest(mobId);
            if (notifyQueueFull) {
                player.sendSystemMessage(Component.literal("[Enturma AI] Muitas requisições simultâneas; aguarde alguns segundos e tente novamente."));
            }
            return false;
        }""")
replace_once("src/main/java/com/enturma/mod/MobConversationHandler.java",
    "if (mob == null || !mob.isAlive() || mob.distanceToSqr(player) > Math.pow(EnturmaConfig.TALK_RADIUS.get(), 2)) {",
    "if (mob == null || !mob.isAlive() || !MobSettings.allows(mob)\n            || mob.distanceToSqr(player) > Math.pow(EnturmaConfig.TALK_RADIUS.get(), 2)) {")
replace_once("src/main/java/com/enturma/mod/MobConversationHandler.java",
    """        for (Mob mob : mobs) {
            UUID mobId = mob.getUUID();
            UUID previousPlayer = ACTIVE_PLAYER_BY_MOB.remove(mobId);
            if (previousPlayer != null) ACTIVE_MOB_BY_PLAYER.remove(previousPlayer, mobId);
            GLOBAL_CHAT_MOBS.add(mobId);
            MEMORY.computeIfAbsent(mobId, ignored -> new java.util.ArrayList<>());
            pruneMemory(mobId);
            mob.lookAt(player, 180.0F, 90.0F);
            if (sendTurn(mob, player, message, false)) submitted++;
        }""",
    """        for (Mob mob : mobs) {
            mob.lookAt(player, 180.0F, 90.0F);
            if (sendTurn(mob, player, message, false, true)) submitted++;
        }""")
replace_once("src/main/java/com/enturma/mod/MobConversationHandler.java",
    """            if (!candidate.equals(currentMobId)) {
                MEMORY.remove(candidate);
                LAST_TALK_TICK.remove(candidate);
                IN_FLIGHT_MOBS.remove(candidate);
                if (MEMORY.size() <= 448) break;
            }""",
    """            if (!candidate.equals(currentMobId) && !IN_FLIGHT_MOBS.contains(candidate)) {
                MEMORY.remove(candidate);
                LAST_TALK_TICK.remove(candidate);
                GLOBAL_CHAT_MOBS.remove(candidate);
                if (MEMORY.size() <= 448) break;
            }""")
p = root / "src/main/java/com/enturma/mod/MobConversationHandler.java"
text = p.read_text(encoding="utf-8")
start = text.find("    private static boolean sendTurn(Mob mob, ServerPlayer player, String message) {")
end = text.find("    public static void releaseRequest(UUID mobId) {", start)
if start < 0 or end < 0:
    raise SystemExit("MobConversationHandler.java: sendTurn section not found")
text = text[:start] + """    private static boolean sendTurn(Mob mob, ServerPlayer player, String message) {
        return sendTurn(mob, player, message, true, false);
    }

    private static boolean sendTurn(Mob mob, ServerPlayer player, String message, boolean notifyBusy, boolean global) {
        UUID mobId = mob.getUUID();
        if (!IN_FLIGHT_MOBS.add(mobId)) {
            if (notifyBusy) player.sendSystemMessage(Component.literal("[Enturma AI] Uma criatura está ocupada; tente novamente em alguns instantes."));
            return false;
        }
        long currentTick = player.serverLevel().getServer().getTickCount();
        Long previous = LAST_TALK_TICK.put(mobId, currentTick);
        if (previous != null && currentTick - previous < 2) {
            IN_FLIGHT_MOBS.remove(mobId);
            if (notifyBusy) player.sendSystemMessage(Component.literal("[Enturma AI] Aguarde um instante antes de falar com essa criatura novamente."));
            return false;
        }
        if (global) GLOBAL_CHAT_MOBS.add(mobId);
        java.util.List<AIClient.Turn> memory = MEMORY.computeIfAbsent(mobId, ignored -> new java.util.ArrayList<>());
        AIClient.Turn pendingTurn = new AIClient.Turn("user", message);
        java.util.List<AIClient.Turn> history;
        synchronized (memory) {
            memory.add(pendingTurn);
            while (memory.size() > 8) memory.remove(0);
            history = java.util.List.copyOf(memory);
        }
        try {
            boolean accepted = AIClient.request(mob, player, message, history, notifyBusy);
            if (!accepted) {
                removePendingTurn(memory, pendingTurn);
                IN_FLIGHT_MOBS.remove(mobId);
                if (global) GLOBAL_CHAT_MOBS.remove(mobId);
            }
            return accepted;
        } catch (RuntimeException exception) {
            removePendingTurn(memory, pendingTurn);
            IN_FLIGHT_MOBS.remove(mobId);
            if (global) GLOBAL_CHAT_MOBS.remove(mobId);
            if (notifyBusy) player.sendSystemMessage(Component.literal("[Enturma AI] Não foi possível iniciar a requisição; tente novamente."));
            return false;
        }
    }

    private static void removePendingTurn(java.util.List<AIClient.Turn> memory, AIClient.Turn pendingTurn) {
        synchronized (memory) {
            for (int i = memory.size() - 1; i >= 0; i--) {
                if (memory.get(i) == pendingTurn) {
                    memory.remove(i);
                    return;
                }
            }
        }
    }

""" + text[end:]
p.write_text(text, encoding="utf-8")
cmds = (root / "src/main/java/com/enturma/mod/EnturmaCommands.java").read_text(encoding="utf-8")
if 'Commands.literal("local")' not in cmds or 'Commands.literal("global")' not in cmds:
    raise SystemExit("Missing /chat local or /chat global command")
if not (root / "src/main/resources/pack.mcmeta").is_file():
    raise SystemExit("Missing pack.mcmeta")
if "notifyQueueFull" not in (root / "src/main/java/com/enturma/mod/AIClient.java").read_text(encoding="utf-8"):
    raise SystemExit("AIClient queue patch failed")
print("Source patches applied and checked.")
