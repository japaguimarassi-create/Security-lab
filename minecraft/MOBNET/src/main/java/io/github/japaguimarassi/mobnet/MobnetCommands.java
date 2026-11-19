package io.github.japaguimarassi.mobnet;

import com.mojang.brigadier.arguments.FloatArgumentType;
import com.mojang.brigadier.arguments.StringArgumentType;
import net.minecraft.commands.Commands;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.network.chat.Component;
import net.minecraftforge.event.RegisterCommandsEvent;

public final class MobnetCommands {
    private MobnetCommands() {}

    public static void register(RegisterCommandsEvent event) {
        event.getDispatcher().register(Commands.literal("mobnet")
                .then(Commands.literal("say")
                        .then(Commands.argument("message", StringArgumentType.greedyString())
                                .executes(context -> {
                                    ServerPlayer player = context.getSource().getPlayerOrException();
                                    MobnetRuntime.say(player, StringArgumentType.getString(context, "message"));
                                    return 1;
                                })))
                .then(Commands.literal("chat")
                        .then(Commands.argument("message", StringArgumentType.greedyString())
                                .executes(context -> {
                                    ServerPlayer player = context.getSource().getPlayerOrException();
                                    MobnetRuntime.say(player, StringArgumentType.getString(context, "message"));
                                    return 1;
                                })))
                .then(Commands.literal("gift").executes(context -> {
                    MobnetRuntime.gift(context.getSource().getPlayerOrException());
                    return 1;
                }))
                .then(Commands.literal("memory").executes(context -> {
                    MobnetRuntime.showMemory(context.getSource().getPlayerOrException());
                    return 1;
                }))
                .then(Commands.literal("relationship").executes(context -> {
                    MobnetRuntime.showRelationship(context.getSource().getPlayerOrException());
                    return 1;
                }))
                .then(Commands.literal("reward")
                        .then(Commands.argument("value", FloatArgumentType.floatArg(-1.0f, 1.0f))
                                .executes(context -> {
                                    MobnetRuntime.reward(context.getSource().getPlayerOrException(),
                                            FloatArgumentType.getFloat(context, "value"));
                                    return 1;
                                })))
                .then(Commands.literal("stop").executes(context -> {
                    MobnetRuntime.stopBehavior(context.getSource().getPlayerOrException());
                    return 1;
                }))
                .then(Commands.literal("help").executes(context -> {
                    ServerPlayer player = context.getSource().getPlayerOrException();
                    player.sendSystemMessage(Component.literal("§bMOBNET — comandos"));
                    player.sendSystemMessage(Component.literal("§fAgache + clique com a mão vazia em um mob para selecioná-lo."));
                    player.sendSystemMessage(Component.literal("§a/mobnet say <mensagem> §7— conversar"));
                    player.sendSystemMessage(Component.literal("§a/mobnet gift §7— oferecer o item da mão"));
                    player.sendSystemMessage(Component.literal("§a/mobnet memory §7— memórias recentes"));
                    player.sendSystemMessage(Component.literal("§a/mobnet relationship §7— nível de amizade"));
                    player.sendSystemMessage(Component.literal("§a/mobnet reward <-1..1> §7— avaliar a última decisão"));
                    player.sendSystemMessage(Component.literal("§a/mobnet stop §7— parar o comportamento atual"));
                    return 1;
                }))
        );
    }
}
