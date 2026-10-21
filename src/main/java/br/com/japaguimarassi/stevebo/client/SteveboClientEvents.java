package br.com.japaguimarassi.stevebo.client;

import br.com.japaguimarassi.stevebo.SteveboState;
import cpw.mods.fml.common.eventhandler.SubscribeEvent;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiCreateWorld;
import net.minecraft.client.gui.GuiMainMenu;
import net.minecraft.client.gui.GuiScreen;
import net.minecraft.client.gui.GuiButton;
import net.minecraftforge.client.event.GuiScreenEvent;

public class SteveboClientEvents {
    private static final int BUTTON_ID = 19421;

    @SubscribeEvent
    public void onInitGui(GuiScreenEvent.InitGuiEvent.Post event) {
        if (!(event.getGui() instanceof GuiMainMenu)) return;
        for (Object object : event.getButtonList()) {
            if (object instanceof GuiButton && ((GuiButton) object).id == BUTTON_ID) return;
        }
        event.getButtonList().add(new GuiButton(BUTTON_ID, 8, 8, 116, 20, "Stevebô"));
    }

    @SubscribeEvent
    public void onAction(GuiScreenEvent.ActionPerformedEvent.Pre event) {
        GuiScreen gui = event.getGui();
        GuiButton button = event.getButton();
        if (gui instanceof GuiMainMenu && button != null && button.id == BUTTON_ID) {
            event.setCanceled(true);
            Minecraft.getMinecraft().displayGuiScreen(new GuiSteveboHub(gui));
            return;
        }
        if (gui instanceof GuiCreateWorld && button != null && button.id == 1) {
            SteveboState.cancelWorldCreation();
        }
    }
}