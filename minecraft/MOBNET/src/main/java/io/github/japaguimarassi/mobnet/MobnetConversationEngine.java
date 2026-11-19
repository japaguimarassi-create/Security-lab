package io.github.japaguimarassi.mobnet;

import java.util.List;
import java.util.Locale;

public final class MobnetConversationEngine {
    private MobnetConversationEngine() {}

    public static String reply(MobnetProfile profile, String playerName, String input,
                               MobnetAction action, int friendship, List<String> recentMemories) {
        String name = profile.displayName() == null || profile.displayName().isBlank() ? "criatura" : profile.displayName();
        String player = playerName == null || playerName.isBlank() ? "amigo" : playerName;
        String text = input == null ? "" : input.toLowerCase(Locale.ROOT);

        if (contains(text, "oi", "olá", "ola", "bom dia", "boa tarde", "boa noite", "e aí", "e ai")) {
            return "Olá, " + player + "! Que bom encontrar você novamente.";
        }
        if (contains(text, "como você está", "como voce esta", "tudo bem", "como vai")) {
            return "Estou bem, " + player + ". Sou " + name + " e estou aprendendo com nossas aventuras.";
        }
        if (contains(text, "obrigado", "obrigada", "valeu")) {
            return friendship > 2 ? "Pode contar comigo, " + player + ". Nossa amizade significa muito." : "De nada! Gosto de conversar com você.";
        }

        return switch (action) {
            case FOLLOW -> "Entendi, " + player + ". Vou acompanhar você.";
            case FLEE -> "Preciso me afastar. Vou procurar um lugar mais seguro.";
            case ATTACK -> "Entendi o desafio. Vou avaliar se consigo enfrentar você.";
            case PROTECT -> "Ficarei atento. Vou tentar proteger você de ameaças.";
            case GUIDE -> "Venha comigo, " + player + ". Vou indicar um caminho.";
            case STAY -> "Tudo bem. Vou ficar aqui e esperar.";
            case IDLE -> "Estou ouvindo você, " + player + ".";
            case TALK -> {
                if (recentMemories != null && recentMemories.size() > 2) {
                    yield "Eu me lembro das nossas conversas, " + player + ". Você disse: \"" + shorten(input, 90) + "\". O que aconteceu depois?";
                }
                if ("curioso".equals(profile.personality())) {
                    yield "Isso despertou minha curiosidade, " + player + ". Conte-me mais sobre \"" + shorten(input, 90) + "\".";
                }
                if ("cauteloso".equals(profile.personality())) {
                    yield "Entendi. Vou pensar com cuidado no que você disse, " + player + ".";
                }
                yield "Estou ouvindo, " + player + ". Ainda estou aprendendo, mas quero entender melhor: \"" + shorten(input, 90) + "\".";
            }
        };
    }

    private static boolean contains(String text, String... terms) {
        for (String term : terms) if (text.contains(term)) return true;
        return false;
    }

    private static String shorten(String text, int max) {
        if (text == null) return "";
        return text.length() <= max ? text : text.substring(0, max - 3) + "...";
    }
}
