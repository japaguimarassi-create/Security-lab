import argparse
import hashlib
import json
import math
import os
import random
import time
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F


VOCAB_SIZE = 257
EOS_ID = 256
MODEL_CONFIG = {
    "vocab_size": VOCAB_SIZE,
    "context_length": 128,
    "d_model": 160,
    "n_heads": 5,
    "n_layers": 6,
    "feedforward_dim": 640,
    "dropout": 0.1,
    "architecture": "decoder-only causal Transformer",
    "tokenizer": "UTF-8 bytes plus EOS token",
    "pretrained_weights": False
}
EXPECTED_PARAMETERS = 1958977


class KodexTransformer(nn.Module):
    def __init__(self, config=None):
        super().__init__()
        self.config = dict(MODEL_CONFIG)
        if config:
            self.config.update(config)
        self.token_embedding = nn.Embedding(self.config["vocab_size"], self.config["d_model"])
        self.position_embedding = nn.Embedding(self.config["context_length"], self.config["d_model"])
        layer = nn.TransformerEncoderLayer(
            d_model=self.config["d_model"],
            nhead=self.config["n_heads"],
            dim_feedforward=self.config["feedforward_dim"],
            dropout=self.config["dropout"],
            activation="gelu",
            batch_first=True,
            norm_first=False
        )
        self.blocks = nn.TransformerEncoder(layer, num_layers=self.config["n_layers"])
        self.final_norm = nn.LayerNorm(self.config["d_model"])
        self.lm_head = nn.Linear(self.config["d_model"], self.config["vocab_size"], bias=True)

    def forward(self, tokens):
        batch_size, length = tokens.shape
        if length > self.config["context_length"]:
            raise ValueError("Sequence length exceeds the configured context window.")
        positions = torch.arange(length, device=tokens.device).unsqueeze(0).expand(batch_size, length)
        hidden = self.token_embedding(tokens) + self.position_embedding(positions)
        mask = torch.triu(torch.ones(length, length, dtype=torch.bool, device=tokens.device), diagonal=1)
        hidden = self.blocks(hidden, mask=mask)
        return self.lm_head(self.final_norm(hidden))


def count_parameters(model):
    return sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad)


def encode_text(text):
    return list(text.encode("utf-8")) + [EOS_ID]


def dataset_digest(path):
    path = Path(path)
    digest = hashlib.sha256()
    if path.is_dir():
        corpus_files = sorted(path.glob("*.jsonl")) + sorted(path.glob("*.txt"))
        if not corpus_files:
            raise FileNotFoundError(f"No .jsonl or .txt training corpus found in: {path}")
        for corpus_file in corpus_files:
            digest.update(corpus_file.name.encode("utf-8"))
            digest.update(b"\\0")
            digest.update(corpus_file.read_bytes())
            digest.update(b"\\0")
    elif path.is_file():
        digest.update(path.read_bytes())
    else:
        raise FileNotFoundError(f"Training data was not found: {path}")
    return digest.hexdigest()


def read_records(path):
    path = Path(path)
    if path.is_dir():
        files = sorted(path.glob("*.jsonl")) + sorted(path.glob("*.txt"))
        if not files:
            raise FileNotFoundError(f"No .jsonl or .txt training corpus found in: {path}")
        combined = []
        for corpus_file in files:
            combined.extend(read_records(corpus_file))
        if len(combined) < 2:
            raise ValueError("At least two usable records are required.")
        return combined
    if not path.is_file():
        raise FileNotFoundError(f"Training data was not found: {path}")
    if path.suffix.lower() == ".txt":
        text = path.read_text(encoding="utf-8")
        chunks = [chunk.strip() for chunk in text.split("\n\n") if chunk.strip()]
        return chunks
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"Invalid JSON on line {line_number}: {error}") from error
            if isinstance(record, dict) and isinstance(record.get("prompt"), str) and isinstance(record.get("answer"), str):
                history = record.get("history", [])
                context = ""
                if isinstance(history, list):
                    for item in history[-4:]:
                        if isinstance(item, dict) and isinstance(item.get("text"), str):
                            role = "Usuário" if item.get("role") == "user" else "Kodex"
                            context += f"{role}: {item['text']}\n"
                mode = record.get("mode", "chat")
                prompt = record["prompt"].strip()
                answer = record["answer"].strip()
                records.append(f"Modo: {mode}\n{context}Usuário: {prompt}\nKodex: {answer}")
            elif isinstance(record, dict) and isinstance(record.get("text"), str):
                records.append(record["text"].strip())
            else:
                raise ValueError(f"Line {line_number} must contain prompt/answer or text strings.")
    records = [record for record in records if record]
    if len(records) < 2:
        raise ValueError("At least two usable text examples are required for a train/validation split.")
    return records


def split_records(records, seed):
    order = list(range(len(records)))
    random.Random(seed).shuffle(order)
    validation_count = max(1, int(math.ceil(len(order) * 0.1)))
    if validation_count >= len(order):
        validation_count = 1
    validation_ids = set(order[:validation_count])
    train = [encode_text(record) for index, record in enumerate(records) if index not in validation_ids]
    validation = [encode_text(record) for index, record in enumerate(records) if index in validation_ids]
    return train, validation


def join_stream(samples):
    return torch.tensor([token for sample in samples for token in sample], dtype=torch.long)


def get_batch(stream, batch_size, context_length, device, generator):
    max_start = stream.numel() - context_length - 1
    if max_start < 1:
        raise ValueError("Training or validation stream is too short for the chosen context length.")
    starts = torch.randint(max_start + 1, (batch_size,), generator=generator)
    offsets = torch.arange(context_length)
    indices = starts.unsqueeze(1) + offsets.unsqueeze(0)
    inputs = stream[indices].to(device)
    targets = stream[indices + 1].to(device)
    return inputs, targets


@torch.no_grad()
def evaluate(model, stream, batch_size, context_length, batches, device, seed):
    model.eval()
    generator = torch.Generator(device="cpu")
    generator.manual_seed(seed)
    losses = []
    for _ in range(batches):
        inputs, targets = get_batch(stream, batch_size, context_length, device, generator)
        logits = model(inputs)
        losses.append(F.cross_entropy(logits.reshape(-1, VOCAB_SIZE), targets.reshape(-1)).item())
    model.train()
    return float(sum(losses) / len(losses))


def save_checkpoint(path, model, optimizer, scheduler, step, best_validation, config, dataset_hash):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    torch.save({
        "model": model.state_dict(),
        "optimizer": optimizer.state_dict(),
        "scheduler": scheduler.state_dict(),
        "step": step,
        "best_validation_loss": best_validation,
        "config": config,
        "dataset_sha256": dataset_hash
    }, temporary)
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description="Train Kodex's 1,958,977-parameter causal Transformer from scratch.")
    parser.add_argument("--data", type=Path, default=Path("training/data"))
    parser.add_argument("--out-dir", type=Path, default=Path("training/runs/default"))
    parser.add_argument("--steps", type=int, default=2000)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--context-length", type=int, default=128)
    parser.add_argument("--learning-rate", type=float, default=0.0003)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--eval-every", type=int, default=100)
    parser.add_argument("--eval-batches", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.steps < 1 or args.batch_size < 1 or args.eval_every < 1 or args.eval_batches < 1:
        raise ValueError("steps, batch-size, eval-every, and eval-batches must be positive")
    if args.context_length != MODEL_CONFIG["context_length"]:
        raise ValueError("This parameter-count profile uses context-length 128; change the architecture profile and tests together to change it.")
    if args.learning_rate <= 0 or args.weight_decay < 0:
        raise ValueError("learning-rate must be positive and weight-decay cannot be negative.")

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
    torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))
    if args.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is unavailable.")
    device = torch.device("cuda" if args.device == "cuda" or (args.device == "auto" and torch.cuda.is_available()) else "cpu")

    records = read_records(args.data)
    train_samples, validation_samples = split_records(records, args.seed)
    train_stream = join_stream(train_samples)
    validation_stream = join_stream(validation_samples)
    config = dict(MODEL_CONFIG)
    config.update({
        "context_length": args.context_length,
        "batch_size": args.batch_size,
        "learning_rate": args.learning_rate,
        "weight_decay": args.weight_decay,
        "seed": args.seed,
        "device": str(device)
    })
    model = KodexTransformer(config).to(device)
    parameter_count = count_parameters(model)
    if parameter_count != EXPECTED_PARAMETERS:
        raise RuntimeError(f"Architecture has {parameter_count} trainable parameters; expected {EXPECTED_PARAMETERS}.")
    dataset_hash = dataset_digest(args.data)
    metadata = {
        "model": "Kodex Transformer 0.5",
        "architecture": config,
        "trainable_parameters": parameter_count,
        "dataset": str(args.data),
        "dataset_sha256": dataset_hash,
        "records": len(records),
        "train_records": len(train_samples),
        "validation_records": len(validation_samples),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pretrained_weights_used": False,
        "training_claim": "steps recorded by this run; no claim of equivalent calendar years"
    }
    if args.dry_run:
        print(json.dumps({**metadata, "dry_run": True}, ensure_ascii=False, indent=2))
        return

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "config.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    model.train()
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=args.weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(1, args.steps))
    start_step = 0
    best_validation = float("inf")
    if args.resume:
        checkpoint = torch.load(args.resume, map_location=device, weights_only=False)
        if checkpoint.get("dataset_sha256") != dataset_hash:
            raise ValueError("Checkpoint dataset hash differs from the current dataset.")
        if checkpoint.get("config", {}).get("context_length") != args.context_length:
            raise ValueError("Checkpoint architecture does not match this run.")
        model.load_state_dict(checkpoint["model"])
        optimizer.load_state_dict(checkpoint["optimizer"])
        scheduler.load_state_dict(checkpoint["scheduler"])
        start_step = int(checkpoint["step"])
        best_validation = float(checkpoint.get("best_validation_loss", float("inf")))

    latest_path = args.out_dir / "latest.pt"
    best_path = args.out_dir / "best.pt"
    metrics_path = args.out_dir / "metrics.jsonl"
    if args.resume and args.resume.resolve() != latest_path.resolve():
        print(f"Resuming from {args.resume}", flush=True)

    generator = torch.Generator(device="cpu")
    generator.manual_seed(args.seed + start_step)
    started = time.monotonic()
    for step in range(start_step + 1, args.steps + 1):
        inputs, targets = get_batch(train_stream, args.batch_size, args.context_length, device, generator)
        logits = model(inputs)
        loss = F.cross_entropy(logits.reshape(-1, VOCAB_SIZE), targets.reshape(-1))
        if not torch.isfinite(loss):
            raise FloatingPointError(f"Non-finite training loss at step {step}")
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        scheduler.step()

        if step == 1 or step % args.eval_every == 0 or step == args.steps:
            train_loss = evaluate(model, train_stream, args.batch_size, args.context_length, args.eval_batches, device, args.seed + step)
            validation_loss = evaluate(model, validation_stream, args.batch_size, args.context_length, args.eval_batches, device, args.seed + 100000 + step)
            row = {
                "step": step,
                "train_loss": round(train_loss, 6),
                "validation_loss": round(validation_loss, 6),
                "learning_rate": optimizer.param_groups[0]["lr"],
                "elapsed_seconds": round(time.monotonic() - started, 3)
            }
            with metrics_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row) + "\n")
            print(json.dumps(row), flush=True)
            save_checkpoint(latest_path, model, optimizer, scheduler, step, best_validation, config, dataset_hash)
            if validation_loss < best_validation:
                best_validation = validation_loss
                save_checkpoint(best_path, model, optimizer, scheduler, step, best_validation, config, dataset_hash)

    final = {
        **metadata,
        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "completed_steps": args.steps,
        "starting_step": start_step,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "best_validation_loss": best_validation,
        "checkpoint": str(best_path),
        "latest_checkpoint": str(latest_path),
        "trainable_parameters": parameter_count
    }
    (args.out_dir / "result.json").write_text(json.dumps(final, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(final, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
