package io.github.japaguimarassi.mobnet;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Random;
import java.util.zip.CRC32;

public final class MobnetNeuralCore {
    public static final int LAYERS = 12;
    public static final int WIDTH = 678;
    public static final int BOTTLENECK = 64;
    private static final int ACTIONS = MobnetAction.values().length;
    private static final int MAGIC = 0x4D4F424E;
    private static final int FORMAT_VERSION = 1;
    private static final float RESIDUAL_SCALE = 0.02f;
    private static final float LEARNING_RATE = 0.20f;

    private final float[][][] down = new float[LAYERS][BOTTLENECK][WIDTH];
    private final float[][][] up = new float[LAYERS][WIDTH][BOTTLENECK];
    private final float[][] policyHead = new float[ACTIONS][WIDTH];
    private final float[] bias = new float[ACTIONS];

    public MobnetNeuralCore() {
        initializeBackbone();
        initializeActionHead();
    }

    private void initializeBackbone() {
        Random random = new Random(0x4D4F424E455431L);
        for (int layer = 0; layer < LAYERS; layer++) {
            for (int b = 0; b < BOTTLENECK; b++) {
                for (int i = 0; i < WIDTH; i++) down[layer][b][i] = (float) (random.nextGaussian() * 0.004);
            }
            for (int i = 0; i < WIDTH; i++) {
                for (int b = 0; b < BOTTLENECK; b++) up[layer][i][b] = (float) (random.nextGaussian() * 0.004);
            }
        }
    }

    private void initializeActionHead() {
        for (MobnetAction action : MobnetAction.values()) {
            policyHead[action.ordinal()][action.ordinal()] = 1.0f;
        }
    }

    public synchronized MobnetAction chooseAction(float[] input) {
        validateState(input);
        float[] state = input.clone();
        float[] hidden = new float[BOTTLENECK];

        for (int layer = 0; layer < LAYERS; layer++) {
            for (int b = 0; b < BOTTLENECK; b++) {
                float sum = 0.0f;
                for (int i = 0; i < WIDTH; i++) sum += down[layer][b][i] * state[i];
                hidden[b] = Math.max(0.0f, sum);
            }
            for (int i = 0; i < WIDTH; i++) {
                float projected = 0.0f;
                for (int b = 0; b < BOTTLENECK; b++) projected += up[layer][i][b] * hidden[b];
                state[i] = clamp(state[i] + RESIDUAL_SCALE * (float) Math.tanh(projected), -4.0f, 4.0f);
            }
        }

        int bestIndex = MobnetAction.IDLE.ordinal();
        float bestScore = Float.NEGATIVE_INFINITY;
        for (int action = 0; action < ACTIONS; action++) {
            float score = bias[action];
            for (int i = 0; i < WIDTH; i++) score += policyHead[action][i] * state[i];
            if (score > bestScore) {
                bestScore = score;
                bestIndex = action;
            }
        }
        return MobnetAction.values()[bestIndex];
    }

    public synchronized void learn(float[] input, MobnetAction action, float reward) {
        validateState(input);
        if (action == null) throw new IllegalArgumentException("Action is required");
        if (!Float.isFinite(reward) || reward < -1.0f || reward > 1.0f) {
            throw new IllegalArgumentException("Reward must be finite and between -1 and 1");
        }
        float rate = LEARNING_RATE * reward;
        for (int i = 0; i < WIDTH; i++) {
            policyHead[action.ordinal()][i] = clamp(policyHead[action.ordinal()][i] + rate * input[i], -4.0f, 4.0f);
        }
        bias[action.ordinal()] = clamp(bias[action.ordinal()] + rate * 0.25f, -2.0f, 2.0f);
    }

    public synchronized void save(Path destination) throws IOException {
        Path parent = destination.toAbsolutePath().getParent();
        if (parent != null) Files.createDirectories(parent);

        ByteArrayOutputStream buffer = new ByteArrayOutputStream(ACTIONS * WIDTH * 4 + 128);
        try (DataOutputStream out = new DataOutputStream(buffer)) {
            out.writeInt(MAGIC);
            out.writeInt(FORMAT_VERSION);
            out.writeInt(LAYERS);
            out.writeInt(WIDTH);
            out.writeInt(BOTTLENECK);
            out.writeInt(ACTIONS);
            for (int action = 0; action < ACTIONS; action++) {
                out.writeFloat(bias[action]);
                for (int i = 0; i < WIDTH; i++) out.writeFloat(policyHead[action][i]);
            }
        }
        byte[] payload = buffer.toByteArray();
        CRC32 crc = new CRC32();
        crc.update(payload);
        ByteArrayOutputStream complete = new ByteArrayOutputStream(payload.length + 8);
        complete.write(payload);
        try (DataOutputStream out = new DataOutputStream(complete)) {
            out.writeLong(crc.getValue());
        }

        Path temporary = destination.resolveSibling(destination.getFileName() + ".tmp");
        Files.write(temporary, complete.toByteArray());
        try {
            Files.move(temporary, destination, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
        } catch (AtomicMoveNotSupportedException ignored) {
            Files.move(temporary, destination, StandardCopyOption.REPLACE_EXISTING);
        }
    }

    public synchronized boolean load(Path source) {
        if (!Files.isRegularFile(source)) return false;
        try {
            byte[] complete = Files.readAllBytes(source);
            if (complete.length < 8) return false;
            int payloadLength = complete.length - 8;
            CRC32 crc = new CRC32();
            crc.update(complete, 0, payloadLength);
            long storedCrc;
            try (DataInputStream tail = new DataInputStream(new ByteArrayInputStream(complete, payloadLength, 8))) {
                storedCrc = tail.readLong();
            }
            if (crc.getValue() != storedCrc) return false;

            try (DataInputStream in = new DataInputStream(new ByteArrayInputStream(complete, 0, payloadLength))) {
                if (in.readInt() != MAGIC || in.readInt() != FORMAT_VERSION) return false;
                if (in.readInt() != LAYERS || in.readInt() != WIDTH || in.readInt() != BOTTLENECK || in.readInt() != ACTIONS) return false;
                float[][] loadedHead = new float[ACTIONS][WIDTH];
                float[] loadedBias = new float[ACTIONS];
                for (int action = 0; action < ACTIONS; action++) {
                    loadedBias[action] = in.readFloat();
                    if (!Float.isFinite(loadedBias[action])) return false;
                    for (int i = 0; i < WIDTH; i++) {
                        loadedHead[action][i] = in.readFloat();
                        if (!Float.isFinite(loadedHead[action][i])) return false;
                    }
                }
                if (in.available() != 0) return false;
                for (int action = 0; action < ACTIONS; action++) {
                    bias[action] = loadedBias[action];
                    System.arraycopy(loadedHead[action], 0, policyHead[action], 0, WIDTH);
                }
            }
            return true;
        } catch (IOException | RuntimeException exception) {
            return false;
        }
    }

    private static void validateState(float[] input) {
        if (input == null || input.length != WIDTH) {
            throw new IllegalArgumentException("MOBNET state must contain exactly " + WIDTH + " values");
        }
        for (float value : input) {
            if (!Float.isFinite(value)) throw new IllegalArgumentException("State contains a non-finite value");
        }
    }

    private static float clamp(float value, float min, float max) {
        return Math.max(min, Math.min(max, value));
    }
}
