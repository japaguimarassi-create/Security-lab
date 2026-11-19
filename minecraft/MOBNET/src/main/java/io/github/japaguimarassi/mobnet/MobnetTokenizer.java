package io.github.japaguimarassi.mobnet;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class MobnetTokenizer {
    private final List<Merge> merges = new ArrayList<>();
    private final Map<String, Integer> tokenIds = new HashMap<>();
    private final Map<Integer, String> idTokens = new HashMap<>();

    public MobnetTokenizer() {
        train(List.of(
                "Olá, aldeão! Como você está? Vamos explorar a floresta.",
                "Me siga, me proteja e mostre o caminho até a vila.",
                "Minecraft mob jogador amizade memória inventário item bloco",
                "Eu me lembro de você. Obrigado pelo presente.",
                "Não tenha medo. Vou ficar ao seu lado.",
                "zumbi esqueleto creeper lobo gato vaca porco aldeão iron golem",
                "follow flee attack protect guide stay talk",
                "sim não obrigado olá casa vila floresta caverna noite dia"
        ), 160);
    }

    public synchronized void train(List<String> corpus, int maxMerges) {
        merges.clear();
        List<List<String>> sequences = new ArrayList<>();
        for (String text : corpus) {
            if (text == null || text.isEmpty()) continue;
            byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
            List<String> sequence = new ArrayList<>(bytes.length);
            for (byte value : bytes) sequence.add(String.valueOf((char) (value & 0xFF)));
            sequences.add(sequence);
        }

        for (int step = 0; step < Math.max(0, maxMerges); step++) {
            Map<Pair, Integer> counts = new HashMap<>();
            for (List<String> sequence : sequences) {
                for (int i = 0; i + 1 < sequence.size(); i++) {
                    counts.merge(new Pair(sequence.get(i), sequence.get(i + 1)), 1, Integer::sum);
                }
            }
            Pair best = counts.entrySet().stream()
                    .filter(entry -> entry.getValue() >= 2)
                    .max(Comparator.<Map.Entry<Pair, Integer>>comparingInt(Map.Entry::getValue)
                            .thenComparing(entry -> entry.getKey().left())
                            .thenComparing(entry -> entry.getKey().right()))
                    .map(Map.Entry::getKey)
                    .orElse(null);
            if (best == null) break;

            merges.add(new Merge(best.left(), best.right()));
            for (int s = 0; s < sequences.size(); s++) {
                List<String> old = sequences.get(s);
                List<String> next = new ArrayList<>(old.size());
                for (int i = 0; i < old.size(); i++) {
                    if (i + 1 < old.size() && old.get(i).equals(best.left()) && old.get(i + 1).equals(best.right())) {
                        next.add(best.left() + best.right());
                        i++;
                    } else {
                        next.add(old.get(i));
                    }
                }
                sequences.set(s, next);
            }
        }
        rebuildVocabulary();
    }

    private void rebuildVocabulary() {
        tokenIds.clear();
        idTokens.clear();
        for (int i = 0; i < 256; i++) {
            String piece = String.valueOf((char) i);
            tokenIds.put(piece, i);
            idTokens.put(i, piece);
        }
        for (int i = 0; i < merges.size(); i++) {
            String merged = merges.get(i).left() + merges.get(i).right();
            int id = 256 + i;
            tokenIds.put(merged, id);
            idTokens.put(id, merged);
        }
    }

    public synchronized List<Integer> encode(String text) {
        Objects.requireNonNull(text, "text");
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        List<String> pieces = new ArrayList<>(bytes.length);
        for (byte value : bytes) pieces.add(String.valueOf((char) (value & 0xFF)));
        for (Merge merge : merges) {
            List<String> next = new ArrayList<>(pieces.size());
            for (int i = 0; i < pieces.size(); i++) {
                if (i + 1 < pieces.size() && pieces.get(i).equals(merge.left()) && pieces.get(i + 1).equals(merge.right())) {
                    next.add(merge.left() + merge.right());
                    i++;
                } else {
                    next.add(pieces.get(i));
                }
            }
            pieces = next;
        }
        List<Integer> result = new ArrayList<>(pieces.size());
        for (String piece : pieces) {
            Integer id = tokenIds.get(piece);
            if (id == null) {
                for (int i = 0; i < piece.length(); i++) result.add((int) piece.charAt(i));
            } else {
                result.add(id);
            }
        }
        return result;
    }

    public synchronized String decode(List<Integer> tokens) {
        Objects.requireNonNull(tokens, "tokens");
        StringBuilder bytes = new StringBuilder();
        for (Integer token : tokens) {
            if (token == null) throw new IllegalArgumentException("Null token ID");
            String piece = idTokens.get(token);
            if (piece == null) throw new IllegalArgumentException("Unknown token ID: " + token);
            bytes.append(piece);
        }
        byte[] raw = new byte[bytes.length()];
        for (int i = 0; i < bytes.length(); i++) raw[i] = (byte) bytes.charAt(i);
        return new String(raw, StandardCharsets.UTF_8);
    }

    public int vocabularySize() {
        return 256 + merges.size();
    }

    private record Pair(String left, String right) {}
    private record Merge(String left, String right) {}
}
