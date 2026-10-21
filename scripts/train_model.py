from collections import Counter
from pathlib import Path
import re
import unicodedata
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "data" / "minecraft_corpus.txt"
ASSET_ROOT = ROOT / "src" / "main" / "resources" / "assets" / "stevebo"
AI_ROOT = ASSET_ROOT / "ai"
TEXTURE_ROOT = ASSET_ROOT / "textures" / "entity"
VOCAB_SIZE = 500
DIMENSIONS = 500
EPOCHS = 4
LEARNING_RATE = 0.025
NEGATIVE_SAMPLES = 2
SEED = 17010


def normalize(text):
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()


def tokenize(text):
    return re.findall(r"[a-z0-9_]+", normalize(text))


def generate_skin(path):
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    def box(x1, y1, x2, y2, color):
        if x2 <= x1 or y2 <= y1:
            return
        draw.rectangle((x1, y1, x2 - 1, y2 - 1), fill=color)

    skin = (167, 116, 83, 255)
    shadow = (105, 68, 55, 255)
    hair = (28, 24, 36, 255)
    hair_light = (49, 38, 62, 255)
    hoodie = (22, 20, 30, 255)
    hoodie_light = (43, 39, 58, 255)
    purple = (132, 69, 224, 255)
    purple_light = (188, 131, 255, 255)
    pants = (27, 25, 40, 255)
    shoes = (210, 210, 220, 255)

    box(8, 0, 16, 8, hair)
    box(16, 0, 24, 8, shadow)
    box(0, 8, 8, 16, hair)
    box(8, 8, 16, 16, skin)
    box(16, 8, 24, 16, skin)
    box(24, 8, 32, 16, hair)
    box(8, 0, 16, 3, hair_light)
    box(8, 8, 16, 10, hair)
    box(9, 11, 11, 12, purple)
    box(13, 11, 15, 12, purple)
    box(9, 11, 10, 11, (245, 245, 255, 255))
    box(13, 11, 14, 11, (245, 245, 255, 255))
    box(10, 14, 14, 15, shadow)

    box(40, 0, 48, 8, hair)
    box(48, 0, 56, 8, hoodie)
    box(32, 8, 40, 16, hair)
    box(40, 8, 48, 16, hair_light)
    box(48, 8, 56, 16, hoodie)
    box(56, 8, 64, 16, hair)
    box(40, 8, 42, 11, purple)
    box(40, 7, 42, 9, purple_light)
    box(45, 8, 47, 11, purple)
    box(45, 7, 47, 9, purple_light)

    box(20, 16, 28, 20, hoodie)
    box(16, 20, 20, 32, hoodie)
    box(20, 20, 28, 32, hoodie_light)
    box(28, 20, 32, 32, hoodie)
    box(32, 20, 40, 32, hoodie)
    box(20, 32, 28, 36, hoodie)
    box(20, 36, 28, 48, hoodie)
    box(16, 36, 20, 48, hoodie)
    box(28, 36, 32, 48, hoodie)
    box(32, 36, 40, 48, hoodie)
    box(20, 38, 28, 39, hoodie_light)
    box(21, 40, 23, 43, purple)
    box(22, 40, 25, 41, purple)
    box(23, 42, 26, 44, purple)
    box(24, 43, 27, 45, hoodie)
    box(21, 44, 23, 45, hoodie)
    box(24, 46, 27, 47, hoodie_light)
    box(21, 45, 24, 46, hoodie_light)
    box(20, 47, 28, 48, hoodie)

    box(44, 16, 48, 20, hoodie)
    box(40, 20, 44, 32, hoodie)
    box(44, 20, 48, 32, hoodie_light)
    box(48, 20, 52, 32, hoodie)
    box(52, 20, 56, 32, hoodie)
    box(44, 32, 48, 36, hoodie)
    box(44, 36, 48, 48, hoodie)
    box(40, 36, 44, 48, hoodie)
    box(48, 36, 52, 48, hoodie)
    box(52, 36, 56, 48, hoodie)
    box(44, 39, 48, 40, purple)
    box(36, 48, 40, 52, hoodie)
    box(32, 52, 36, 64, hoodie)
    box(36, 52, 40, 64, hoodie_light)
    box(40, 52, 44, 64, hoodie)
    box(44, 52, 48, 64, hoodie)

    box(4, 16, 8, 20, pants)
    box(0, 20, 4, 32, pants)
    box(4, 20, 8, 32, pants)
    box(8, 20, 12, 32, pants)
    box(12, 20, 16, 32, pants)
    box(4, 32, 8, 36, pants)
    box(4, 36, 8, 48, pants)
    box(0, 36, 4, 48, pants)
    box(8, 36, 12, 48, pants)
    box(12, 36, 16, 48, pants)
    box(20, 48, 24, 52, pants)
    box(16, 52, 20, 64, pants)
    box(20, 52, 24, 64, pants)
    box(24, 52, 28, 64, pants)
    box(28, 52, 32, 64, pants)
    box(20, 60, 24, 64, shoes)
    box(4, 44, 8, 48, shoes)
    box(4, 24, 8, 25, hoodie_light)
    box(20, 56, 24, 57, hoodie_light)

    TEXTURE_ROOT.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")


def update_pair(vectors, left, right, label, learning_rate):
    first = vectors[left].copy()
    second = vectors[right].copy()
    score = float(np.clip(np.dot(first, second), -8.0, 8.0))
    probability = 1.0 / (1.0 + np.exp(-score))
    gradient = (label - probability) * learning_rate
    vectors[left] += gradient * second
    vectors[right] += gradient * first


def train():
    text = CORPUS.read_text(encoding="utf-8")
    words = tokenize(text)
    counts = Counter(words)
    vocab = ["<unk>"] + [word for word, _ in counts.most_common(VOCAB_SIZE - 1) if word != "<unk>"]
    vocab = vocab[:VOCAB_SIZE]
    while len(vocab) < VOCAB_SIZE:
        vocab.append("__pad_" + str(len(vocab)))

    index = {word: i for i, word in enumerate(vocab)}
    sequence = [index.get(word, 0) for word in words]
    if len(sequence) < 20:
        raise RuntimeError("Minecraft corpus is too small to train the model.")

    rng = np.random.default_rng(SEED)
    vectors = rng.normal(0.0, 0.04, size=(VOCAB_SIZE, DIMENSIONS)).astype(np.float32)
    frequencies = np.array([max(counts.get(word, 0), 1) for word in vocab], dtype=np.float64)
    for i, word in enumerate(vocab):
        if word.startswith("__pad_"):
            frequencies[i] = 0.0001
    probabilities = np.power(frequencies, 0.75)
    probabilities /= probabilities.sum()

    for epoch in range(EPOCHS):
        learning_rate = LEARNING_RATE * (1.0 - 0.12 * epoch)
        for position, center in enumerate(sequence):
            for distance in (1, 2):
                for other_position in (position - distance, position + distance):
                    if other_position < 0 or other_position >= len(sequence):
                        continue
                    context = sequence[other_position]
                    if center == context:
                        continue
                    update_pair(vectors, center, context, 1.0, learning_rate)
                    for _ in range(NEGATIVE_SAMPLES):
                        negative = int(rng.choice(VOCAB_SIZE, p=probabilities))
                        if negative != center and negative != context:
                            update_pair(vectors, center, negative, 0.0, learning_rate)

    AI_ROOT.mkdir(parents=True, exist_ok=True)
    vectors.astype(">f4").tofile(AI_ROOT / "embeddings.bin")
    with (AI_ROOT / "vocab.tsv").open("w", encoding="utf-8", newline="\n") as output:
        for i, word in enumerate(vocab):
            output.write(str(i) + "\t" + word + "\n")
    (AI_ROOT / "model-info.txt").write_text(
        "architecture=single shared embedding matrix\n"
        "vocabulary_size=500\n"
        "embedding_dimension=500\n"
        "trainable_parameters=250000\n"
        "objective=skip-gram with negative sampling\n"
        "corpus=data/minecraft_corpus.txt\n"
        "epochs=" + str(EPOCHS) + "\n",
        encoding="utf-8"
    )
    generate_skin(TEXTURE_ROOT / "stevebo.png")
    print("Trained exactly 250000 embedding weights from", len(words), "tokens and wrote the Stevebo texture.")


if __name__ == "__main__":
    train()
