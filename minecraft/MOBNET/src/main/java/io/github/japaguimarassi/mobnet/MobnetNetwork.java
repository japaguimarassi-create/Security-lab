package io.github.japaguimarassi.mobnet;

import net.minecraft.network.FriendlyByteBuf;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.Mob;
import net.minecraftforge.network.NetworkDirection;
import net.minecraftforge.network.NetworkEvent;
import net.minecraftforge.network.NetworkRegistry;
import net.minecraftforge.network.PacketDistributor;
import net.minecraftforge.network.simple.SimpleChannel;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.function.Supplier;

public final class MobnetNetwork {
    private static final String PROTOCOL = "1";
    public static final SimpleChannel CHANNEL = NetworkRegistry.newSimpleChannel(
            new ResourceLocation(MobnetMod.MODID, "main"),
            () -> PROTOCOL,
            PROTOCOL::equals,
            PROTOCOL::equals
    );
    private static boolean registered;

    private MobnetNetwork() {}

    public static synchronized void register() {
        if (registered) return;
        int id = 0;
        CHANNEL.messageBuilder(OpenChatRequest.class, id++, NetworkDirection.PLAY_TO_SERVER)
                .encoder(OpenChatRequest::encode).decoder(OpenChatRequest::decode).consumerMainThread(OpenChatRequest::handle).add();
        CHANNEL.messageBuilder(SendChatRequest.class, id++, NetworkDirection.PLAY_TO_SERVER)
                .encoder(SendChatRequest::encode).decoder(SendChatRequest::decode).consumerMainThread(SendChatRequest::handle).add();
        CHANNEL.messageBuilder(ConversationSync.class, id++, NetworkDirection.PLAY_TO_CLIENT)
                .encoder(ConversationSync::encode).decoder(ConversationSync::decode).consumerMainThread(ConversationSync::handle).add();
        CHANNEL.messageBuilder(BubbleSync.class, id, NetworkDirection.PLAY_TO_CLIENT)
                .encoder(BubbleSync::encode).decoder(BubbleSync::decode).consumerMainThread(BubbleSync::handle).add();
        registered = true;
    }

    public static void openChat(UUID mobId) {
        CHANNEL.sendToServer(new OpenChatRequest(mobId));
    }

    public static void sendChat(UUID mobId, String message) {
        CHANNEL.sendToServer(new SendChatRequest(mobId, message));
    }

    public static void sendConversation(ServerPlayer player, UUID mobId, String name,
                                        int friendship, List<MobnetChatLine> lines) {
        CHANNEL.send(PacketDistributor.PLAYER.with(() -> player),
                new ConversationSync(mobId, name, friendship, lines));
    }

    public static void sendBubble(Mob mob, String message, int friendship) {
        CHANNEL.send(PacketDistributor.TRACKING_ENTITY_AND_SELF.with(() -> mob),
                new BubbleSync(mob.getUUID(), mob.getName().getString(), message, friendship, 4200));
    }

    public static final class OpenChatRequest {
        private final UUID mobId;

        public OpenChatRequest(UUID mobId) {
            this.mobId = mobId;
        }

        private static void encode(OpenChatRequest message, FriendlyByteBuf buffer) {
            buffer.writeUUID(message.mobId);
        }

        private static OpenChatRequest decode(FriendlyByteBuf buffer) {
            return new OpenChatRequest(buffer.readUUID());
        }

        private static void handle(OpenChatRequest message, Supplier<NetworkEvent.Context> supplier) {
            NetworkEvent.Context context = supplier.get();
            ServerPlayer player = context.getSender();
            if (player != null) MobnetRuntime.openChat(player, message.mobId);
            context.setPacketHandled(true);
        }
    }

    public static final class SendChatRequest {
        private final UUID mobId;
        private final String message;

        public SendChatRequest(UUID mobId, String message) {
            this.mobId = mobId;
            this.message = message == null ? "" : message;
        }

        private static void encode(SendChatRequest message, FriendlyByteBuf buffer) {
            buffer.writeUUID(message.mobId);
            buffer.writeUtf(message.message, 512);
        }

        private static SendChatRequest decode(FriendlyByteBuf buffer) {
            return new SendChatRequest(buffer.readUUID(), buffer.readUtf(512));
        }

        private static void handle(SendChatRequest message, Supplier<NetworkEvent.Context> supplier) {
            NetworkEvent.Context context = supplier.get();
            ServerPlayer player = context.getSender();
            if (player != null) MobnetRuntime.say(player, message.mobId, message.message);
            context.setPacketHandled(true);
        }
    }

    public static final class ConversationSync {
        private final UUID mobId;
        private final String mobName;
        private final int friendship;
        private final List<MobnetChatLine> lines;

        public ConversationSync(UUID mobId, String mobName, int friendship, List<MobnetChatLine> lines) {
            this.mobId = mobId;
            this.mobName = mobName == null ? "Mob" : mobName;
            this.friendship = Math.max(-3, Math.min(3, friendship));
            this.lines = lines == null ? List.of() : List.copyOf(lines.subList(Math.max(0, lines.size() - 40), lines.size()));
        }

        private static void encode(ConversationSync message, FriendlyByteBuf buffer) {
            buffer.writeUUID(message.mobId);
            buffer.writeUtf(message.mobName, 128);
            buffer.writeInt(message.friendship);
            buffer.writeVarInt(message.lines.size());
            for (MobnetChatLine line : message.lines) {
                buffer.writeUtf(line.speaker(), 16);
                buffer.writeUtf(line.message(), 1500);
                buffer.writeLong(line.timestamp());
            }
        }

        private static ConversationSync decode(FriendlyByteBuf buffer) {
            UUID id = buffer.readUUID();
            String name = buffer.readUtf(128);
            int friendship = buffer.readInt();
            int count = Math.min(40, Math.max(0, buffer.readVarInt()));
            List<MobnetChatLine> lines = new ArrayList<>(count);
            for (int i = 0; i < count; i++) {
                lines.add(new MobnetChatLine(buffer.readUtf(16), buffer.readUtf(1500), buffer.readLong()));
            }
            return new ConversationSync(id, name, friendship, lines);
        }

        private static void handle(ConversationSync message, Supplier<NetworkEvent.Context> supplier) {
            MobnetClientState.setConversation(message.mobId, message.mobName, message.friendship, message.lines);
            supplier.get().setPacketHandled(true);
        }
    }

    public static final class BubbleSync {
        private final UUID mobId;
        private final String mobName;
        private final String message;
        private final int friendship;
        private final int durationMillis;

        public BubbleSync(UUID mobId, String mobName, String message, int friendship, int durationMillis) {
            this.mobId = mobId;
            this.mobName = mobName == null ? "Mob" : mobName.length() > 128 ? mobName.substring(0, 128) : mobName;
            String safeMessage = message == null ? "" : message;
            this.message = safeMessage.length() > 512 ? safeMessage.substring(0, 509) + "..." : safeMessage;
            this.friendship = Math.max(-3, Math.min(3, friendship));
            this.durationMillis = Math.max(500, Math.min(15000, durationMillis));
        }

        private static void encode(BubbleSync message, FriendlyByteBuf buffer) {
            buffer.writeUUID(message.mobId);
            buffer.writeUtf(message.mobName, 128);
            buffer.writeUtf(message.message, 512);
            buffer.writeInt(message.friendship);
            buffer.writeVarInt(message.durationMillis);
        }

        private static BubbleSync decode(FriendlyByteBuf buffer) {
            return new BubbleSync(buffer.readUUID(), buffer.readUtf(128), buffer.readUtf(512),
                    buffer.readInt(), buffer.readVarInt());
        }

        private static void handle(BubbleSync message, Supplier<NetworkEvent.Context> supplier) {
            MobnetClientState.setBubble(message.mobId, message.mobName, message.message,
                    message.friendship, message.durationMillis);
            supplier.get().setPacketHandled(true);
        }
    }
}
