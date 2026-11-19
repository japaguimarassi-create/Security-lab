package io.github.japaguimarassi.mobnet;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MobnetCharacterSheetTest {
    @Test
    void parsesCharacterFieldsAndUsesFallbacksForMissingValues() {
        String source = """
                - Name: Nilo
                - Personality: Curioso e leal
                - Speaking Style / Tone: Calmo e brincalhão
                - Class: Explorador
                - Likes: Cavernas e mapas
                - Short Greeting: Vamos descobrir algo novo!
                """;
        MobnetCharacterSheet sheet = MobnetCharacterSheet.parse(source, "Mob", "Observador");
        assertEquals("Nilo", sheet.name());
        assertEquals("Curioso e leal", sheet.personality());
        assertEquals("Explorador", sheet.characterClass());
        assertEquals("Cavernas e mapas", sheet.likes());
        assertEquals("Vamos descobrir algo novo!", sheet.shortGreeting());
        assertEquals("Perigo desnecessário e hostilidade", sheet.dislikes());
    }

    @Test
    void defaultSheetAlwaysHasIdentityAndGreeting() {
        MobnetCharacterSheet sheet = MobnetCharacterSheet.defaultFor("minecraft:wolf", "Lobo", "Leal");
        assertEquals("Lobo", sheet.name());
        assertEquals("Leal", sheet.personality());
        assertEquals(true, sheet.shortGreeting().contains("Lobo"));
    }
}
