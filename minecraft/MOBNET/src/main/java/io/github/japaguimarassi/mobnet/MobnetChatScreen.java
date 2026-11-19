package io.github.japaguimarassi.mobnet;

import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;

import java.util.List;
import java.util.UUID;

public final class MobnetChatScreen extends Screen {
    private final UUID mobId;
    private final String initialName;
    private EditBox input;
    private Button sendButton;
    private int panelLeft;
    private int panelTop;

    public MobnetChatScreen(UUID mobId, String mobName) {
        super(Component.literal("MOBNET"));
        this.mobId = mobId;
        this.initialName = mobName == null ? "Mob" : mobName;
    }

    @Override
    protected void init() {
        panelLeft = (width - 330) / 2;
        panelTop = (height - 210) / 2;

        input = new EditBox(font, panelLeft + 12, panelTop + 164, 306, 20, Component.literal(""));
        input.setMaxLength(512);
        input.setHint(Component.literal("Escreva uma mensagem..."));
        input.setResponder(value -> sendButton.active = !value.trim().isEmpty());
        addRenderableWidget(input);
        setInitialFocus(input);

        addRenderableWidget(Button.builder(Component.literal("Fechar"), button -> onClose())
                .bounds(panelLeft + 12, panelTop + 188, 92, 18).build());
        sendButton = Button.builder(Component.literal("Enviar"), button -> sendMessage())
                .bounds(panelLeft + 226, panelTop + 188, 92, 18).build();
        sendButton.active = false;
        addRenderableWidget(sendButton);
    }

    private void sendMessage() {
        String value = input.getValue().trim();
        if (value.isEmpty()) return;
        MobnetNetwork.sendChat(mobId, value);
        input.setValue("");
        setFocused(input);
    }

    @Override
    public boolean keyPressed(int keyCode, int scanCode, int modifiers) {
        if ((keyCode == 257 || keyCode == 335) && input != null && input.isFocused()) {
            sendMessage();
            return true;
        }
        return super.keyPressed(keyCode, scanCode, modifiers);
    }

    @Override
    public void render(GuiGraphics graphics, int mouseX, int mouseY, float partialTick) {
        renderBackground(graphics);
        panelLeft = (width - 330) / 2;
        panelTop = (height - 210) / 2;
        graphics.fill(panelLeft, panelTop, panelLeft + 330, panelTop + 210, 0xEE111820);
        graphics.fill(panelLeft, panelTop, panelLeft + 330, panelTop + 24, 0xFF24465B);
        graphics.drawString(font, "MOBNET  /  " + initialName, panelLeft + 10, panelTop + 8, 0xFFFFFFFF, false);

        MobnetClientState.Conversation conversation = MobnetClientState.conversation(mobId);
        graphics.drawString(font, "Amizade: " + conversation.friendship() + "/3",
                panelLeft + 10, panelTop + 30, 0xFFB9D6E5, false);

        List<MobnetChatLine> lines = conversation.lines();
        int y = panelTop + 48;
        int maxLines = 6;
        int start = Math.max(0, lines.size() - maxLines);
        for (int i = start; i < lines.size(); i++) {
            MobnetChatLine line = lines.get(i);
            boolean assistant = "MOB".equalsIgnoreCase(line.speaker());
            String label = assistant ? initialName : "Você";
            int color = assistant ? 0xFF9ED2F0 : 0xFFE9D49E;
            graphics.drawString(font, label + ":", panelLeft + 12, y, color, false);
            String text = shorten(line.message(), 43);
            graphics.drawString(font, text, panelLeft + 58, y, 0xFFF1F3F5, false);
            y += 17;
        }
        if (lines.isEmpty()) {
            graphics.drawString(font, "Comece a conversa com esta criatura.",
                    panelLeft + 12, panelTop + 64, 0xFFBFC7CE, false);
        }

        super.render(graphics, mouseX, mouseY, partialTick);
    }

    @Override
    public boolean isPauseScreen() {
        return false;
    }

    private static String shorten(String text, int max) {
        if (text == null) return "";
        return text.length() <= max ? text : text.substring(0, max - 3) + "...";
    }
}
