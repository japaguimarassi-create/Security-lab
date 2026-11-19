package io.github.japaguimarassi.mobnet;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MobnetIntentParserTest {
    @Test
    void parsesPortugueseFollowIntent() {
        assertEquals(MobnetAction.FOLLOW, MobnetIntentParser.parse("Venha comigo e me acompanhe"));
    }

    @Test
    void parsesProtectIntent() {
        assertEquals(MobnetAction.PROTECT, MobnetIntentParser.parse("Por favor, me proteja"));
    }

    @Test
    void parsesFleeIntent() {
        assertEquals(MobnetAction.FLEE, MobnetIntentParser.parse("Fuja daqui"));
    }

    @Test
    void unknownTextRemainsConversational() {
        assertEquals(MobnetAction.TALK, MobnetIntentParser.parse("Como está o clima hoje?"));
    }
    @Test
    void negatedCommandDoesNotTriggerBehavior() {
        assertEquals(MobnetAction.TALK, MobnetIntentParser.parse("Não me ataque, quero apenas conversar"));
        assertEquals(MobnetAction.TALK, MobnetIntentParser.parse("Não me siga agora"));
    }

}
