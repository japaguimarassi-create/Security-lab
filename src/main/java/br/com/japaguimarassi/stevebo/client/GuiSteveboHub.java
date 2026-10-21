package br.com.japaguimarassi.stevebo.client;

import br.com.japaguimarassi.stevebo.SteveboMode;
import br.com.japaguimarassi.stevebo.SteveboState;
import net.minecraft.client.gui.GuiButton;
import net.minecraft.client.gui.GuiCreateWorld;
import net.minecraft.client.gui.GuiScreen;
import net.minecraft.util.StatCollector;

public class GuiSteveboHub extends GuiScreen {
    private int selected;
    private final GuiScreen parent;

    public GuiSteveboHub(GuiScreen parent) {
        this.parent = parent;
        this.selected = 0;
    }

    @Override
    public void initGui() {
        buttonList.clear();
        int center = width / 2;
        buttonList.add(new GuiButton(0, center - 102, height / 2 - 8, 38, 20, "<"));
        buttonList.add(new GuiButton(1, center + 64, height / 2 - 8, 38, 20, ">"));
        buttonList.add(new GuiButton(2, center - 100, height / 2 + 28, 200, 20, "Criar mundo e entrar"));
        buttonList.add(new GuiButton(3, center - 100, height / 2 + 54, 200, 20, StatCollector.translateToLocal("gui.cancel")));
    }

    @Override
    protected void actionPerformed(GuiButton button) {
        if (button.id == 0) selected = (selected + SteveboMode.values().length - 1) % SteveboMode.values().length;
        if (button.id == 1) selected = (selected + 1) % SteveboMode.values().length;
        if (button.id == 2) {
            SteveboState.requestWorldCreation(SteveboMode.values()[selected]);
            mc.displayGuiScreen(new GuiCreateWorld(this));
        }
        if (button.id == 3) {
            SteveboState.cancelWorldCreation();
            mc.displayGuiScreen(parent);
        }
    }

    @Override
    public void drawScreen(int mouseX, int mouseY, float partialTicks) {
        drawDefaultBackground();
        drawCenteredString(fontRendererObj, "STEVEBO", width / 2, height / 2 - 68, 0xA9D8FF);
        drawCenteredString(fontRendererObj, "Escolha o destino inicial do Stevebô", width / 2, height / 2 - 48, 0xFFFFFF);
        SteveboMode mode = SteveboMode.values()[selected];
        drawCenteredString(fontRendererObj, mode.label, width / 2, height / 2 - 29, 0xFFFF55);
        drawCenteredString(fontRendererObj, description(mode), width / 2, height / 2 + 3, 0xDDDDDD);
        drawCenteredString(fontRendererObj, "Depois de entrar, clique nas placas Stevebo para viajar.", width / 2, height / 2 + 87, 0xAAAAAA);
        super.drawScreen(mouseX, mouseY, partialTicks);
    }

    private String description(SteveboMode mode) {
        switch (mode) {
            case PVP: return "Arena de pedra preparada para duelo.";
            case SURVIVAL: return "Ponto afastado em terreno natural.";
            case BUILD: return "Plataforma livre para construir.";
            case EXPLORE: return "Regiao afastada para explorar.";
            default: return "Spawn natural do mundo criado.";
        }
    }
}