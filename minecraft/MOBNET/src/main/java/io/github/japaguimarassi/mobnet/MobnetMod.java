package io.github.japaguimarassi.mobnet;

import net.minecraftforge.fml.ModLoadingContext;
import net.minecraftforge.fml.common.Mod;
import net.minecraftforge.fml.config.ModConfig;

@Mod(MobnetMod.MODID)
public final class MobnetMod {
    public static final String MODID = "mobnet";
    public static final String VERSION = "0.3.1";

    public MobnetMod() {
        ModLoadingContext.get().registerConfig(ModConfig.Type.COMMON, MobnetConfig.SPEC, "mobnet-common.toml");
        MobnetModEvents.LOGGER.info("MOBNET CreatureChat bridge {} loaded", VERSION);
    }
}
