package br.com.japaguimarassi.stevebo;

import java.text.Normalizer;
import java.util.List;
import java.util.Locale;
import net.minecraft.block.Block;
import net.minecraft.init.Blocks;
import net.minecraft.entity.Entity;
import net.minecraft.entity.player.EntityPlayer;
import net.minecraft.tileentity.TileEntity;
import net.minecraft.tileentity.TileEntitySign;
import net.minecraft.util.AxisAlignedBB;
import net.minecraft.util.ChatComponentText;
import net.minecraft.world.World;
import net.minecraft.world.WorldServer;
import net.minecraftforge.event.ServerChatEvent;
import net.minecraftforge.event.entity.EntityJoinWorldEvent;
import net.minecraftforge.event.entity.player.PlayerInteractEvent;
import cpw.mods.fml.common.eventhandler.SubscribeEvent;
import net.minecraftforge.event.world.WorldEvent;

public class SteveboEvents {
    @SubscribeEvent
    public void onPlayerJoinWorld(EntityJoinWorldEvent event) {
        if (event.world.isRemote || !(event.entity instanceof EntityPlayer)) return;
        SteveboMode mode = SteveboState.consumeWorldCreationRequest();
        if (mode == null) return;
        World world = event.world;
        if (!(world instanceof WorldServer)) return;

        try {
            createHub((WorldServer) world, mode, (EntityPlayer) event.entity);
        } catch (Exception exception) {
            ((EntityPlayer) event.entity).addChatMessage(new ChatComponentText("§bStevebô§f: Não consegui preparar todos os destinos. Confira o log do servidor."));
            throw new RuntimeException("Failed to initialize Stevebo world", exception);
        }
    }

    private void createHub(WorldServer world, SteveboMode selected, EntityPlayer joiningPlayer) {
        int baseX = world.getSpawnPoint().posX;
        int baseZ = world.getSpawnPoint().posZ;

        for (SteveboMode mode : SteveboMode.values()) {
            int targetX = baseX + mode.offsetX;
            int targetZ = baseZ + mode.offsetZ;
            int targetY = world.getTopSolidOrLiquidBlock(targetX, targetZ);
            if (mode != SteveboMode.COMMON) {
                Block floor = mode == SteveboMode.PVP ? Blocks.stonebrick : mode == SteveboMode.BUILD ? Blocks.planks : mode == SteveboMode.EXPLORE ? Blocks.cobblestone : Blocks.grass;
                for (int dx = -3; dx <= 3; dx++) {
                    for (int dz = -3; dz <= 3; dz++) world.setBlock(targetX + dx, targetY - 1, targetZ + dz, floor, 0, 3);
                }
            }
            if (mode != SteveboMode.COMMON) placeMarker(world, targetX + 4, targetZ, mode);
        }

        int signIndex = 0;
        for (SteveboMode mode : SteveboMode.values()) {
            int signX = baseX + 2 + signIndex * 2;
            int signZ = baseZ + 2;
            int signY = world.getTopSolidOrLiquidBlock(signX, signZ);
            world.setBlock(signX, signY, signZ, Blocks.fence, 0, 3);
            world.setBlock(signX, signY + 1, signZ, Blocks.standing_sign, 0, 3);
            TileEntity tile = world.getTileEntity(signX, signY + 1, signZ);
            if (tile instanceof TileEntitySign) {
                TileEntitySign sign = (TileEntitySign) tile;
                sign.signText[0] = "Stevebo";
                sign.signText[1] = mode.label;
                sign.signText[2] = "Clique para ir";
                sign.signText[3] = "";
                sign.markDirty();
            }
            signIndex++;
        }

        EntityStevebo bot = new EntityStevebo(world);
        int spawnX = baseX + selected.offsetX;
        int spawnZ = baseZ + selected.offsetZ;
        int spawnY = world.getTopSolidOrLiquidBlock(spawnX, spawnZ);
        bot.setLocationAndAngles(spawnX + 1.5D, spawnY, spawnZ + 1.5D, 0.0F, 0.0F);
        world.spawnEntityInWorld(bot);
        bot.commandFollow(joiningPlayer);
        joiningPlayer.addChatMessage(new ChatComponentText("§bStevebô§f: Mundo preparado. Destino: §e" + selected.label + "§f. Digite §a!stevebo ajuda§f no chat."));
    }

    private void placeMarker(World world, int x, int z, SteveboMode mode) {
        int y = world.getTopSolidOrLiquidBlock(x, z);
        world.setBlock(x, y, z, Blocks.fence, 0, 3);
        world.setBlock(x, y + 1, z, Blocks.standing_sign, 0, 3);
        TileEntity tile = world.getTileEntity(x, y + 1, z);
        if (tile instanceof TileEntitySign) {
            TileEntitySign sign = (TileEntitySign) tile;
            sign.signText[0] = "Stevebo";
            sign.signText[1] = mode.label;
            sign.signText[2] = "Destino";
            sign.signText[3] = "";
            sign.markDirty();
        }
    }

    @SubscribeEvent
    public void onSignClick(PlayerInteractEvent event) {
        if (event.world == null || event.world.isRemote || event.action != PlayerInteractEvent.Action.RIGHT_CLICK_BLOCK) return;
        Block block = event.world.getBlock(event.x, event.y, event.z);
        if (block != Blocks.standing_sign && block != Blocks.wall_sign) return;
        TileEntity tile = event.world.getTileEntity(event.x, event.y, event.z);
        if (!(tile instanceof TileEntitySign)) return;

        TileEntitySign sign = (TileEntitySign) tile;
        if (!"Stevebo".equalsIgnoreCase(sign.signText[0])) return;
        SteveboMode mode = SteveboMode.fromLabel(sign.signText[1]);
        if (mode == null) return;

        World world = event.world;
        int x = world.getSpawnPoint().posX + mode.offsetX;
        int z = world.getSpawnPoint().posZ + mode.offsetZ;
        int y = world.getTopSolidOrLiquidBlock(x, z);
        event.entityPlayer.setPositionAndUpdate(x + 0.5D, y, z + 0.5D);

        EntityStevebo bot = findAnyStevebo(world);
        if (bot != null) {
            bot.setLocationAndAngles(event.entityPlayer.posX + 1.5D, event.entityPlayer.posY, event.entityPlayer.posZ + 0.5D, event.entityPlayer.rotationYaw, 0.0F);
            bot.commandFollow(event.entityPlayer);
        }
        event.entityPlayer.addChatMessage(new ChatComponentText("§bStevebô§f: Você chegou em §e" + mode.label + "§f."));
    }

    private EntityStevebo findAnyStevebo(World world) {
        for (Object entity : world.loadedEntityList) {
            if (entity instanceof EntityStevebo) return (EntityStevebo) entity;
        }
        return null;
    }

    @SubscribeEvent
    public void onServerChat(ServerChatEvent event) {
        EntityPlayer player = event.player;
        if (player == null || player.worldObj == null) return;
        String message = event.message == null ? "" : event.message.trim();
        String normalized = normalize(message);
        String commandPrefix = "!stevebo";
        String lower = normalized.toLowerCase(Locale.ROOT);
        boolean command = lower.equals(commandPrefix) || lower.startsWith(commandPrefix + " ");
        boolean directAddress = lower.startsWith("@stevebo ") || lower.startsWith("stevebo ") || lower.startsWith("stevebo,");
        if (!command && !directAddress) return;

        String query;
        if (command) query = message.length() > commandPrefix.length() ? message.substring(commandPrefix.length()).trim() : "";
        else if (lower.startsWith("@stevebo ")) query = message.substring(9).trim();
        else query = message.length() > 7 ? message.substring(7).replaceFirst("^[, ]+", "").trim() : "";

        EntityStevebo bot = findNearestStevebo(player);
        if (bot == null) {
            event.setCanceled(true);
            player.addChatMessage(new ChatComponentText("§bStevebô§f: Não estou por perto. Crie um mundo pelo botão Stevebô primeiro."));
            return;
        }

        String action = normalize(query).toLowerCase(Locale.ROOT);
        if (action.equals("ajuda") || action.equals("help") || action.isEmpty()) {
            event.setCanceled(true);
            player.addChatMessage(new ChatComponentText("§bStevebô§f: Comandos: §a!stevebo vem§f, §a!stevebo siga§f, §a!stevebo pare§f, §a!stevebo proteja§f, §a!stevebo pvp§f e §a!stevebo status§f. Para perguntar, use §a!stevebo como acho diamante?"));
        } else if (action.equals("vem") || action.equals("venha") || action.equals("siga") || action.equals("me siga")) {
            event.setCanceled(true);
            bot.commandFollow(player);
            player.addChatMessage(new ChatComponentText("§bStevebô§f: Vou acompanhar você."));
        } else if (action.equals("pare") || action.equals("espera") || action.equals("fique")) {
            event.setCanceled(true);
            bot.commandStop();
            player.addChatMessage(new ChatComponentText("§bStevebô§f: Parei e vou ficar aqui."));
        } else if (action.equals("proteja") || action.equals("me proteja") || action.equals("defenda") || action.equals("me defenda")) {
            event.setCanceled(true);
            bot.commandProtect(player);
            player.addChatMessage(new ChatComponentText("§bStevebô§f: Vou tentar afastar mobs hostis perto de você."));
        } else if (action.equals("pvp") || action.equals("duelo") || action.equals("lute comigo")) {
            event.setCanceled(true);
            bot.commandDuel(player);
            player.addChatMessage(new ChatComponentText("§bStevebô§f: Duelo iniciado. Digite §a!stevebo pare§f para encerrar."));
        } else if (action.equals("status")) {
            event.setCanceled(true);
            player.addChatMessage(new ChatComponentText("§bStevebô§f: Estou ativo. Modelo de embeddings: " + (MinecraftModel.getInstance().isLoaded() ? "carregado (250.000 pesos)" : "indisponível; usando a base de regras") + "."));
        } else {
            event.setCanceled(true);
            player.addChatMessage(new ChatComponentText("§bStevebô§f: " + SteveboBrain.answer(query)));
        }
    }

    private EntityStevebo findNearestStevebo(EntityPlayer player) {
        List<EntityStevebo> bots = player.worldObj.getEntitiesWithinAABB(EntityStevebo.class, player.boundingBox.expand(64.0D, 64.0D, 64.0D));
        EntityStevebo closest = null;
        double bestDistance = Double.MAX_VALUE;
        for (EntityStevebo bot : bots) {
            double distance = player.getDistanceSqToEntity(bot);
            if (distance < bestDistance) {
                bestDistance = distance;
                closest = bot;
            }
        }
        return closest;
    }

    private static String normalize(String text) {
        return Normalizer.normalize(text == null ? "" : text.toLowerCase(Locale.ROOT), Normalizer.Form.NFD).replaceAll("\\p{M}", "");
    }
}