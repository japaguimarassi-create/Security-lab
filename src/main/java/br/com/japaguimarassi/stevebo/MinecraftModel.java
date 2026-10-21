package br.com.japaguimarassi.stevebo;

import java.io.BufferedReader;
import java.io.DataInputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.text.Normalizer;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

public final class MinecraftModel {
    private static final int SIZE = 500;
    private static final MinecraftModel INSTANCE = new MinecraftModel();
    private final Map<String, Integer> vocabulary = new HashMap<String, Integer>();
    private final float[][] vectors = new float[SIZE][SIZE];
    private boolean loaded;

    private MinecraftModel() {
        load();
    }

    public static MinecraftModel getInstance() {
        return INSTANCE;
    }

    public boolean isLoaded() {
        return loaded;
    }

    private void load() {
        try {
            InputStream vocabularyStream = getClass().getResourceAsStream("/assets/stevebo/ai/vocab.tsv");
            InputStream weightsStream = getClass().getResourceAsStream("/assets/stevebo/ai/embeddings.bin");
            if (vocabularyStream == null || weightsStream == null) return;

            BufferedReader reader = new BufferedReader(new InputStreamReader(vocabularyStream, "UTF-8"));
            String line;
            while ((line = reader.readLine()) != null) {
                String[] parts = line.split("\\t", 2);
                if (parts.length == 2) vocabulary.put(parts[1], Integer.valueOf(parts[0]));
            }
            reader.close();

            DataInputStream data = new DataInputStream(weightsStream);
            for (int row = 0; row < SIZE; row++) {
                for (int column = 0; column < SIZE; column++) vectors[row][column] = data.readFloat();
            }
            data.close();
            loaded = true;
        } catch (Exception ignored) {
            loaded = false;
        }
    }

    public int findBest(String query, String[] prompts) {
        if (!loaded || prompts == null || prompts.length == 0) return -1;
        double best = -1.0D;
        int bestIndex = -1;
        for (int i = 0; i < prompts.length; i++) {
            double score = similarity(query, prompts[i]);
            if (score > best) {
                best = score;
                bestIndex = i;
            }
        }
        return best >= 0.08D ? bestIndex : -1;
    }

    private double similarity(String first, String second) {
        double[] a = vectorFor(first);
        double[] b = vectorFor(second);
        double dot = 0.0D;
        double lengthA = 0.0D;
        double lengthB = 0.0D;
        for (int i = 0; i < SIZE; i++) {
            dot += a[i] * b[i];
            lengthA += a[i] * a[i];
            lengthB += b[i] * b[i];
        }
        if (lengthA == 0.0D || lengthB == 0.0D) return -1.0D;
        return dot / (Math.sqrt(lengthA) * Math.sqrt(lengthB));
    }

    private double[] vectorFor(String text) {
        double[] result = new double[SIZE];
        List<String> words = tokens(text);
        int count = 0;
        for (String word : words) {
            Integer index = vocabulary.get(word);
            if (index == null) index = vocabulary.get("<unk>");
            if (index == null || index.intValue() < 0 || index.intValue() >= SIZE) continue;
            float[] row = vectors[index.intValue()];
            for (int i = 0; i < SIZE; i++) result[i] += row[i];
            count++;
        }
        if (count > 0) {
            for (int i = 0; i < SIZE; i++) result[i] /= count;
        }
        return result;
    }

    private static List<String> tokens(String text) {
        String normalized = Normalizer.normalize(text == null ? "" : text.toLowerCase(Locale.ROOT), Normalizer.Form.NFD);
        normalized = normalized.replaceAll("\\p{M}", "");
        String[] parts = normalized.split("[^a-z0-9_]+");
        List<String> result = new ArrayList<String>();
        for (String part : parts) if (!part.isEmpty()) result.add(part);
        return result;
    }
}