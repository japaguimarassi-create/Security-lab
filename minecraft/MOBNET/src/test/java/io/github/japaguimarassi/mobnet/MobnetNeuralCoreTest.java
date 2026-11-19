package io.github.japaguimarassi.mobnet;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class MobnetNeuralCoreTest {
    @Test
    void policyUsesNeuralActionFeatures() {
        MobnetNeuralCore core = new MobnetNeuralCore();
        float[] features = new float[MobnetNeuralCore.WIDTH];
        features[MobnetAction.FOLLOW.ordinal()] = 1.0f;
        assertEquals(MobnetAction.FOLLOW, core.chooseAction(features));
    }

    @Test
    void rewardMustBeBounded() {
        MobnetNeuralCore core = new MobnetNeuralCore();
        float[] features = new float[MobnetNeuralCore.WIDTH];
        features[MobnetAction.FOLLOW.ordinal()] = 1.0f;
        assertThrows(IllegalArgumentException.class,
                () -> core.learn(features, MobnetAction.FOLLOW, 2.0f));
    }

    @Test
    void policyHeadCanBeSavedAndReloaded(@TempDir Path tempDir) throws Exception {
        MobnetNeuralCore first = new MobnetNeuralCore();
        float[] features = new float[MobnetNeuralCore.WIDTH];
        features[MobnetAction.PROTECT.ordinal()] = 1.0f;
        first.learn(features, MobnetAction.PROTECT, 0.5f);
        Path model = tempDir.resolve("policy-head.bin");
        first.save(model);

        MobnetNeuralCore second = new MobnetNeuralCore();
        assertTrue(second.load(model));
        assertEquals(first.chooseAction(features), second.chooseAction(features));
    }
}
