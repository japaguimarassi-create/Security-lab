package io.github.japaguimarassi.mobnet;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class MobnetTokenizerTest {
    @Test
    void byteBpeRoundTripsPortugueseAndMinecraftTerms() {
        MobnetTokenizer tokenizer = new MobnetTokenizer();
        String source = "Olá, aldeão! Vamos explorar a floresta e proteger a vila.";
        List<Integer> encoded = tokenizer.encode(source);
        assertEquals(source, tokenizer.decode(encoded));
        assertTrue(encoded.size() > 0);
    }
}
