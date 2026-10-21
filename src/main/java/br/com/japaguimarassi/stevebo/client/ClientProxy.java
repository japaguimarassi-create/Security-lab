package br.com.japaguimarassi.stevebo.client;

import br.com.japaguimarassi.stevebo.CommonProxy;
import br.com.japaguimarassi.stevebo.EntityStevebo;
import br.com.japaguimarassi.stevebo.SteveboMod;
import cpw.mods.fml.client.registry.RenderingRegistry;
import net.minecraft.client.model.ModelBiped;
import net.minecraft.client.renderer.entity.RenderBiped;
import net.minecraft.util.ResourceLocation;
import net.minecraft.entity.Entity;
import net.minecraftforge.common.MinecraftForge;

public class ClientProxy extends CommonProxy {
    @Override
    public void init() {
        MinecraftForge.EVENT_BUS.register(new SteveboClientEvents());
        RenderingRegistry.registerEntityRenderingHandler(EntityStevebo.class, new RenderBiped(new ModelBiped(), 0.45F) {
            @Override
            protected ResourceLocation getEntityTexture(Entity entity) {
                return new ResourceLocation(SteveboMod.MODID, "textures/entity/stevebo.png");
            }
        });
    }
}