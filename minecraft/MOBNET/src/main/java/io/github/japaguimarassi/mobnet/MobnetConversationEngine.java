package io.github.japaguimarassi.mobnet;

import java.util.List;
import java.util.Locale;

public final class MobnetConversationEngine {
    private MobnetConversationEngine() {}

    public static String systemPrompt(MobnetProfile profile, Mob mob, ServerPlayerContext player,
                                      int friendship, List<MobnetChatLine> history) {
        StringBuilder prompt = new StringBuilder();
        prompt.append("Você interpreta uma criatura viva dentro de Minecraft Java. Responda em português brasileiro, ")
                .append("mantenha personalidade consistente, nunca mencione IA, prompt ou sistemas externos e prefira ")
                .append("respostas curtas, naturais e adequadas a uma bolha de fala.\n\n");
        prompt.append("FICHA DO PERSONAGEM:\n").append(profile.characterSheet()).append("\n\n");
        prompt.append("ESTADO ATUAL:\n")
                .append("- Tipo: ").append(mob.entityType()).append("\n")
                .append("- Vida: ").append(Math.round(mob.health())).append("/").append(Math.round(mob.maxHealth())).append("\n")
                .append("- Bioma: ").append(player.biome()).append("\n")
                .append("- Horário: ").append(player.worldTime()).append("\n")
                .append("- Chuva: ").append(player.raining()).append("\n")
                .append("- Jogador: ").append(player.name()).append("\n")
                .append("- Vida do jogador: ").append(Math.round(player.health())).append("\n")
                .append("- Item na mão: ").append(player.heldItem()).append("\n")
                .append("- Distância: ").append(Math.round(player.distance())).append(" blocos\n")
                .append("- Amizade: ").append(friendship).append(" (limite -3 a 3)\n\n");
        prompt.append("COMPORTAMENTOS DISPONÍVEIS — use marcadores somente quando a fala realmente solicitar uma mudança:\n")
                .append("<FRIENDSHIP -3..3>, <FOLLOW>, <UNFOLLOW>, <LEAD>, <UNLEAD>, <FLEE>, <UNFLEE>, ")
                .append("<ATTACK>, <PROTECT>, <UNPROTECT>.\n")
                .append("Não invente vários comportamentos incompatíveis. Não ataque por brincadeira, pergunta ou ameaça ambígua. ")
                .append("Use <FRIENDSHIP> apenas quando a relação realmente mudar. Não coloque os marcadores no meio do texto; ")
                .append("coloque-os ao final. Responda somente com a fala e os marcadores necessários.");
        return prompt.toString();
    }

    public static String characterPrompt(String entityType, String displayName, String personality) {
        return "Você cria personagens originais para criaturas de Minecraft. Gere uma ficha curta, consistente e "
                + "apropriada à espécie indicada. Não crie habilidades que a criatura não possa representar no jogo. "
                + "Responda em português brasileiro, sem introdução e exatamente com estes campos, um por linha:\\n"
                + "- Name: nome curto\\n"
                + "- Personality: traços de personalidade\\n"
                + "- Speaking Style / Tone: estilo de fala\\n"
                + "- Class: papel narrativo\\n"
                + "- Skills: habilidades plausíveis\\n"
                + "- Likes: coisas de que gosta\\n"
                + "- Dislikes: coisas de que não gosta\\n"
                + "- Alignment: alinhamento simples\\n"
                + "- Background: origem curta\\n"
                + "- Short Greeting: saudação em uma frase\\n\\n"
                + "Tipo de entidade: " + entityType + "\\n"
                + "Nome atual: " + displayName + "\\n"
                + "Personalidade-base: " + personality;
    }

    public static String reply(MobnetProfile profile, String playerName, String input,
                               MobnetAction action, int friendship, List<String> recentMemories) {
        String name = profile.displayName() == null || profile.displayName().isBlank() ? "criatura" : profile.displayName();
        String player = playerName == null || playerName.isBlank() ? "amigo" : playerName;
        String text = input == null ? "" : input.toLowerCase(Locale.ROOT);

        if (contains(text, "oi", "olá", "ola", "bom dia", "boa tarde", "boa noite", "e aí", "e ai")) {
            return "Olá, " + player + "! " + profile.personality() + " combina com mais uma aventura.";
        }
        if (contains(text, "como você está", "como voce esta", "tudo bem", "como vai")) {
            return "Estou bem, " + player + ". Sou " + name + " e ainda temos muito para descobrir.";
        }
        if (contains(text, "obrigado", "obrigada", "valeu")) {
            return friendship > 1 ? "Pode contar comigo, " + player + ". Nossa amizade já significa muito." : "De nada! Foi bom receber isso de você.";
        }

        return switch (action) {
            case FOLLOW -> "Entendi, " + player + ". Vou acompanhar seus passos.";
            case FLEE -> "Preciso de espaço. Vou me afastar um pouco.";
            case ATTACK -> "Você quer mesmo lutar? Vou me preparar.";
            case PROTECT -> "Fique perto de mim. Vou prestar atenção nas ameaças.";
            case GUIDE -> "Venha comigo. Vou procurar um caminho seguro.";
            case STAY -> "Certo. Ficarei por aqui até você voltar.";
            case IDLE -> "Estou ouvindo você, " + player + ".";
            case TALK -> {
                if (recentMemories != null && recentMemories.size() > 2) {
                    yield "Lembro de nossas conversas, " + player + ". Ainda penso no que vivemos juntos.";
                }
                if (profile.personality().toLowerCase(Locale.ROOT).contains("curioso")) {
                    yield "Isso me deixou curioso, " + player + ". O que aconteceu depois?";
                }
                if (profile.personality().toLowerCase(Locale.ROOT).contains("cauteloso")) {
                    yield "Entendi. Vou pensar um pouco antes de responder.";
                }
                yield "Estou ouvindo, " + player + ". Quero entender melhor o que você quis dizer.";
            }
        };
    }

    private static boolean contains(String text, String... terms) {
        for (String term : terms) if (text.contains(term)) return true;
        return false;
    }

    public record Mob(String entityType, float health, float maxHealth) {}
    public record ServerPlayerContext(String name, float health, String heldItem, String biome,
                                      String worldTime, boolean raining, double distance) {}
}
