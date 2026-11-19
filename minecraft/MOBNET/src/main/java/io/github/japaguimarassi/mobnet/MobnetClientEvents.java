package io.github.japaguimarassi.mobnet;

import com.mojang.blaze3d.vertex.PoseStack;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.Font;
import net.minecraft.client.renderer.MultiBufferSource;
import net.minecraft.world.entity.Mob;
import net.minecraftforge.api.distmarker.Dist;
import net.minecraftforge.client.event.RenderLivingEvent;
import net.minecraftforge.event.entity.player.PlayerInteractEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

import java.util.ArrayList;
import java.util.List;

@Mod.EventBusSubscriber(modid = MobnetMod.MODID, bus = Mod.EventBusSubscriber.Bus.FORGE, value = Dist.CLIENT)
public final class MobnetClientEvents {
    private MobnetClientEvents() {}

    @SubscribeEvent
    public static void onMobInteract(PlayerInteractEvent.EntityInteract event) {
        if (!event.getLevel().isClientSide()) return;
        if (!event.getEntity().isShiftKeyDown() || !event.getItemStack().isEmpty()) return;
        if (!(event.getTarget() instanceof Mob mob)) return;

        Minecraft minecraft = Minecraft.getInstance();
        if (minecraft.player == null) return;
        MobnetNetwork.openChat(mob.getUUID());
        minecraft.setScreen(new MobnetChatScreen(mob.getUUID(), mob.getName().getString()));
        event.setCanceled(true);
    }

    @SubscribeEvent
    public static void onRenderMobBubble(RenderLivingEvent.Post<?, ?> event) {
        if (!(event.getEntity() instanceof Mob mob)) return;
        MobnetClientState.Bubble bubble = MobnetClientState.bubble(mob.getUUID());
        if (bubble == null || bubble.message().isBlank()) return;

        Minecraft minecraft = Minecraft.getInstance();
        if (minecraft.player == null || minecraft.player.distanceToSqr(mob) > 24.0 * 24.0) return;

        PoseStack pose = event.getPoseStack();
        pose.pushPose();
        pose.translate(0.0D, mob.getBbHeight() + 0.38D, 0.0D);
        pose.mulPose(minecraft.getEntityRenderDispatcher().cameraOrientation());
        pose.scale(-0.024F, -0.024F, 0.024F);

        Font font = minecraft.font;
        MultiBufferSource buffers = event.getMultiBufferSource();
        List<String> lines = wrap(bubble.message(), 32, 3);
        int maxWidth = 0;
        for (String line : lines) maxWidth = Math.max(maxWidth, font.width(line));
        String name = bubble.mobName() + "  [" + bubble.friendship() + "/3]";
        maxWidth = Math.max(maxWidth, font.width(name));
        int y = -(lines.size() * (font.lineHeight + 2)) - 12;

        font.drawInBatch(name, -font.width(name) / 2.0F, y, 0xFFBFE9FF,
                true, pose.last().pose(), buffers, Font.DisplayMode.NORMAL, 0, event.getPackedLight());
        y += font.lineHeight + 2;
        for (String line : lines) {
            font.drawInBatch(line, -font.width(line) / 2.0F, y, 0xFFFFFFFF,
                    true, pose.last().pose(), buffers, Font.DisplayMode.NORMAL, 0, event.getPackedLight());
            y += font.lineHeight + 2;
        }
        pose.popPose();
    }

    private static List<String> wrap(String text, int maxCharacters, int maxLines) {
        List<String> result = new ArrayList<>();
        StringBuilder line = new StringBuilder();
        for (String word : text.split("\\s+")) {
            if (line.length() > 0 && line.length() + word.length() + 1 > maxCharacters) {
                result.add(line.toString());
                line.setLength(0);
                if (result.size() >= maxLines) break;
            }
            if (line.length() > 0) line.append(' ');
            line.append(word);
        }
        if (result.size() < maxLines && line.length() > 0) result.add(line.toString());
        if (result.size() == maxLines && text.length() > result.stream().mapToInt(String::length).sum()) {
            int last = result.size() - 1;
            String tail = result.get(last);
            result.set(last, tail.length() > maxCharacters - 3 ? tail.substring(0, maxCharacters - 3) + "..." : tail + "...");
        }
        return result;
    }
}
