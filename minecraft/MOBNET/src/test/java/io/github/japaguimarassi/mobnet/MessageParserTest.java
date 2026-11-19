package io.github.japaguimarassi.mobnet;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class MessageParserTest {
    @Test
    void stripsBehaviorMarkersAndPreservesMessage() {
        ParsedMessage parsed = MessageParser.parseMessage("Come with me! <FOLLOW> <FRIENDSHIP 2>");
        assertEquals("Come with me!", parsed.getCleanedMessage());
        assertEquals("Come with me! <FOLLOW> <FRIENDSHIP 2>", parsed.getOriginalMessage());
        assertEquals(2, parsed.getBehaviors().size());
        assertEquals("FOLLOW", parsed.getBehaviors().get(0).getName());
        assertEquals(2, parsed.getBehaviors().get(1).getArgument());
    }

    @Test
    void parsesAllCreatureChatBehaviorTypes() {
        ParsedMessage parsed = MessageParser.parseMessage(
                "Okay <FOLLOW><UNFOLLOW><LEAD><UNLEAD><FLEE><UNFLEE><ATTACK><PROTECT><UNPROTECT><FRIENDSHIP -3>"
        );
        assertEquals(10, parsed.getBehaviors().size());
        assertEquals("FRIENDSHIP", parsed.getBehaviors().get(9).getName());
        assertEquals(-3, parsed.getBehaviors().get(9).getArgument());
    }

    @Test
    void malformedAndUnknownTagsRemainVisible() {
        ParsedMessage parsed = MessageParser.parseMessage("Hello <FLY> <FRIENDSHIP nope>");
        assertEquals("Hello <FLY> <FRIENDSHIP nope>", parsed.getCleanedMessage());
        assertTrue(parsed.getBehaviors().isEmpty());
    }

    @Test
    void nullInputIsSafe() {
        assertEquals("", MessageParser.parseMessage(null).getCleanedMessage());
    }
}
