package io.github.japaguimarassi.mobnet;

import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.ai.goal.Goal;
import net.minecraft.world.phys.Vec3;

import java.util.EnumSet;
import java.util.UUID;

public final class MobnetBehaviorGoal extends Goal {
    private final Mob mob;
    private int pathCooldown;
    private LivingEntity previousTarget;

    public MobnetBehaviorGoal(Mob mob) {
        this.mob = mob;
        this.setFlags(EnumSet.of(Flag.MOVE, Flag.LOOK, Flag.TARGET));
    }

    @Override
    public boolean canUse() {
        MobnetAction action = readAction();
        ServerPlayer owner = owner();
        return action != MobnetAction.IDLE && action != MobnetAction.TALK
                && owner != null && owner.isAlive() && owner.level() == mob.level();
    }

    @Override
    public boolean canContinueToUse() {
        return canUse();
    }

    @Override
    public void start() {
        pathCooldown = 0;
        previousTarget = mob.getTarget();
    }

    @Override
    public void stop() {
        mob.getNavigation().stop();
        if (mob.getTarget() != previousTarget) {
            mob.setTarget(previousTarget != null && previousTarget.isAlive() ? previousTarget : null);
        }
        previousTarget = null;
    }

    @Override
    public void tick() {
        MobnetAction action = readAction();
        ServerPlayer owner = owner();
        if (owner == null || owner.level() != mob.level() || !owner.isAlive()) {
            mob.getNavigation().stop();
            return;
        }

        mob.getLookControl().setLookAt(owner, 30.0F, 30.0F);
        double distance = mob.distanceToSqr(owner);
        if (pathCooldown > 0) pathCooldown--;

        switch (action) {
            case FOLLOW -> {
                if (distance > 16.0 && mob.getNavigation().isDone()) mob.getNavigation().moveTo(owner, 1.05);
                if (distance <= 9.0) mob.getNavigation().stop();
            }
            case FLEE -> {
                if (distance < 1024.0 && pathCooldown == 0) {
                    Vec3 away = mob.position().subtract(owner.position()).normalize();
                    if (away.lengthSqr() < 0.001) away = new Vec3(1.0, 0.0, 0.0);
                    Vec3 destination = mob.position().add(away.scale(14.0));
                    mob.getNavigation().moveTo(destination.x, destination.y, destination.z, 1.15);
                    pathCooldown = 30;
                }
            }
            case ATTACK -> {
                if (mob.canAttack(owner)) mob.setTarget(owner);
                else if (distance > 16.0 && distance < 256.0 && mob.getNavigation().isDone()) mob.getNavigation().moveTo(owner, 0.9);
            }
            case PROTECT -> {
                LivingEntity attacker = owner.getLastHurtByMob();
                if (attacker != null && attacker.isAlive() && mob.canAttack(attacker)) {
                    mob.setTarget(attacker);
                } else if (distance > 25.0 && mob.getNavigation().isDone()) {
                    mob.getNavigation().moveTo(owner, 0.95);
                }
            }
            case GUIDE -> {
                if (pathCooldown == 0) {
                    Vec3 direction = owner.getLookAngle().normalize();
                    Vec3 destination = owner.position().add(direction.scale(9.0));
                    mob.getNavigation().moveTo(destination.x, destination.y, destination.z, 0.9);
                    pathCooldown = 40;
                }
            }
            case STAY -> {
                mob.getNavigation().stop();
                mob.setTarget(null);
            }
            default -> mob.getNavigation().stop();
        }
    }

    private MobnetAction readAction() {
        String raw = mob.getPersistentData().getString(MobnetRuntime.NBT_ACTION);
        long expires = mob.getPersistentData().getLong(MobnetRuntime.NBT_EXPIRES);
        if (expires > 0 && mob.level().getGameTime() > expires) {
            MobnetRuntime.clearBehavior(mob);
            return MobnetAction.IDLE;
        }
        try {
            return raw.isBlank() ? MobnetAction.IDLE : MobnetAction.valueOf(raw);
        } catch (IllegalArgumentException ignored) {
            MobnetRuntime.clearBehavior(mob);
            return MobnetAction.IDLE;
        }
    }

    private ServerPlayer owner() {
        if (mob.getServer() == null) return null;
        UUID id = mob.getPersistentData().hasUUID(MobnetRuntime.NBT_OWNER)
                ? mob.getPersistentData().getUUID(MobnetRuntime.NBT_OWNER) : null;
        if (id == null) return null;
        MinecraftServer server = mob.getServer();
        return server.getPlayerList().getPlayer(id);
    }
}
