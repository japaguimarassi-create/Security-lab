import argparse
import hashlib
import json
import math
import random
import time
from contextlib import nullcontext
from pathlib import Path

import torch

from kodex_lm import KodexLanguageModel, ModelConfig, encode_bytes
from train import autocast_context, learning_rate_at_step, make_optimizer


def parse_args():
    parser = argparse.ArgumentParser(description="Supervised instruction fine-tuning for a Kodex base checkpoint.")
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--validation-data", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("training/checkpoints/kodex-instruct.pt"))
    parser.add_argument("--resume-from", type=Path, default=None)
    parser.add_argument("--steps", type=int, default=2000)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=1e-5)
    parser.add_argument("--min-learning-rate", type=float, default=1e-6)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--warmup-steps", type=int, default=50)
    parser.add_argument("--decay-ratio", type=float, default=0.1)
    parser.add_argument("--eval-interval", type=int, default=100)
    parser.add_argument("--eval-batches", type=int, default=8)
    parser.add_argument("--save-every", type=int, default=500)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--precision", choices=("auto", "fp32", "fp16", "bf16"), default="auto")
    return parser.parse_args()


def load_jsonl(path):
    examples = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"Invalid JSONL on line {line_number}: {error.msg}") from error
            messages = item.get("messages") if isinstance(item, dict) else None
            if not isinstance(messages, list) or not messages:
                raise ValueError(f"Line {line_number} must have a non-empty messages array")
            normalized = []
            for message in messages:
                if not isinstance(message, dict):
                    raise ValueError(f"Line {line_number} contains a non-object message")
                role = message.get("role")
                text = message.get("content")
                if role not in {"system", "user", "assistant", "tool"} or not isinstance(text, str) or not text.strip():
                    raise ValueError(f"Line {line_number} has an invalid role or empty content")
                normalized.append({"role": role, "content": text})
            if not any(message["role"] == "user" for message in normalized):
                raise ValueError(f"Line {line_number} has no user message")
            if not any(message["role"] == "assistant" for message in normalized):
                raise ValueError(f"Line {line_number} has no assistant target")
            examples.append(normalized)
    if not examples:
        raise ValueError(f"No instruction examples found in {path}")
    return examples


def tokenize_example(messages, tokenizer_kind, tokenizer):
    parts = []
    target_ranges = []
    cursor = 0
    for message in messages:
        role = message["role"]
        header = f"<|{role}|>\n"
        body = message["content"] + "\n"
        parts.append(header)
        cursor += len(header)
        body_start = cursor
        parts.append(body)
        cursor += len(body)
        if role == "assistant":
            target_ranges.append((body_start, cursor))

    full_text = "".join(parts)
    if tokenizer_kind == "byte-level-bpe":
        encoded = tokenizer.encode(full_text)
        token_ids = encoded.ids
        token_offsets = encoded.offsets
        target_mask = [
            any(start < token_end and token_start < end for start, end in target_ranges)
            for token_start, token_end in token_offsets
        ]
    else:
        raw = full_text.encode("utf-8")
        token_ids = list(raw)
        target_mask = [False] * len(raw)
        for start, end in target_ranges:
            byte_start = len(full_text[:start].encode("utf-8"))
            byte_end = len(full_text[:end].encode("utf-8"))
            for index in range(byte_start, byte_end):
                target_mask[index] = True

    if len(token_ids) < 2:
        return None
    input_ids = token_ids[:-1]
    targets = [token_ids[index + 1] if target_mask[index + 1] else -100 for index in range(len(token_ids) - 1)]
    if not any(value != -100 for value in targets):
        return None
    return input_ids, targets


def load_windows(path, tokenizer_kind, tokenizer, block_size):
    examples = load_jsonl(path)
    windows = []
    for messages in examples:
        encoded = tokenize_example(messages, tokenizer_kind, tokenizer)
        if encoded is None:
            continue
        input_ids, targets = encoded
        stride = max(1, block_size // 2)
        for start in range(0, len(input_ids), stride):
            x = input_ids[start:start + block_size]
            y = targets[start:start + block_size]
            if not y or all(value == -100 for value in y):
                continue
            x = x + [0] * (block_size - len(x))
            y = y + [-100] * (block_size - len(y))
            windows.append((x, y))
    if not windows:
        raise ValueError(f"No windows with assistant targets were produced from {path}")
    return windows, len(examples)


def make_batch(windows, batch_size, device):
    selected = random.choices(windows, k=batch_size)
    inputs = torch.tensor([row[0] for row in selected], dtype=torch.long, device=device)
    targets = torch.tensor([row[1] for row in selected], dtype=torch.long, device=device)
    return inputs, targets


@torch.no_grad()
def evaluate(model, windows, batch_size, device, precision_dtype, batches):
    model.eval()
    losses = []
    for _ in range(batches):
        inputs, targets = make_batch(windows, batch_size, device)
        with autocast_context(device, precision_dtype):
            _, loss = model(inputs, targets)
        if not torch.isfinite(loss):
            raise FloatingPointError("Non-finite instruction validation loss")
        losses.append(float(loss.item()))
    model.train()
    return sum(losses) / len(losses)


def save_checkpoint(path, model, optimizer, scaler, base_payload, training, step, best_loss):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 2,
        "model_name": "KodexInstructionLM",
        "config": model.config_dict(),
        "model_state_dict": model.state_dict(),
        "tokenizer_kind": base_payload.get("tokenizer_kind", "utf8-bytes"),
        "tokenizer_json": base_payload.get("tokenizer_json"),
        "optimizer_state_dict": optimizer.state_dict(),
        "scaler_state_dict": scaler.state_dict(),
        "training": training,
        "global_step": step,
        "best_validation_loss": best_loss,
        "torch_rng_state": torch.get_rng_state(),
        "cuda_rng_states": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else [],
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    torch.save(payload, temporary)
    temporary.replace(path)


def main():
    args = parse_args()
    for name, value in (
        ("steps", args.steps),
        ("batch-size", args.batch_size),
        ("gradient-accumulation-steps", args.gradient_accumulation_steps),
        ("eval-interval", args.eval_interval),
        ("eval-batches", args.eval_batches),
    ):
        if value < 1:
            raise SystemExit(f"{name} must be positive")
    if args.save_every < 0 or args.warmup_steps < 0:
        raise SystemExit("save-every and warmup-steps must be non-negative")
    if args.learning_rate <= 0 or args.min_learning_rate < 0 or args.min_learning_rate > args.learning_rate:
        raise SystemExit("Learning rates must satisfy 0 <= min-learning-rate <= learning-rate")
    if args.weight_decay < 0 or not 0.0 <= args.decay_ratio <= 1.0:
        raise SystemExit("weight-decay must be non-negative and decay-ratio must be in [0, 1]")

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

    base_path = args.checkpoint.resolve(strict=True)
    base_bytes = base_path.read_bytes()
    base_payload = torch.load(base_path, map_location="cpu", weights_only=True)
    if "model_state_dict" not in base_payload or "config" not in base_payload:
        raise SystemExit("Base checkpoint is missing model weights or configuration")
    config = ModelConfig(**base_payload["config"])

    tokenizer = None
    tokenizer_kind = base_payload.get("tokenizer_kind", "utf8-bytes")
    if tokenizer_kind == "byte-level-bpe":
        try:
            from tokenizers import Tokenizer
        except ImportError as error:
            raise SystemExit("Install tokenizers to fine-tune a BPE checkpoint") from error
        tokenizer_json = base_payload.get("tokenizer_json")
        if not isinstance(tokenizer_json, str) or not tokenizer_json:
            raise SystemExit("Base checkpoint is missing its BPE tokenizer")
        tokenizer = Tokenizer.from_str(tokenizer_json)

    train_path = args.data.resolve(strict=True)
    validation_path = args.validation_data.resolve(strict=True)
    train_windows, train_example_count = load_windows(train_path, tokenizer_kind, tokenizer, config.block_size)
    validation_windows, validation_example_count = load_windows(
        validation_path, tokenizer_kind, tokenizer, config.block_size
    )
    model = KodexLanguageModel(config).to(device)
    model.load_state_dict(base_payload["model_state_dict"])
    optimizer = make_optimizer(model, args.learning_rate, args.weight_decay)
    use_fp16_scaler = device.type == "cuda" and effective_precision == "fp16"
    scaler = torch.amp.GradScaler("cuda", enabled=use_fp16_scaler)

    step = 0
    best_loss = math.inf
    if args.resume_from is not None:
        resume_payload = torch.load(args.resume_from.resolve(strict=True), map_location="cpu", weights_only=True)
        if resume_payload.get("model_name") != "KodexInstructionLM":
            raise SystemExit("Resume checkpoint is not a Kodex instruction checkpoint")
        if resume_payload.get("config") != base_payload.get("config"):
            raise SystemExit("Resume checkpoint architecture differs from the selected base checkpoint")
        model.load_state_dict(resume_payload["model_state_dict"])
        optimizer.load_state_dict(resume_payload["optimizer_state_dict"])
        if resume_payload.get("scaler_state_dict"):
            scaler.load_state_dict(resume_payload["scaler_state_dict"])
        step = int(resume_payload.get("global_step", 0))
        best_loss = float(resume_payload.get("best_validation_loss", math.inf))
        if resume_payload.get("torch_rng_state") is not None:
            torch.set_rng_state(resume_payload["torch_rng_state"])
        cuda_states = resume_payload.get("cuda_rng_states", [])
        if device.type == "cuda" and cuda_states and len(cuda_states) == torch.cuda.device_count():
            torch.cuda.set_rng_state_all(cuda_states)
        if step >= args.steps:
            raise SystemExit("Resume checkpoint already reached --steps; choose a larger total step count")

    output_path = args.output.resolve()
    training = {
        "stage": "supervised_instruction_fine_tuning",
        "base_checkpoint_sha256": hashlib.sha256(base_bytes).hexdigest(),
        "base_checkpoint": str(base_path),
        "data_sha256": hashlib.sha256(train_path.read_bytes()).hexdigest(),
        "validation_sha256": hashlib.sha256(validation_path.read_bytes()).hexdigest(),
        "training_examples": train_example_count,
        "validation_examples": validation_example_count,
        "training_windows": len(train_windows),
        "validation_windows": len(validation_windows),
        "tokenizer_kind": tokenizer_kind,
        "pretrained_weights": base_payload.get("training", {}).get("pretrained_weights", False),
        "learning_rate": args.learning_rate,
        "weight_decay": args.weight_decay,
        "batch_size": args.batch_size,
        "gradient_accumulation_steps": args.gradient_accumulation_steps,
        "precision": effective_precision,
        "seed": args.seed,
    }
    print(json.dumps({
        "status": "sft_started",
        "device": str(device),
        "precision": effective_precision,
        "config": model.config_dict(),
        "training_examples": train_example_count,
        "validation_examples": validation_example_count,
        "training_windows": len(train_windows),
        "validation_windows": len(validation_windows),
        "resume_step": step,
        "base_checkpoint_sha256": training["base_checkpoint_sha256"],
    }, sort_keys=True))

    warmup_steps = min(args.warmup_steps, max(0, args.steps - 1))
    started = time.time()
    model.train()
    for current_step in range(step + 1, args.steps + 1):
        learning_rate = learning_rate_at_step(
            current_step, args.steps, args.learning_rate, args.min_learning_rate,
            warmup_steps, args.decay_ratio
        )
        for group in optimizer.param_groups:
            group["lr"] = learning_rate
        optimizer.zero_grad(set_to_none=True)
        accumulated_loss = 0.0

        for _ in range(args.gradient_accumulation_steps):
            inputs, targets = make_batch(train_windows, args.batch_size, device)
            with autocast_context(device, precision_dtype):
                _, loss = model(inputs, targets)
            if not torch.isfinite(loss):
                raise FloatingPointError(f"Non-finite SFT loss at step {current_step}")
            accumulated_loss += float(loss.detach().item())
            scaler.scale(loss / args.gradient_accumulation_steps).backward()

        scaler.unscale_(optimizer)
        grad_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        if not torch.isfinite(grad_norm):
            raise FloatingPointError(f"Non-finite SFT gradient norm at step {current_step}")
        scaler.step(optimizer)
        scaler.update()

        if current_step == 1 or current_step % args.eval_interval == 0 or current_step == args.steps:
            validation_loss = evaluate(
                model, validation_windows, args.batch_size, device, precision_dtype, args.eval_batches
            )
            if validation_loss < best_loss:
                best_loss = validation_loss
                save_checkpoint(
                    output_path.with_name(output_path.stem + "-best" + output_path.suffix),
                    model, optimizer, scaler, base_payload, training, current_step, best_loss
                )
            print(json.dumps({
                "step": current_step,
                "steps": args.steps,
                "learning_rate": learning_rate,
                "microbatch_loss": accumulated_loss / args.gradient_accumulation_steps,
                "validation_loss": validation_loss,
                "best_validation_loss": best_loss,
                "gradient_norm": float(grad_norm.item()),
                "elapsed_seconds": round(time.time() - started, 2),
            }, sort_keys=True))

        if args.save_every and current_step % args.save_every == 0:
            save_checkpoint(
                output_path, model, optimizer, scaler, base_payload, training, current_step, best_loss
            )

    save_checkpoint(output_path, model, optimizer, scaler, base_payload, training, args.steps, best_loss)
    print(json.dumps({
        "status": "sft_checkpoint_saved",
        "path": str(output_path),
        "best_checkpoint": str(output_path.with_name(output_path.stem + "-best" + output_path.suffix)),
        "steps": args.steps,
        "elapsed_seconds": round(time.time() - started, 2),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
