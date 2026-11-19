package io.github.japaguimarassi.mobnet;

import java.text.Normalizer;
import java.util.Locale;

public final class MobnetIntentParser {
    private MobnetIntentParser() {}

    public static MobnetAction parse(String input) {
        if (input == null || input.isBlank()) return MobnetAction.TALK;
        String text = normalize(input);

        if (containsAny(text, "me proteja", "proteja", "me defenda", "defenda", "proteger")) return MobnetAction.PROTECT;
        if (containsAny(text, "fuja", "foge", "afaste", "va embora", "saia daqui", "corra")) return MobnetAction.FLEE;
        if (containsAny(text, "me ataque", "ataque", "lute contra mim", "bata em mim")) return MobnetAction.ATTACK;
        if (containsAny(text, "me guie", "guie", "mostre o caminho", "me leve", "leve me")) return MobnetAction.GUIDE;
        if (containsAny(text, "me siga", "siga me", "acompanhe", "venha comigo", "vem comigo", "me acompanhe")) return MobnetAction.FOLLOW;
        if (containsAny(text, "pare", "fique aqui", "espere", "nao se mova", "fica")) return MobnetAction.STAY;
        return MobnetAction.TALK;
    }

    private static String normalize(String input) {
        String decomposed = Normalizer.normalize(input, Normalizer.Form.NFD);
        return decomposed.replaceAll("\\p{M}+", "").toLowerCase(Locale.ROOT).trim();
    }

    private static boolean containsAny(String text, String... phrases) {
        for (String phrase : phrases) {
            if (text.contains(phrase)) return true;
        }
        return false;
    }
}
