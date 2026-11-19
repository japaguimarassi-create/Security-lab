package io.github.japaguimarassi.mobnet;

import net.minecraftforge.fml.common.Mod;

@Mod(MobnetMod.MODID)
public final class MobnetMod {
    public static final String MODID = "mobnet";
    public static final String VERSION = "0.1.0";

    public MobnetMod() {
        MobnetModEvents.LOGGER.info("MOBNET {} loaded", VERSION);
    }
}
