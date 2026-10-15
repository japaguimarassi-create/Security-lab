import argparse
import hashlib
import json
from pathlib import Path

from tokenizers import Tokenizer, decoders, models, pre_tokenizers, trainers


def train_tokenizer(data_path, output_path, vocab_size):
    if vocab_size < 259:
        raise ValueError("vocab-size must be at least 259 for byte-level BPE and special tokens")
    source = data_path.resolve(strict=True)
    if not source.is_file():
        raise ValueError("data must be a file")
    raw = source.read_bytes()
    if len(raw) < 512:
        raise ValueError("training corpus is too small; expected at least 512 bytes")
    raw.decode("utf-8")

    tokenizer = Tokenizer(models.BPE(unk_token="[UNK]"))
    tokenizer.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    tokenizer.decoder = decoders.ByteLevel()
    trainer = trainers.BpeTrainer(
        vocab_size=vocab_size,
        min_frequency=2,
        special_tokens=["[UNK]", "[BOS]", "[EOS]"],
        initial_alphabet=pre_tokenizers.ByteLevel.alphabet(),
        show_progress=False,
    )
    tokenizer.train([str(source)], trainer)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tokenizer.save(str(output_path))
    return {
        "status": "tokenizer_trained",
        "algorithm": "byte-level BPE",
        "source_bytes": len(raw),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "vocabulary_size": tokenizer.get_vocab_size(),
        "requested_vocabulary_size": vocab_size,
        "output": str(output_path),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("training/data/smoke_corpus.txt"))
    parser.add_argument("--output", type=Path, default=Path("training/checkpoints/kodex-tokenizer.json"))
    parser.add_argument("--vocab-size", type=int, default=512)
    args = parser.parse_args()

    try:
        result = train_tokenizer(args.data, args.output, args.vocab_size)
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise SystemExit(str(error)) from error
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()