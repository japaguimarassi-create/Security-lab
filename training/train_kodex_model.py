import argparse
import hashlib
import json
import math
import random
import shutil
import tempfile
import time
from dataclasses import asdict
from pathlib import Path

import torch
from tokenizers import Tokenizer
from torch.nn.utils import clip_grad_norm_

from kodex_lm import KodexLanguageModel, ModelConfig, masked_cross_entropy
from train_tokenizer import train_tokenizer


def parse_args():
    parser = argparse.ArgumentParser(description="Train the experimental Kodex sparse Transformer from scratch.")
    parser.add_argument("--data", default="training/data/mobile_dialogue.jsonl")
    parser.add_argument("--out-dir", default="artifacts/kodex-km-model")
    parser.add_argument("--steps", type=int, default=200)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--split-seed", type=int, default=42)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--weight-decay", type=float, default=0.1)
    parser.add_argument("--dropout", type=float, default=0.05)
    parser.add_argument("--max-seq-len", "--block-size", dest="block_size", type=int, default=128)
    parser.add_argument("--n-layer", type=int, default=4)
    parser.add_argument("--n-head", type=int, default=4)
    parser.add_argument("--n-embd", type=int, default=128)
    parser.add_argument("--n-kv-head", type=int, default=2)
    parser.add_argument("--n-experts", type=int, default=4)
    parser.add_argument("--experts-per-token", type=int, default=2)
    parser.add_argument("--router-aux-loss-coef", type=float, default=0.01)
    parser.add_argument("--router-aux-loss-coef", type=float, default=0.01)
    parser.add_argument("--mtp-heads", type=int, default=2)
    parser.add_argument("--mtp-loss-weight", type=float, default=0.1)
    parser.add_argument("--vocab-size", type=int, default=512)
    parser.add_argument("--eval-every", type=int, default=50)
    parser.add_argument("--resume", default="")
    parser.add_argument("--cpu-threads", type=int, default=4)
    return parser.parse_args()


def load_records(path):
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Training corpus not found: {source}")
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    records = []
    for line_number, line in enumerate(raw.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid JSON on line {line_number}: {error}") from error
        if not isinstance(item, dict):
            raise ValueError(f"Line {line_number} must contain a JSON object.")
        if isinstance(item.get("prompt"), str) and isinstance(item.get("answer"), str):
            prompt = item["prompt"].strip()
            answer = item["answer"].strip()
            mode = str(item.get("mode") or "chat").strip().lower()
            if prompt and answer:
                records.append(f"Modo: {mode}\nUsuário: {prompt}\nKodex: {answer}\n")
        elif isinstance(item.get("text"), str) and item["text"].strip():
            records.append(item["text"].strip() + "\n")
        else:
            raise ValueError(f"Line {line_number} needs non-empty prompt/answer strings or a text field.")
    if len(records) < 10:
        raise ValueError(f"At least 10 examples are required for train/validation/test; found {len(records)}.")
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


def atomic_json_save(payload, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def atomic_torch_save(payload, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    torch.save(payload, temporary)
    temporary.replace(path)


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def train_bpe_tokenizer(train_records, tokenizer_path, requested_vocab_size):
    with tempfile.TemporaryDirectory(prefix="kodex-tokenizer-") as temporary:
        source = Path(temporary) / "train.txt"
        source.write_text("\n".join(train_records) + "\n", encoding="utf-8")
        result = train_tokenizer(source, tokenizer_path, requested_vocab_size)
    tokenizer = Tokenizer.from_file(str(tokenizer_path))
    eos_id = tokenizer.token_to_id("[EOS]")
    if eos_id is None:
        raise RuntimeError("Trained tokenizer does not contain the [EOS] token.")
    return tokenizer, eos_id, result


def encode_records(records, tokenizer, eos_id):
    ids = []
    for record in records:
        ids.extend(tokenizer.encode(record).ids)
        ids.append(eos_id)
    if len(ids) < 2:
        raise ValueError("Encoded dataset must contain at least two tokens.")
    return torch.tensor(ids, dtype=torch.long)


def get_batch(tokens, batch_size, block_size, device):
    if tokens.numel() < 2:
        raise ValueError("Encoded dataset must contain at least two tokens.")
    length = min(block_size, tokens.numel() - 1)
    starts_max = tokens.numel() - length
    starts = torch.randint(0, max(1, starts_max), (batch_size,))
    inputs = torch.stack([tokens[int(start):int(start) + length] for start in starts])
    targets = torch.stack([tokens[int(start) + 1:int(start) + length + 1] for start in starts])
    return inputs.to(device), targets.to(device)


@torch.no_grad()
def evaluate_loss(model, tokens, block_size, device):
    model.eval()
    total_cross_entropy = 0.0
    total_objective = 0.0
    total_tokens = 0
    for start in range(0, max(1, tokens.numel() - 1), block_size):
        end = min(start + block_size, tokens.numel() - 1)
        if end <= start:
            continue
        inputs = tokens[start:end].unsqueeze(0).to(device)
        targets = tokens[start + 1:end + 1].unsqueeze(0).to(device)
        if inputs.shape != targets.shape:
            continue
        logits, objective_loss = model(inputs, targets)
        cross_entropy = masked_cross_entropy(logits, targets)
        count = targets.numel()
        total_cross_entropy += float(cross_entropy.item()) * count
        total_objective += float(objective_loss.item()) * count
        total_tokens += count
    model.train()
    denominator = max(1, total_tokens)
    return {
        "cross_entropy": total_cross_entropy / denominator,
        "objective_loss": total_objective / denominator,
        "tokens": total_tokens,
    }


def learning_rate_at(step, total_steps, base_lr):
    warmup_steps = min(25, max(1, total_steps // 10))
    if step <= warmup_steps:
        return base_lr * step / warmup_steps
    progress = (step - warmup_steps) / max(1, total_steps - warmup_steps)
    cosine = 0.5 * (1.0 + math.cos(math.pi * min(1.0, progress)))
    return base_lr * (0.1 + 0.9 * cosine)


def build_checkpoint(model, optimizer, step, config, metrics, data_digest, tokenizer_digest, tokenizer_path):
    return {
        "architecture": "KodexLanguageModel",
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "step": step,
        "model_config": asdict(config),
        "parameter_count": model.parameter_count(),
        "metrics": metrics,
        "corpus_sha256": data_digest,
        "tokenizer_sha256": tokenizer_digest,
        "tokenizer_file": str(tokenizer_path.name),
    }


def main():
    args = parse_args()
    if not 1 <= args.steps <= 10000000:
        raise ValueError("steps must be between 1 and 10,000,000.")
    if not 1 <= args.batch_size <= 256:
        raise ValueError("batch-size must be between 1 and 256.")
    if args.eval_every < 1:
        raise ValueError("eval-every must be at least 1.")
    if not 0 < args.learning_rate <= 0.1:
        raise ValueError("learning-rate must be in (0, 0.1].")
    if not 0 <= args.weight_decay <= 1:
        raise ValueError("weight-decay must be in [0, 1].")
    if not 0 <= args.dropout < 1:
        raise ValueError("dropout must be in [0, 1).")
    if not 259 <= args.vocab_size <= 65536:
        raise ValueError("vocab-size must be between 259 and 65,536.")
    if args.block_size < 8 or args.block_size > 2048:
        raise ValueError("max-seq-len must be between 8 and 2048.")

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
        device = torch.device("cuda")
    else:
        device = torch.device("cpu")
        torch.set_num_threads(max(1, min(args.cpu_threads, __import__("os").cpu_count() or 1)))

    records, data_digest = load_records(args.data)
    train_records, validation_records, test_records = split_records(records, args.split_seed)
    output_dir = Path(args.out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    tokenizer_path = output_dir / "tokenizer.json"
    if args.resume:
        checkpoint_path = Path(args.resume)
        if not checkpoint_path.is_file():
            raise FileNotFoundError(f"Resume checkpoint not found: {checkpoint_path}")
        original_tokenizer = checkpoint_path.parent / "tokenizer.json"
        if not original_tokenizer.is_file():
            raise FileNotFoundError("Resume requires tokenizer.json beside the checkpoint.")
        if original_tokenizer.resolve() != tokenizer_path.resolve():
            shutil.copy2(original_tokenizer, tokenizer_path)
        tokenizer = Tokenizer.from_file(str(tokenizer_path))
        eos_id = tokenizer.token_to_id("[EOS]")
        if eos_id is None:
            raise ValueError("Resume tokenizer has no [EOS] token.")
        tokenizer_result = {"status": "loaded_for_resume", "vocabulary_size": tokenizer.get_vocab_size()}
    else:
        tokenizer, eos_id, tokenizer_result = train_bpe_tokenizer(train_records, tokenizer_path, args.vocab_size)

    tokenizer_digest = sha256_file(tokenizer_path)
    train_tokens = encode_records(train_records, tokenizer, eos_id)
    validation_tokens = encode_records(validation_records, tokenizer, eos_id)
    test_tokens = encode_records(test_records, tokenizer, eos_id)
    config = ModelConfig(
        vocab_size=tokenizer.get_vocab_size(),
        block_size=args.block_size,
        n_layer=args.n_layer,
        n_head=args.n_head,
        n_embd=args.n_embd,
        n_kv_head=args.n_kv_head,
        n_experts=args.n_experts,
        experts_per_token=args.experts_per_token,
        router_aux_loss_coef=args.router_aux_loss_coef,
        mtp_heads=args.mtp_heads,
        mtp_loss_weight=args.mtp_loss_weight,
        dropout=args.dropout,
    )
    model = KodexLanguageModel(config).to(device)
    parameter_count = model.parameter_count()
    if parameter_count <= 780000:
        raise RuntimeError(f"Model must exceed 780,000 trainable parameters; found {parameter_count}.")
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=args.learning_rate,
        betas=(0.9, 0.95),
        weight_decay=args.weight_decay,
    )

    start_step = 0
    if args.resume:
        checkpoint = torch.load(args.resume, map_location=device, weights_only=False)
        if checkpoint.get("model_config") != asdict(config):
            raise ValueError("Resume checkpoint model configuration does not match this run.")
        if checkpoint.get("corpus_sha256") != data_digest:
            raise ValueError("Resume checkpoint corpus SHA-256 does not match the current data.")
        if checkpoint.get("tokenizer_sha256") != tokenizer_digest:
            raise ValueError("Resume checkpoint tokenizer SHA-256 does not match.")
        model.load_state_dict(checkpoint["model_state_dict"])
        optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        start_step = int(checkpoint["step"])
        if start_step >= args.steps:
            raise ValueError("The total target steps must exceed the checkpoint step.")

    if device.type == "cuda":
        torch.backends.cuda.matmul.allow_tf32 = True

    print(json.dumps({
        "event": "training_started",
        "architecture": "decoder-only sparse Transformer with GQA, RoPE, MoE, and multi-token prediction",
        "device": str(device),
        "parameters": parameter_count,
        "model_config": asdict(config),
        "examples": {"train": len(train_records), "validation": len(validation_records), "test": len(test_records)},
        "tokens": {"train": int(train_tokens.numel()), "validation": int(validation_tokens.numel()), "test": int(test_tokens.numel())},
        "tokenizer": tokenizer_result,
        "tokenizer_sha256": tokenizer_digest,
        "corpus_sha256": data_digest,
        "seed": args.seed,
        "split_seed": args.split_seed,
        "steps": args.steps,
        "start_step": start_step,
        "warning": "The current corpus is small. This model architecture and parameter count do not establish useful chat or coding capability."
    }, ensure_ascii=False), flush=True)

    started = time.time()
    best_validation_loss = float("inf")
    best_step = start_step
    last_metrics = {}
    model.train()
    for step in range(start_step + 1, args.steps + 1):
        current_lr = learning_rate_at(step, args.steps, args.learning_rate)
        for group in optimizer.param_groups:
            group["lr"] = current_lr
        inputs, targets = get_batch(train_tokens, args.batch_size, config.block_size, device)
        optimizer.zero_grad(set_to_none=True)
        _, loss = model(inputs, targets)
        if not torch.isfinite(loss):
            raise FloatingPointError(f"Non-finite training loss at step {step}.")
        loss.backward()
        clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()

        if step == 1 or step % args.eval_every == 0 or step == args.steps:
            train_eval = evaluate_loss(model, train_tokens, config.block_size, device)
            validation_eval = evaluate_loss(model, validation_tokens, config.block_size, device)
            last_metrics = {
                "step": step,
                "train_loss": train_eval["cross_entropy"],
                "validation_loss": validation_eval["cross_entropy"],
                "train_objective_loss": train_eval["objective_loss"],
                "validation_objective_loss": validation_eval["objective_loss"],
                "learning_rate": current_lr,
                "elapsed_seconds": round(time.time() - started, 2),
                "tokens_seen_estimate": step * args.batch_size * config.block_size,
                "parameters": parameter_count,
                "train_tokens": train_eval["tokens"],
                "validation_tokens": validation_eval["tokens"],
                "test_loss": None,
                "corpus_sha256": data_digest,
                "tokenizer_sha256": tokenizer_digest,
            }
            print(json.dumps({"event": "evaluation", **last_metrics}, ensure_ascii=False), flush=True)
            checkpoint_payload = build_checkpoint(
                model, optimizer, step, config, last_metrics, data_digest, tokenizer_digest, tokenizer_path
            )
            atomic_torch_save(checkpoint_payload, output_dir / "checkpoint-last.pt")
            if validation_eval["cross_entropy"] < best_validation_loss:
                best_validation_loss = validation_eval["cross_entropy"]
                best_step = step
                atomic_torch_save(
                    {key: value for key, value in checkpoint_payload.items() if key != "optimizer_state_dict"},
                    output_dir / "model-best.pt",
                )

    test_eval = evaluate_loss(model, test_tokens, config.block_size, device)
    last_metrics.update({
        "step": args.steps,
        "test_loss": test_eval["cross_entropy"],
        "test_objective_loss": test_eval["objective_loss"],
        "train_perplexity": math.exp(min(float(last_metrics["train_loss"]), 20)),
        "validation_perplexity": math.exp(min(float(last_metrics["validation_loss"]), 20)),
        "test_perplexity": math.exp(min(float(test_eval["cross_entropy"]), 20)),
        "elapsed_seconds": round(time.time() - started, 2),
        "tokens_seen_estimate": args.steps * args.batch_size * config.block_size,
        "parameter_count": parameter_count,
        "best_validation_loss": best_validation_loss,
        "best_step": best_step,
        "test_tokens": test_eval["tokens"],
        "tokenizer_file": "tokenizer.json",
    })
    final_payload = build_checkpoint(
        model, optimizer, args.steps, config, last_metrics, data_digest, tokenizer_digest, tokenizer_path
    )
    atomic_torch_save(final_payload, output_dir / "checkpoint-last.pt")
    atomic_torch_save(
        {key: value for key, value in final_payload.items() if key != "optimizer_state_dict"},
        output_dir / "model-final.pt",
    )
    atomic_json_save(last_metrics, output_dir / "metrics.json")
    atomic_json_save({
        "model_id": "kodex-sparse-transformer-0.5.0",
        "architecture": "decoder-only causal Transformer; grouped-query attention; rotary embeddings; sparse top-k mixture-of-experts; multi-token prediction",
        "parameter_count": parameter_count,
        "model_config": asdict(config),
        "training_from_random_initialization": not bool(args.resume),
        "training_examples": len(train_records),
        "validation_examples": len(validation_records),
        "test_examples": len(test_records),
        "corpus_sha256": data_digest,
        "tokenizer_sha256": tokenizer_digest,
        "metrics_file": "metrics.json",
        "limitations": [
            "The current starter corpus is too small to establish broad conversational or coding ability.",
            "Parameter count is not a neuron count and does not measure quality.",
            "This is an experimental model trained from scratch, not GPT-6 Astra, GPT-6.1 Sol, Codex, or Copilot.",
            "Training does not call a remote inference API.",
            "The held-out score and sample generations require manual review."
        ],
    }, output_dir / "model-card.json")
    print(json.dumps({"event": "training_completed", **last_metrics}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
