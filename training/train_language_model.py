import argparse
import hashlib
import json
import math
import os
import random
import time
from pathlib import Path

import torch
from torch.nn.parallel import DistributedDataParallel
from torch.nn.utils import clip_grad_norm_

from model import ByteTokenizer, KodexGPT, ModelConfig


def parse_args():
    parser = argparse.ArgumentParser(description="Train the Kodex causal Transformer language model from scratch.")
    parser.add_argument("--data", default="training/data/mobile_dialogue.jsonl")
    parser.add_argument("--out-dir", default="artifacts/kodex-model")
    parser.add_argument("--steps", type=int, default=200)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--split-seed", type=int, default=42)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--weight-decay", type=float, default=0.1)
    parser.add_argument("--dropout", type=float, default=0.1)
    parser.add_argument("--max-seq-len", type=int, default=128)
    parser.add_argument("--eval-every", type=int, default=50)
    parser.add_argument("--resume", default="")
    parser.add_argument("--cpu-threads", type=int, default=4)
    return parser.parse_args()


def load_records(path):
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Training corpus was not found: {source}")
    records = []
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    for line_number, line in enumerate(raw.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid JSON on line {line_number}: {error}") from error
        if isinstance(item.get("prompt"), str) and isinstance(item.get("answer"), str):
            prompt = item["prompt"].strip()
            answer = item["answer"].strip()
            if prompt and answer:
                records.append(f"Usuário: {prompt}\nKodex: {answer}\n")
        elif isinstance(item.get("text"), str) and item["text"].strip():
            records.append(item["text"].strip() + "\n")
        else:
            raise ValueError(f"Line {line_number} needs non-empty prompt/answer strings or a text field.")
    if len(records) < 10:
        raise ValueError(f"At least 10 examples are required for separate train/validation/test splits; found {len(records)}.")
    return records, digest


def split_records(records, seed):
    shuffled = list(records)
    random.Random(seed).shuffle(shuffled)
    test_count = max(1, int(len(shuffled) * 0.1))
    validation_count = max(1, int(len(shuffled) * 0.1))
    train_count = len(shuffled) - test_count - validation_count
    if train_count < 2:
        raise ValueError("Not enough examples after splitting.")
    return (
        shuffled[:train_count],
        shuffled[train_count:train_count + validation_count],
        shuffled[train_count + validation_count:],
    )


def encode_records(records, tokenizer):
    ids = []
    for record in records:
        ids.extend(tokenizer.encode(record, add_eos=True))
    return torch.tensor(ids, dtype=torch.long)


def get_batch(tokens, batch_size, sequence_length, device):
    if tokens.numel() < 2:
        raise ValueError("Encoded dataset needs at least two tokens.")
    available = max(1, tokens.numel() - 1)
    length = min(sequence_length, available)
    starts_max = max(1, tokens.numel() - length)
    starts = torch.randint(0, starts_max, (batch_size,))
    inputs = torch.stack([tokens[int(start):int(start) + length] for start in starts])
    targets = torch.stack([tokens[int(start) + 1:int(start) + length + 1] for start in starts])
    return inputs.to(device), targets.to(device)


@torch.no_grad()
def evaluate_loss(model, tokens, batch_size, sequence_length, device, batches=8):
    model.eval()
    total_loss = 0.0
    total_tokens = 0
    for _ in range(batches):
        inputs, targets = get_batch(tokens, batch_size, sequence_length, device)
        _, loss = model(inputs, targets)
        token_count = targets.numel()
        total_loss += float(loss.item()) * token_count
        total_tokens += token_count
    model.train()
    return total_loss / max(1, total_tokens)


def full_loss(model, tokens, sequence_length, device):
    model.eval()
    total_loss = 0.0
    total_tokens = 0
    with torch.no_grad():
        for start in range(0, max(1, tokens.numel() - 1), sequence_length):
            end = min(start + sequence_length, tokens.numel() - 1)
            if end <= start:
                continue
            inputs = tokens[start:end]
            targets = tokens[start + 1:end + 1]
            _, loss = model(inputs.unsqueeze(0).to(device), targets.unsqueeze(0).to(device))
            total_loss += float(loss.item()) * targets.numel()
            total_tokens += targets.numel()
    model.train()
    return total_loss / max(1, total_tokens)


def learning_rate_at(step, total_steps, base_lr):
    warmup_steps = min(25, max(1, total_steps // 10))
    if step <= warmup_steps:
        return base_lr * step / warmup_steps
    progress = (step - warmup_steps) / max(1, total_steps - warmup_steps)
    cosine = 0.5 * (1.0 + math.cos(math.pi * min(1.0, progress)))
    return base_lr * (0.1 + 0.9 * cosine)


def atomic_torch_save(payload, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    torch.save(payload, temporary)
    temporary.replace(path)


def atomic_json_save(payload, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main():
    args = parse_args()
    if args.steps < 1 or args.steps > 10000000:
        raise ValueError("steps must be between 1 and 10,000,000.")
    if args.batch_size < 1 or args.batch_size > 256:
        raise ValueError("batch-size must be between 1 and 256.")
    if args.eval_every < 1:
        raise ValueError("eval-every must be at least 1.")
    if args.learning_rate <= 0 or args.learning_rate > 0.1:
        raise ValueError("learning-rate must be in (0, 0.1].")
    if args.weight_decay < 0 or args.weight_decay > 1:
        raise ValueError("weight-decay must be in [0, 1].")
    if not 0 <= args.dropout < 1:
        raise ValueError("dropout must be in [0, 1).")

    world_size = int(os.environ.get("WORLD_SIZE", "1"))
    rank = int(os.environ.get("RANK", "0"))
    local_rank = int(os.environ.get("LOCAL_RANK", "0"))
    distributed = world_size > 1
    if distributed:
        backend = "nccl" if torch.cuda.is_available() else "gloo"
        torch.distributed.init_process_group(backend=backend)
    is_primary = rank == 0
    if torch.cuda.is_available():
        device = torch.device(f"cuda:{local_rank}" if distributed else "cuda")
        if distributed:
            torch.cuda.set_device(device)
    else:
        device = torch.device("cpu")
        torch.set_num_threads(max(1, min(args.cpu_threads, os.cpu_count() or 1)))

    seed = args.seed + rank
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

    records, data_digest = load_records(args.data)
    train_records, validation_records, test_records = split_records(records, args.split_seed)
    tokenizer = ByteTokenizer()
    train_tokens = encode_records(train_records, tokenizer)
    validation_tokens = encode_records(validation_records, tokenizer)
    test_tokens = encode_records(test_records, tokenizer)
    config = ModelConfig(
        vocab_size=tokenizer.vocab_size,
        max_seq_len=args.max_seq_len,
        dropout=args.dropout,
    )
    config.validate()
    core_model = KodexGPT(config).to(device)
    parameter_count = core_model.parameter_count()
    if parameter_count <= 780000:
        raise RuntimeError(f"Model must exceed 780,000 parameters; actual count: {parameter_count}.")
    model = DistributedDataParallel(core_model, device_ids=[local_rank] if device.type == "cuda" else None) if distributed else core_model
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=args.learning_rate,
        betas=(0.9, 0.95),
        weight_decay=args.weight_decay,
    )
    start_step = 0
    if args.resume:
        checkpoint = torch.load(args.resume, map_location=device, weights_only=False)
        if checkpoint.get("model_config") != config.__dict__:
            raise ValueError("Resume checkpoint configuration does not match this run.")
        core_model.load_state_dict(checkpoint["model_state_dict"])
        optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        start_step = int(checkpoint["step"])
        if start_step >= args.steps:
            raise ValueError("The requested total steps must exceed the checkpoint step.")

    output_dir = Path(args.out_dir)
    if is_primary:
        output_dir.mkdir(parents=True, exist_ok=True)
        print(json.dumps({
            "event": "training_started",
            "device": str(device),
            "distributed_world_size": world_size,
            "parameters": parameter_count,
            "examples": {"train": len(train_records), "validation": len(validation_records), "test": len(test_records)},
            "tokens": {"train": train_tokens.numel(), "validation": validation_tokens.numel(), "test": test_tokens.numel()},
            "seed": args.seed,
            "steps": args.steps,
            "start_step": start_step,
            "corpus_sha256": data_digest,
            "warning": "This corpus is small; a falling loss does not establish general language ability."
        }, ensure_ascii=False), flush=True)

    started = time.time()
    metrics = {"step": start_step, "train_loss": None, "validation_loss": None, "test_loss": None}
    model.train()
    for step in range(start_step + 1, args.steps + 1):
        current_lr = learning_rate_at(step, args.steps, args.learning_rate)
        for group in optimizer.param_groups:
            group["lr"] = current_lr
        inputs, targets = get_batch(train_tokens, args.batch_size, config.max_seq_len, device)
        optimizer.zero_grad(set_to_none=True)
        _, loss = model(inputs, targets)
        loss.backward()
        clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()
        if step == 1 or step % args.eval_every == 0 or step == args.steps:
            train_loss = evaluate_loss(model, train_tokens, args.batch_size, config.max_seq_len, device, batches=4)
            validation_loss = full_loss(model, validation_tokens, config.max_seq_len, device)
            metrics = {
                "step": step,
                "train_loss": train_loss,
                "validation_loss": validation_loss,
                "test_loss": None,
                "learning_rate": current_lr,
                "elapsed_seconds": round(time.time() - started, 2),
                "tokens_seen_estimate": step * args.batch_size * config.max_seq_len,
            }
            if is_primary:
                print(json.dumps({"event": "evaluation", **metrics}, ensure_ascii=False), flush=True)

    final_test_loss = full_loss(model, test_tokens, config.max_seq_len, device)
    metrics["test_loss"] = final_test_loss
    metrics["test_perplexity"] = math.exp(min(final_test_loss, 20))
    metrics["train_perplexity"] = math.exp(min(float(metrics["train_loss"]), 20))
    metrics["validation_perplexity"] = math.exp(min(float(metrics["validation_loss"]), 20))
    metrics["elapsed_seconds"] = round(time.time() - started, 2)
    metrics["tokens_seen_estimate"] = args.steps * args.batch_size * config.max_seq_len
    metrics["parameters"] = parameter_count
    metrics["examples"] = {
        "train": len(train_records),
        "validation": len(validation_records),
        "test": len(test_records),
        "total": len(records),
    }
    metrics["corpus_sha256"] = data_digest
    metrics["seed"] = args.seed
    metrics["device"] = str(device)
    metrics["model_config"] = config.__dict__
    metrics["training_warning"] = "Small corpus; inspect held-out losses and manually evaluate generations before claiming useful chat or coding ability."

    if is_primary:
        checkpoint_payload = {
            "model_state_dict": core_model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "step": args.steps,
            "model_config": config.__dict__,
            "parameter_count": parameter_count,
            "metrics": metrics,
            "tokenizer": {"type": "utf8_bytes_plus_eos", "vocab_size": tokenizer.vocab_size, "eos_id": tokenizer.eos_id},
            "corpus_sha256": data_digest,
        }
        atomic_torch_save(checkpoint_payload, output_dir / "checkpoint-last.pt")
        atomic_torch_save({key: value for key, value in checkpoint_payload.items() if key != "optimizer_state_dict"}, output_dir / "model-final.pt")
        atomic_json_save(metrics, output_dir / "metrics.json")
        (output_dir / "model-card.json").write_text(json.dumps({
            "model_id": "kodex-gpt-small-0.5.0",
            "architecture": "decoder-only causal Transformer",
            "parameter_count": parameter_count,
            "training_from_random_initialization": True,
            "training_examples": len(train_records),
            "validation_examples": len(validation_records),
            "test_examples": len(test_records),
            "corpus_sha256": data_digest,
            "metrics_file": "metrics.json",
            "limitations": [
                "A small training corpus is not enough to establish broad conversational ability.",
                "Parameter count is not a neuron count and does not measure quality.",
                "This is a from-scratch experimental model, not GPT-6, Codex, or Copilot.",
                "No external API is used by this training script."
            ]
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"event": "training_completed", **metrics}, ensure_ascii=False), flush=True)

    if distributed:
        torch.distributed.barrier()
        torch.distributed.destroy_process_group()


if __name__ == "__main__":
    main()
