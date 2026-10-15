import argparse
import hashlib
import json
import math
import os
import random
import time
from contextlib import nullcontext
from pathlib import Path

import torch

from kodex_lm import KodexLanguageModel, ModelConfig, encode_bytes


def parse_args():
    parser = argparse.ArgumentParser(description="Train Kodex from random initialization.")
    parser.add_argument("--data", type=Path, default=Path("training/data/smoke_corpus.txt"))
    parser.add_argument("--validation-data", type=Path, default=None)
    parser.add_argument("--tokenizer", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=Path("training/checkpoints/kodex.pt"))
    parser.add_argument("--resume-from", type=Path, default=None)
    parser.add_argument("--steps", type=int, default=1000)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=1)
    parser.add_argument("--block-size", type=int, default=256)
    parser.add_argument("--layers", type=int, default=6)
    parser.add_argument("--heads", type=int, default=6)
    parser.add_argument("--kv-heads", type=int, default=2)
    parser.add_argument("--embedding-size", type=int, default=192)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--min-learning-rate", type=float, default=3e-5)
    parser.add_argument("--weight-decay", type=float, default=0.1)
    parser.add_argument("--warmup-steps", type=int, default=None)
    parser.add_argument("--decay-ratio", type=float, default=0.1)
    parser.add_argument("--eval-interval", type=int, default=100)
    parser.add_argument("--eval-batches", type=int, default=8)
    parser.add_argument("--save-every", type=int, default=500)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--precision", choices=("auto", "fp32", "fp16", "bf16"), default="auto")
    return parser.parse_args()


def encode_text(text, tokenizer):
    if tokenizer is None:
        return encode_bytes(text)
    return tokenizer.encode(text).ids


def sample_batch(data, batch_size, block_size, device):
    if data.numel() <= block_size + 1:
        raise ValueError("Token stream is too short for block_size")
    starts = torch.randint(0, data.numel() - block_size - 1, (batch_size,), device=device)
    inputs = torch.stack([data[start:start + block_size] for start in starts])
    targets = torch.stack([data[start + 1:start + block_size + 1] for start in starts])
    return inputs, targets


def autocast_context(device, dtype):
    if device.type == "cuda" and dtype is not None:
        return torch.autocast(device_type="cuda", dtype=dtype)
    return nullcontext()


@torch.no_grad()
def estimate_loss(model, train_data, val_data, batch_size, block_size, device, precision_dtype, batches):
    model.eval()
    estimates = {}
    for name, data in (("train", train_data), ("validation", val_data)):
        values = []
        for _ in range(batches):
            inputs, targets = sample_batch(data, batch_size, block_size, device)
            with autocast_context(device, precision_dtype):
                _, loss = model(inputs, targets)
            if not torch.isfinite(loss):
                raise FloatingPointError(f"Non-finite {name} loss during evaluation")
            values.append(float(loss.item()))
        estimates[name] = sum(values) / len(values)
    model.train()
    return estimates


def learning_rate_at_step(step, total_steps, max_lr, min_lr, warmup_steps, decay_ratio):
    if warmup_steps > 0 and step <= warmup_steps:
        return max_lr * step / warmup_steps
    decay_start = max(warmup_steps, int(total_steps * (1.0 - decay_ratio)))
    if step <= decay_start:
        return max_lr
    denominator = max(1, total_steps - decay_start)
    progress = min(1.0, max(0.0, (step - decay_start) / denominator))
    return min_lr + (max_lr - min_lr) * (1.0 - progress)


def make_optimizer(model, learning_rate, weight_decay):
    decay_parameters = []
    no_decay_parameters = []
    for name, parameter in model.named_parameters():
        if not parameter.requires_grad:
            continue
        if parameter.ndim < 2 or "token_embedding" in name or "norm" in name:
            no_decay_parameters.append(parameter)
        else:
            decay_parameters.append(parameter)
    groups = [
        {"params": decay_parameters, "weight_decay": weight_decay},
        {"params": no_decay_parameters, "weight_decay": 0.0},
    ]
    return torch.optim.AdamW(groups, lr=learning_rate, betas=(0.9, 0.95), eps=1e-8)


def save_checkpoint(path, model, optimizer, scaler, config, training, step, best_validation_loss):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 2,
        "model_name": "KodexScratchLM",
        "config": config,
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "scaler_state_dict": scaler.state_dict(),
        "training": training,
        "global_step": step,
        "best_validation_loss": best_validation_loss,
        "torch_rng_state": torch.get_rng_state(),
        "cuda_rng_states": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else [],
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    torch.save(payload, temporary)
    temporary.replace(path)


def main():
    args = parse_args()
    positive = {
        "steps": args.steps,
        "batch-size": args.batch_size,
        "gradient-accumulation-steps": args.gradient_accumulation_steps,
        "block-size": args.block_size,
        "eval-interval": args.eval_interval,
        "eval-batches": args.eval_batches,
    }
    invalid = [name for name, value in positive.items() if value < 1]
    if invalid:
        raise SystemExit("Values must be positive: " + ", ".join(invalid))
    if args.save_every < 0:
        raise SystemExit("save-every must be zero or positive")
    if args.learning_rate <= 0 or args.min_learning_rate < 0 or args.min_learning_rate > args.learning_rate:
        raise SystemExit("Learning rates must satisfy 0 <= min-learning-rate <= learning-rate")
    if args.weight_decay < 0 or not 0.0 <= args.decay_ratio <= 1.0:
        raise SystemExit("weight-decay must be non-negative and decay-ratio must be in [0, 1]")
    if args.warmup_steps is not None and args.warmup_steps < 0:
        raise SystemExit("warmup-steps must be non-negative")

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    if args.device == "cuda" and not torch.cuda.is_available():
        raise SystemExit("CUDA was requested but is not available")
    device = torch.device(
        "cuda" if args.device == "cuda" or (args.device == "auto" and torch.cuda.is_available()) else "cpu"
    )

    precision_dtype = None
    effective_precision = "fp32"
    if device.type == "cuda":
        if args.precision == "bf16":
            if not torch.cuda.is_bf16_supported():
                raise SystemExit("bf16 was requested but this CUDA device does not support it")
            precision_dtype = torch.bfloat16
            effective_precision = "bf16"
        elif args.precision == "fp16":
            precision_dtype = torch.float16
            effective_precision = "fp16"
        elif args.precision == "auto" and torch.cuda.is_bf16_supported():
            precision_dtype = torch.bfloat16
            effective_precision = "bf16"
        elif args.precision == "auto":
            precision_dtype = torch.float16
            effective_precision = "fp16"
    elif args.precision in {"fp16", "bf16"}:
        raise SystemExit("fp16 and bf16 precision require a CUDA device")

    data_path = args.data.resolve()
    if not data_path.is_file():
        raise SystemExit(f"Training data file not found: {data_path}")
    raw_bytes = data_path.read_bytes()
    if len(raw_bytes) < 512:
        raise SystemExit("Training corpus is too small; expected at least 512 UTF-8 bytes")
    raw_text = raw_bytes.decode("utf-8")
    corpus_sha256 = hashlib.sha256(raw_bytes).hexdigest()

    tokenizer = None
    tokenizer_json = None
    tokenizer_kind = "utf8-bytes"
    vocab_size = 256
    if args.tokenizer is not None:
        tokenizer_path = args.tokenizer.resolve()
        if not tokenizer_path.is_file():
            raise SystemExit(f"Tokenizer file not found: {tokenizer_path}")
        try:
            from tokenizers import Tokenizer
        except ImportError as error:
            raise SystemExit("Install the tokenizers package to use a BPE tokenizer") from error
        tokenizer = Tokenizer.from_file(str(tokenizer_path))
        tokenizer_json = tokenizer.to_str()
        vocab_size = tokenizer.get_vocab_size()
        tokenizer_kind = "byte-level-bpe"

    all_ids = encode_text(raw_text, tokenizer)
    if args.validation_data is None:
        split_index = int(len(all_ids) * 0.9)
        train_ids = all_ids[:split_index]
        validation_ids = all_ids[split_index:]
        validation_sha256 = hashlib.sha256(bytes(raw_bytes[split_index:])).hexdigest() if tokenizer is None else None
        validation_source = "last 10 percent of tokenized training file; use --validation-data for an independent holdout"
    else:
        validation_path = args.validation_data.resolve()
        if not validation_path.is_file():
            raise SystemExit(f"Validation data file not found: {validation_path}")
        validation_bytes = validation_path.read_bytes()
        validation_text = validation_bytes.decode("utf-8")
        train_ids = all_ids
        validation_ids = encode_text(validation_text, tokenizer)
        validation_sha256 = hashlib.sha256(validation_bytes).hexdigest()
        validation_source = str(validation_path)

    if len(train_ids) <= args.block_size + 1 or len(validation_ids) <= args.block_size + 1:
        raise SystemExit("Training or validation token stream is too short; add data or reduce block-size")
    train_data = torch.tensor(train_ids, dtype=torch.long, device=device)
    val_data = torch.tensor(validation_ids, dtype=torch.long, device=device)

    resume_payload = None
    if args.resume_from is not None:
        resume_path = args.resume_from.resolve(strict=True)
        resume_payload = torch.load(resume_path, map_location="cpu", weights_only=True)
        if resume_payload.get("schema_version") != 2:
            raise SystemExit("Checkpoint schema is incompatible; start a new run with the upgraded model")
        config = ModelConfig(**resume_payload["config"])
        if config.vocab_size != vocab_size:
            raise SystemExit("Checkpoint vocabulary does not match the current tokenizer")
        if resume_payload.get("training", {}).get("tokenizer_kind") != tokenizer_kind:
            raise SystemExit("Checkpoint tokenizer kind does not match the current data pipeline")
    else:
        config = ModelConfig(
            vocab_size=vocab_size,
            block_size=args.block_size,
            n_layer=args.layers,
            n_head=args.heads,
            n_embd=args.embedding_size,
            n_kv_head=args.kv_heads,
        )

    if args.block_size > config.block_size and resume_payload is not None:
        raise SystemExit("Requested block-size exceeds the checkpoint's context length")
    model = KodexLanguageModel(config).to(device)
    optimizer = make_optimizer(model, args.learning_rate, args.weight_decay)
    use_fp16_scaler = device.type == "cuda" and effective_precision == "fp16"
    scaler = torch.amp.GradScaler("cuda", enabled=use_fp16_scaler)
    global_step = 0
    best_validation_loss = math.inf
    if resume_payload is not None:
        model.load_state_dict(resume_payload["model_state_dict"])
        optimizer.load_state_dict(resume_payload["optimizer_state_dict"])
        if resume_payload.get("scaler_state_dict"):
            scaler.load_state_dict(resume_payload["scaler_state_dict"])
        global_step = int(resume_payload.get("global_step", 0))
        best_validation_loss = float(resume_payload.get("best_validation_loss", math.inf))
        if resume_payload.get("torch_rng_state") is not None:
            torch.set_rng_state(resume_payload["torch_rng_state"])
        saved_cuda_states = resume_payload.get("cuda_rng_states", [])
        if device.type == "cuda" and saved_cuda_states and len(saved_cuda_states) == torch.cuda.device_count():
            torch.cuda.set_rng_state_all(saved_cuda_states)
        if global_step >= args.steps:
            raise SystemExit("Checkpoint already reached --steps; choose a larger total step count")

    warmup_steps = args.warmup_steps
    if warmup_steps is None:
        warmup_steps = min(1000, max(0, int(args.steps * 0.03)))
    warmup_steps = min(warmup_steps, max(0, args.steps - 1))

    output_path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    training = {
        "seed": args.seed,
        "device": str(device),
        "precision": effective_precision,
        "data_file": str(data_path),
        "corpus_bytes": len(raw_bytes),
        "corpus_sha256": corpus_sha256,
        "validation_source": validation_source,
        "validation_sha256": validation_sha256,
        "training_tokens": len(train_ids),
        "validation_tokens": len(validation_ids),
        "tokenizer_kind": tokenizer_kind,
        "tokenizer_json": tokenizer_json,
        "vocabulary_size": vocab_size,
        "pretrained_weights": False,
        "source_commit": os.environ.get("GITHUB_SHA"),
        "optimizer": "AdamW",
        "betas": [0.9, 0.95],
        "weight_decay": args.weight_decay,
        "learning_rate": args.learning_rate,
        "min_learning_rate": args.min_learning_rate,
        "warmup_steps": warmup_steps,
        "decay_ratio": args.decay_ratio,
        "batch_size": args.batch_size,
        "gradient_accumulation_steps": args.gradient_accumulation_steps,
        "effective_batch_tokens": args.batch_size * config.block_size * args.gradient_accumulation_steps,
    }

    print(json.dumps({
        "status": "training_started",
        "device": str(device),
        "precision": effective_precision,
        "corpus_bytes": len(raw_bytes),
        "corpus_sha256": corpus_sha256,
        "training_tokens": len(train_ids),
        "validation_tokens": len(validation_ids),
        "validation_source": validation_source,
        "tokenizer_kind": tokenizer_kind,
        "vocabulary_size": vocab_size,
        "parameter_count": model.parameter_count(),
        "config": model.config_dict(),
        "optimizer": training["optimizer"],
        "betas": training["betas"],
        "warmup_steps": warmup_steps,
        "decay_ratio": args.decay_ratio,
        "gradient_accumulation_steps": args.gradient_accumulation_steps,
        "resumed_from_step": global_step,
        "pretrained_weights": False,
        "seed": args.seed,
    }, sort_keys=True))

    started = time.time()
    model.train()
    for step in range(global_step + 1, args.steps + 1):
        learning_rate = learning_rate_at_step(
            step, args.steps, args.learning_rate, args.min_learning_rate, warmup_steps, args.decay_ratio
        )
        for group in optimizer.param_groups:
            group["lr"] = learning_rate
        optimizer.zero_grad(set_to_none=True)
        running_loss = 0.0

        for _ in range(args.gradient_accumulation_steps):
            inputs, targets = sample_batch(train_data, args.batch_size, config.block_size, device)
            with autocast_context(device, precision_dtype):
                _, loss = model(inputs, targets)
            if not torch.isfinite(loss):
                raise FloatingPointError(f"Non-finite loss at step {step}")
            running_loss += float(loss.detach().item())
            scaler.scale(loss / args.gradient_accumulation_steps).backward()

        scaler.unscale_(optimizer)
        grad_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        if not torch.isfinite(grad_norm):
            raise FloatingPointError(f"Non-finite gradient norm at step {step}")
        scaler.step(optimizer)
        scaler.update()

        should_evaluate = step == 1 or step % args.eval_interval == 0 or step == args.steps
        if should_evaluate:
            metrics = estimate_loss(
                model, train_data, val_data, args.batch_size, config.block_size,
                device, precision_dtype, args.eval_batches
            )
            is_best = metrics["validation"] < best_validation_loss
            if is_best:
                best_validation_loss = metrics["validation"]
                best_path = output_path.with_name(output_path.stem + "-best" + output_path.suffix)
                save_checkpoint(
                    best_path, model, optimizer, scaler, model.config_dict(), training,
                    step, best_validation_loss
                )
            print(json.dumps({
                "step": step,
                "steps": args.steps,
                "learning_rate": learning_rate,
                "microbatch_loss": running_loss / args.gradient_accumulation_steps,
                "train_loss": metrics["train"],
                "validation_loss": metrics["validation"],
                "best_validation_loss": best_validation_loss,
                "gradient_norm": float(grad_norm.item()),
                "tokens_processed_estimate": step * training["effective_batch_tokens"],
                "elapsed_seconds": round(time.time() - started, 2),
            }, sort_keys=True))

        if args.save_every and step % args.save_every == 0:
            save_checkpoint(
                output_path, model, optimizer, scaler, model.config_dict(), training,
                step, best_validation_loss
            )

    save_checkpoint(
        output_path, model, optimizer, scaler, model.config_dict(), training,
        args.steps, best_validation_loss
    )
    print(json.dumps({
        "status": "checkpoint_saved",
        "path": str(output_path),
        "best_checkpoint": str(output_path.with_name(output_path.stem + "-best" + output_path.suffix)),
        "global_step": args.steps,
        "parameter_count": model.parameter_count(),
        "elapsed_seconds": round(time.time() - started, 2),
        "resumable": True,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
