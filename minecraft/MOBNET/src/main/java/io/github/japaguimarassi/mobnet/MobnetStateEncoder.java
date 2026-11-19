package io.github.japaguimarassi.mobnet;

import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.Mob;

public final class MobnetStateEncoder {
    private MobnetStateEncoder() {}

    public static float[] encode(Mob mob, ServerPlayer player, MobnetAction intent, int friendship) {
        float[] state = new float[MobnetNeuralCore.WIDTH];
        MobnetAction requested = intent == null ? MobnetAction.TALK : intent;
        state[requested.ordinal()] = 1.0f;
        state[16] = ratio(mob.getHealth(), mob.getMaxHealth());
        state[17] = (float) Math.min(1.0, mob.distanceToSqr(player) / 1024.0);
        state[18] = ratio(player.getHealth(), player.getMaxHealth());
        state[19] = Math.max(-1.0f, Math.min(1.0f, friendship / 10.0f));
        state[20] = mob.getType().getCategory().isFriendly() ? 0.0f : 1.0f;
        state[21] = mob.isInWater() ? 1.0f : 0.0f;
        state[22] = mob.level().isNight() ? 1.0f : 0.0f;
        state[23] = mob.level().isRaining() ? 1.0f : 0.0f;
        state[24] = player.isCreative() ? 1.0f : 0.0f;
        state[25] = player.getMainHandItem().isEmpty() ? 0.0f : 1.0f;
        state[26] = mob.onGround() ? 1.0f : 0.0f;
        state[27] = mob.isOnFire() ? 1.0f : 0.0f;
        state[28] = mob.isBaby() ? 1.0f : 0.0f;
        state[29] = Math.min(1.0f, friendship / 10.0f);
        return state;
    }

    private static float ratio(float value, float max) {
        if (!Float.isFinite(value) || !Float.isFinite(max) || max <= 0.0f) return 0.0f;
        return Math.max(0.0f, Math.min(1.0f, value / max));
    }
}
