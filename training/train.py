import argparse
import hashlib
import json
import random
import time
from pathlib import Path

import torch

from kodex_lm import KodexLanguageModel, ModelConfig, encode_bytes


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("training/data/smoke_corpus.txt"))
    parser.add_argument("--tokenizer", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=Path("training/checkpoints/kodex-smoke.pt"))
    parser.add_argument("--steps", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--block-size", type=int, default=128)
    parser.add_argument("--layers", type=int, default=4)
    parser.add_argument("--heads", type=int, default=4)
    parser.add_argument("--embedding-size", type=int, default=128)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--eval-interval", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    return parser.parse_args()


def sample_batch(data, batch_size, block_size, device):
    if data.numel() <= block_size + 1:
        raise ValueError("Training split is too short for block_size")
    starts = torch.randint(0, data.numel() - block_size - 1, (batch_size,), device=device)
    inputs = torch.stack([data[start:start + block_size] for start in starts])
    targets = torch.stack([data[start + 1:start + block_size + 1] for start in starts])
    return inputs, targets


@torch.no_grad()
def estimate_loss(model, train_data, val_data, batch_size, block_size, device, batches=4):
    model.eval()
    estimates = {}
    for name, data in (("train", train_data), ("validation", val_data)):
        values = []
        for _ in range(batches):
            inputs, targets = sample_batch(data, batch_size, block_size, device)
            _, loss = model(inputs, targets)
            values.append(float(loss.item()))
        estimates[name] = sum(values) / len(values)
    model.train()
    return estimates


def main():
    args = parse_args()
    if args.steps < 1 or args.batch_size < 1 or args.eval_interval < 1:
        raise SystemExit("steps, batch-size and eval-interval must be positive")

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    if args.device == "cuda" and not torch.cuda.is_available():
        raise SystemExit("CUDA was requested but is not available")
    device = torch.device("cuda" if args.device == "cuda" or (args.device == "auto" and torch.cuda.is_available()) else "cpu")

    data_path = args.data.resolve()
    if not data_path.is_file():
        raise SystemExit(f"Training data file not found: {data_path}")
    raw_text = data_path.read_text(encoding="utf-8")
    raw_bytes = raw_text.encode("utf-8")
    if len(raw_bytes) < 512:
        raise SystemExit("Training corpus is too small; expected at least 512 UTF-8 bytes")
    corpus_sha256 = hashlib.sha256(raw_bytes).hexdigest()

    tokenizer_json = None
    if args.tokenizer is not None:
        tokenizer_path = args.tokenizer.resolve()
        if not tokenizer_path.is_file():
            raise SystemExit(f"Tokenizer file not found: {tokenizer_path}")
        try:
            from tokenizers import Tokenizer
        except ImportError as error:
            raise SystemExit("Install the tokenizers package to use a BPE tokenizer") from error
        tokenizer = Tokenizer.from_file(str(tokenizer_path))
        encoded = tokenizer.encode(raw_text)
        ids = encoded.ids
        vocab_size = tokenizer.get_vocab_size()
        tokenizer_kind = "byte-level-bpe"
        tokenizer_json = tokenizer.to_str()
    else:
        ids = encode_bytes(raw_text)
        vocab_size = 256
        tokenizer_kind = "utf8-bytes"

    token_ids = torch.tensor(ids, dtype=torch.long)
    split_index = int(token_ids.numel() * 0.9)
    train_data = token_ids[:split_index].to(device)
    val_data = token_ids[split_index:].to(device)
    if len(train_data) <= args.block_size + 1 or len(val_data) <= args.block_size + 1:
        raise SystemExit("Train or validation split is too short; add approved text or reduce block-size")

    config = ModelConfig(
        vocab_size=vocab_size,
        block_size=args.block_size,
        n_layer=args.layers,
        n_head=args.heads,
        n_embd=args.embedding_size,
    )
    model = KodexLanguageModel(config).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    print(json.dumps({
        "status": "training_started",
        "device": str(device),
        "corpus_bytes": len(raw_bytes),
        "corpus_sha256": corpus_sha256,
        "training_tokens": int(train_data.numel()),
        "validation_tokens": int(val_data.numel()),
        "tokenizer_kind": tokenizer_kind,
        "vocabulary_size": vocab_size,
        "parameter_count": model.parameter_count(),
        "config": model.config_dict(),
        "pretrained_weights": False,
        "seed": args.seed,
    }, sort_keys=True))

    started = time.time()
    for step in range(1, args.steps + 1):
        inputs, targets = sample_batch(train_data, args.batch_size, config.block_size, device)
        _, loss = model(inputs, targets)
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()

        if step == 1 or step % args.eval_interval == 0 or step == args.steps:
            metrics = estimate_loss(
                model, train_data, val_data, args.batch_size, config.block_size, device
            )
            print(json.dumps({
                "step": step,
                "steps": args.steps,
                "train_loss": metrics["train"],
                "validation_loss": metrics["validation"],
                "elapsed_seconds": round(time.time() - started, 2),
            }, sort_keys=True))

    payload = {
        "schema_version": 1,
        "model_name": "KodexScratchLM",
        "config": model.config_dict(),
        "model_state_dict": model.state_dict(),
        "tokenizer_kind": tokenizer_kind,
        "tokenizer_json": tokenizer_json,
        "training": {
            "steps": args.steps,
            "seed": args.seed,
            "device": str(device),
            "data_file": str(data_path),
            "corpus_bytes": len(raw_bytes),
            "corpus_sha256": corpus_sha256,
            "training_tokens": int(train_data.numel()),
            "validation_tokens": int(val_data.numel()),
            "tokenizer_kind": tokenizer_kind,
            "vocabulary_size": vocab_size,
            "elapsed_seconds": round(time.time() - started, 2),
            "pretrained_weights": False,
        },
    }
    torch.save(payload, args.output)
    print(json.dumps({
        "status": "checkpoint_saved",
        "path": str(args.output),
        "parameter_count": model.parameter_count(),
        "elapsed_seconds": round(time.time() - started, 2),
    }, sort_keys=True))


if __name__ == "__main__":
    main()