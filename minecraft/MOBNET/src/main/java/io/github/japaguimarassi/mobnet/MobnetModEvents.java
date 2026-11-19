package io.github.japaguimarassi.mobnet;

import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.entity.Mob;
import net.minecraftforge.event.RegisterCommandsEvent;
import net.minecraftforge.event.entity.EntityJoinLevelEvent;
import net.minecraftforge.event.entity.EntityLeaveLevelEvent;
import net.minecraftforge.event.entity.living.LivingEvent;
import net.minecraftforge.event.entity.player.PlayerInteractEvent;
import net.minecraftforge.event.server.ServerStartingEvent;
import net.minecraftforge.event.server.ServerStoppingEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@Mod.EventBusSubscriber(modid = MobnetMod.MODID, bus = Mod.EventBusSubscriber.Bus.FORGE)
public final class MobnetModEvents {
    public static final Logger LOGGER = LoggerFactory.getLogger(MobnetMod.MODID);

    private MobnetModEvents() {}

    @SubscribeEvent
    public static void onServerStarting(ServerStartingEvent event) {
        MobnetRuntime.start(event.getServer());
    }

    @SubscribeEvent
    public static void onServerStopping(ServerStoppingEvent event) {
        MobnetRuntime.stop();
    }

    @SubscribeEvent
    public static void onRegisterCommands(RegisterCommandsEvent event) {
        MobnetCommands.register(event);
    }

    @SubscribeEvent
    public static void onEntityInteractSpecific(PlayerInteractEvent.EntityInteractSpecific event) {
        selectMob(event);
    }

    @SubscribeEvent
    public static void onEntityInteract(PlayerInteractEvent.EntityInteract event) {
        selectMob(event);
    }

    private static void selectMob(PlayerInteractEvent event) {
        if (event.getLevel().isClientSide()) return;
        if (!(event.getEntity() instanceof ServerPlayer player)) return;
        if (!player.isShiftKeyDown() || !event.getItemStack().isEmpty()) return;
        if (!(event instanceof PlayerInteractEvent.EntityInteract) &&
                !(event instanceof PlayerInteractEvent.EntityInteractSpecific)) return;
        net.minecraft.world.entity.Entity target;
        if (event instanceof PlayerInteractEvent.EntityInteract specific) target = specific.getTarget();
        else target = ((PlayerInteractEvent.EntityInteractSpecific) event).getTarget();
        if (!(target instanceof Mob mob)) return;

        MobnetRuntime.select(player, mob);
        event.setCancellationResult(InteractionResult.SUCCESS);
        event.setCanceled(true);
    }

    @SubscribeEvent
    public static void onEntityJoin(EntityJoinLevelEvent event) {
        if (event.getLevel().isClientSide()) return;
        if (event.getEntity() instanceof Mob mob) {
            String action = mob.getPersistentData().getString(MobnetRuntime.NBT_ACTION);
            if (!action.isBlank() && !action.equals(MobnetAction.IDLE.name()) && !action.equals(MobnetAction.TALK.name())) {
                MobnetRuntime.attachGoal(mob);
            }
        }
    }

    @SubscribeEvent
    public static void onEntityLeave(EntityLeaveLevelEvent event) {
        if (event.getEntity() instanceof Mob mob) MobnetRuntime.detachGoal(mob);
    }

    @SubscribeEvent
    public static void onLivingTick(LivingEvent.LivingTickEvent event) {
        if (event.getEntity().level().isClientSide()) return;
        if (event.getEntity() instanceof Mob mob) MobnetRuntime.tickBubble(mob);
    }
}
