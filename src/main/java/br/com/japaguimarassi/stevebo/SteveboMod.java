package br.com.japaguimarassi.stevebo;

import cpw.mods.fml.common.Mod;
import cpw.mods.fml.common.SidedProxy;
import cpw.mods.fml.common.event.FMLInitializationEvent;
import cpw.mods.fml.common.event.FMLPreInitializationEvent;
import cpw.mods.fml.common.registry.EntityRegistry;
import net.minecraftforge.common.MinecraftForge;

@Mod(modid = SteveboMod.MODID, name = "Stevebo", version = SteveboMod.VERSION, acceptableRemoteVersions = "*")
public class SteveboMod {
    public static final String MODID = "stevebo";
    public static final String VERSION = "0.1.0";

    @SidedProxy(clientSide = "br.com.japaguimarassi.stevebo.client.ClientProxy", serverSide = "br.com.japaguimarassi.stevebo.CommonProxy")
    public static CommonProxy proxy;

    @Mod.EventHandler
    public void preInit(FMLPreInitializationEvent event) {
        EntityRegistry.registerModEntity(EntityStevebo.class, "Stevebo", 1, this, 80, 3, true);
    }

    @Mod.EventHandler
    public void init(FMLInitializationEvent event) {
        MinecraftForge.EVENT_BUS.register(new SteveboEvents());
        proxy.init();
    }
}