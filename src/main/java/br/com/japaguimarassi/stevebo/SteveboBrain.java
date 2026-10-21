package br.com.japaguimarassi.stevebo;

public final class SteveboBrain {
    private SteveboBrain() {
    }

    public static String answer(String question) {
        String direct = MinecraftKnowledge.answerForKeywords(question);
        if (direct != null) return direct;

        MinecraftModel model = MinecraftModel.getInstance();
        int match = model.findBest(question, MinecraftKnowledge.PROMPTS);
        if (match >= 0 && match < MinecraftKnowledge.ANSWERS.length) {
            return MinecraftKnowledge.ANSWERS[match];
        }

        return "Ainda não tenho uma resposta confiável para isso. Pergunte sobre mineração, crafting, sobrevivência, mobs, redstone, dimensões, PvP ou mods de Forge 1.7.10.";
    }
}