package io.github.japaguimarassi.mobnet;

import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public record MobnetCharacterSheet(
        String name,
        String personality,
        String speakingStyle,
        String characterClass,
        String skills,
        String likes,
        String dislikes,
        String alignment,
        String background,
        String shortGreeting
) {
    private static final Pattern FIELD = Pattern.compile(
            "(?im)^\\s*[-*]?\\s*%s\\s*:\\s*(.*?)\\s*$"
    );

    public static MobnetCharacterSheet parse(String text, String fallbackName, String fallbackPersonality) {
        String source = text == null ? "" : text;
        String name = value(source, "Name", fallbackName);
        String personality = value(source, "Personality", fallbackPersonality);
        String tone = value(source, "Speaking Style(?: / Tone)?", "Calmo e atento, com fala curta e natural");
        String characterClass = value(source, "Class", "Companheiro");
        String skills = value(source, "Skills", "Explorar, observar e ajudar");
        String likes = value(source, "Likes", "Aventuras, abrigo e amizade");
        String dislikes = value(source, "Dislikes", "Perigo desnecessário e abandono");
        String alignment = value(source, "Alignment", "Neutro e leal");
        String background = value(source, "Background", "Uma criatura que aprendeu a observar os jogadores");
        String greeting = value(source, "Short Greeting", "Olá. Quer conversar ou explorar comigo?");
        return new MobnetCharacterSheet(name, personality, tone, characterClass, skills,
                likes, dislikes, alignment, background, greeting);
    }

    public static MobnetCharacterSheet defaultFor(String entityType, String displayName, String personality) {
        String kind = entityType == null ? "criatura" : entityType.substring(entityType.indexOf(':') + 1).replace('_', ' ');
        String name = displayName == null || displayName.isBlank() ? kind : displayName;
        String greeting = "Olá! Sou " + name + ". O que vamos fazer hoje?";
        return new MobnetCharacterSheet(name, personality, "Fala natural e concisa", "Companheiro",
                "Observar o ambiente, explorar e interagir", "Presentes, segurança e exploração",
                "Ameaças e hostilidade", "Neutro", "Uma criatura de " + kind + " que encontrou um novo amigo",
                greeting);
    }

    public String toPromptText() {
        return "- Name: " + name + "\n"
                + "- Personality: " + personality + "\n"
                + "- Speaking Style / Tone: " + speakingStyle + "\n"
                + "- Class: " + characterClass + "\n"
                + "- Skills: " + skills + "\n"
                + "- Likes: " + likes + "\n"
                + "- Dislikes: " + dislikes + "\n"
                + "- Alignment: " + alignment + "\n"
                + "- Background: " + background + "\n"
                + "- Short Greeting: " + shortGreeting;
    }

    private static String value(String source, String key, String fallback) {
        Matcher matcher = Pattern.compile(String.format(Locale.ROOT, FIELD.pattern(), key), Pattern.CASE_INSENSITIVE).matcher(source);
        if (!matcher.find()) return fallback;
        String value = matcher.group(1).trim();
        return value.isEmpty() ? fallback : value;
    }
}
