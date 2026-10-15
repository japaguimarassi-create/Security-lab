from __future__ import annotations

import argparse
import json
import math
import os
import random
import time
from pathlib import Path

import torch
import torch.distributed as distributed
from torch import nn
from torch.nn.parallel import DistributedDataParallel

from kodex_ai.corpus import encode_records, load_records, split_records
from kodex_ai.model import KodexTransformer, ModelConfig, parameter_count
from kodex_ai.tokenizer import ByteBPETokenizer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train Kodex's local decoder-only language model from scratch.")
    parser.add_argument("--data", default="training/data/mobile_dialogue.jsonl")
    parser.add_argument("--output-dir", default="artifacts/kodex-ai-run")
    parser.add_argument("--steps", type=int, default=1000)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--block-size", type=int, default=128)
    parser.add_argument("--vocab-size", type=int, default=1024)
    parser.add_argument("--layers", type=int, default=4)
    parser.add_argument("--heads", type=int, default=6)
    parser.add_argument("--embedding-size", type=int, default=192)
    parser.add_argument("--feed-forward-size", type=int, default=768)
    parser.add_argument("--dropout", type=float, default=0.1)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--validation-fraction", type=float, default=0.1)
    parser.add_argument("--eval-interval", type=int, default=50)
    parser.add_argument("--eval-batches", type=int, default=4)
    parser.add_argument("--checkpoint-interval", type=int, default=250)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda", "mps"), default="auto")
    parser.add_argument("--resume", default="")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def choose_device(requested: str, local_rank: int = 0) -> torch.device:
    if requested == "cpu":
        return torch.device("cpu")
    if requested == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("--device cuda was requested but CUDA is unavailable")
        return torch.device("cuda", local_rank)
    if requested == "mps":
        if not (hasattr(torch.backends, "mps") and torch.backends.mps.is_available()):
            raise RuntimeError("--device mps was requested but MPS is unavailable")
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda", local_rank)
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def ensure_sequence(tokens: list[int], block_size: int) -> torch.Tensor:
    if not tokens:
        raise ValueError("Tokenized corpus is empty")
    required = block_size + 2
    if len(tokens) < required:
        repetitions = math.ceil(required / len(tokens))
        tokens = tokens * repetitions
    return torch.tensor(tokens, dtype=torch.long)


def sample_batch(data: torch.Tensor, batch_size: int, block_size: int, device: torch.device):
    starts = torch.randint(0, data.numel() - block_size, (batch_size,))
    x = torch.stack([data[start : start + block_size] for start in starts])
    y = torch.stack([data[start + 1 : start + block_size + 1] for start in starts])
    return x.to(device, non_blocking=True), y.to(device, non_blocking=True)


@torch.no_grad()
def evaluate(model: nn.Module, train_data: torch.Tensor, val_data: torch.Tensor, args, device):
    was_training = model.training
    model.eval()
    result = {}
    for label, data in (("train", train_data), ("validation", val_data)):
        losses = []
        for _ in range(args.eval_batches):
            x, y = sample_batch(data, args.batch_size, args.block_size, device)
            _, loss = model(x, y)
            losses.append(float(loss.item()))
        result[label + "_loss"] = sum(losses) / max(1, len(losses))
    model.train(was_training)
    return result


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def save_checkpoint(path: Path, model, optimizer, config, tokenizer, step, seed, metrics) -> None:
    raw_model = model.module if isinstance(model, DistributedDataParallel) else model
    payload = {
        "format_version": 1,
        "model_config": config.to_dict(),
        "model_state": raw_model.state_dict(),
        "optimizer_state": optimizer.state_dict(),
        "tokenizer": tokenizer.to_dict(),
        "step": int(step),
        "seed": int(seed),
        "parameter_count": parameter_count(raw_model),
        "metrics": metrics,
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    torch.save(payload, temporary)
    temporary.replace(path)


def main() -> int:
    args = parse_args()
    if args.steps < 1 or args.batch_size < 1 or args.eval_interval < 1:
        raise ValueError("steps, batch-size and eval-interval must be positive")
    if args.eval_batches < 1 or args.checkpoint_interval < 1:
        raise ValueError("eval-batches and checkpoint-interval must be positive")

    world_size = int(os.environ.get("WORLD_SIZE", "1"))
    rank = int(os.environ.get("RANK", "0"))
    local_rank = int(os.environ.get("LOCAL_RANK", "0"))
    distributed_run = world_size > 1
    device = choose_device(args.device, local_rank)
    if distributed_run:
        if args.device == "mps":
            raise RuntimeError("Distributed MPS training is not supported by this runner")
        if device.type == "cuda":
            torch.cuda.set_device(device)
        backend = "nccl" if device.type == "cuda" else "gloo"
        distributed.init_process_group(backend=backend)

    try:
        torch.manual_seed(args.seed)
        random.seed(args.seed)
        if device.type == "cuda":
            torch.cuda.manual_seed_all(args.seed)

        records = load_records(args.data)
        train_records, val_records = split_records(records, args.validation_fraction, args.seed)
        if args.resume:
            checkpoint = torch.load(args.resume, map_location="cpu", weights_only=False)
            tokenizer = ByteBPETokenizer.from_dict(checkpoint["tokenizer"])
            config = ModelConfig(**checkpoint["model_config"])
        else:
            tokenizer = ByteBPETokenizer.train(train_records, args.vocab_size)
            config = ModelConfig(
                vocab_size=tokenizer.vocab_size,
                block_size=args.block_size,
                n_layer=args.layers,
                n_head=args.heads,
                n_embd=args.embedding_size,
                n_ff=args.feed_forward_size,
                dropout=args.dropout,
            )
        config.validate()
        if args.resume:
            if config.block_size != args.block_size:
                raise ValueError("Resume checkpoint block_size differs; repeat the original --block-size value")
            if config.vocab_size != tokenizer.vocab_size:
                raise ValueError("Checkpoint tokenizer and model vocabularies differ")

        train_data = ensure_sequence(encode_records(tokenizer, train_records), config.block_size)
        val_data = ensure_sequence(encode_records(tokenizer, val_records), config.block_size)
        model = KodexTransformer(config).to(device)
        parameter_total = parameter_count(model)
        if args.resume:
            model.load_state_dict(checkpoint["model_state"])
        if args.dry_run:
            if rank == 0:
                print(json.dumps({
                    "status": "validated",
                    "model": "KodexTransformer",
                    "parameter_count": parameter_total,
                    "vocab_size": config.vocab_size,
                    "train_examples": len(train_records),
                    "validation_examples": len(val_records),
                    "train_tokens": train_data.numel(),
                    "validation_tokens": val_data.numel(),
                    "device": str(device),
                    "world_size": world_size,
                    "warning": "Dry-run validates configuration and data; no optimizer step was executed.",
                }, ensure_ascii=False, indent=2))
            return 0

        output_dir = Path(args.output_dir)
        checkpoints = (output_dir / "checkpoint_best.pt", output_dir / "checkpoint_last.pt")
        if not args.resume and any(path.exists() for path in checkpoints):
            raise FileExistsError(
                f"Checkpoints already exist in {output_dir}. Choose a new --output-dir or resume from checkpoint_last.pt."
            )
        if rank == 0:
            output_dir.mkdir(parents=True, exist_ok=True)
            write_json(output_dir / "config.json", {
                **config.to_dict(),
                "parameter_count": parameter_total,
                "architecture": "decoder-only causal Transformer with tied token/output embeddings",
                "seed": args.seed,
                "dataset": str(Path(args.data)),
                "train_examples": len(train_records),
                "validation_examples": len(val_records),
                "device": str(device),
                "world_size": world_size,
                "api_calls": 0,
            })
            write_json(output_dir / "tokenizer.json", tokenizer.to_dict())
        if distributed_run:
            distributed.barrier()

        if distributed_run:
            model = DistributedDataParallel(
                model,
                device_ids=[local_rank] if device.type == "cuda" else None,
            )
        optimizer = torch.optim.AdamW(
            model.parameters(),
            lr=args.learning_rate,
            weight_decay=args.weight_decay,
        )
        start_step = 0
        if args.resume:
            optimizer.load_state_dict(checkpoint["optimizer_state"])
            start_step = int(checkpoint.get("step", 0))
        if args.steps <= start_step:
            raise ValueError(f"steps={args.steps} must be greater than checkpoint step {start_step}")

        metrics_path = output_dir / "metrics.jsonl"
        last_metrics = {}
        start_time = time.monotonic()
        if rank == 0:
            print(f"Model parameters: {parameter_total:,}")
            print(f"Training examples: {len(train_records)} | validation examples: {len(val_records)}")
            print(f"Device: {device} | workers: {world_size} | steps: {start_step} -> {args.steps}")

        for step in range(start_step + 1, args.steps + 1):
            model.train()
            x, y = sample_batch(train_data, args.batch_size, config.block_size, device)
            optimizer.zero_grad(set_to_none=True)
            _, loss = model(x, y)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            should_evaluate = step % args.eval_interval == 0 or step == args.steps
            if should_evaluate:
                metrics = evaluate(model, train_data, val_data, args, device)
                metrics.update({
                    "step": step,
                    "train_step_loss": float(loss.item()),
                    "elapsed_seconds": round(time.monotonic() - start_time, 3),
                    "tokens_processed_estimate": step * args.batch_size * config.block_size * world_size,
                    "parameter_count": parameter_total,
                    "seed": args.seed,
                })
                last_metrics = metrics
                if rank == 0:
                    with metrics_path.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(metrics, ensure_ascii=False) + "\n")
                    print(
                        f"step={step} train_loss={metrics['train_loss']:.4f} "
                        f"validation_loss={metrics['validation_loss']:.4f} "
                        f"elapsed={metrics['elapsed_seconds']:.1f}s"
                    )
                    if not math.isfinite(metrics["validation_loss"]):
                        raise FloatingPointError("Validation loss is not finite; training stopped")
                    best_path = output_dir / "checkpoint_best.pt"
                    if not best_path.exists():
                        save_checkpoint(best_path, model, optimizer, config, tokenizer, step, args.seed, metrics)
                    else:
                        best = torch.load(best_path, map_location="cpu", weights_only=False)
                        best_loss = best.get("metrics", {}).get("validation_loss", math.inf)
                        if metrics["validation_loss"] < best_loss:
                            save_checkpoint(best_path, model, optimizer, config, tokenizer, step, args.seed, metrics)
            if step % args.checkpoint_interval == 0 or step == args.steps:
                if rank == 0:
                    save_checkpoint(
                        output_dir / "checkpoint_last.pt",
                        model,
                        optimizer,
                        config,
                        tokenizer,
                        step,
                        args.seed,
                        last_metrics,
                    )
                if distributed_run:
                    distributed.barrier()

        if rank == 0:
            write_json(output_dir / "training_summary.json", {
                "status": "completed",
                "steps_completed": args.steps,
                "initial_step": start_step,
                "parameter_count": parameter_total,
                "tokens_processed_estimate": args.steps * args.batch_size * config.block_size * world_size,
                "elapsed_seconds": round(time.monotonic() - start_time, 3),
                "final_metrics": last_metrics,
                "checkpoint": str(output_dir / "checkpoint_last.pt"),
                "note": "Completion means the configured optimizer steps ran; it is not proof of general intelligence or years of equivalent learning.",
            })
            print(f"Training finished. Checkpoint: {output_dir / 'checkpoint_last.pt'}")
        if distributed_run:
            distributed.barrier()
        return 0
    finally:
        if distributed_run and distributed.is_initialized():
            distributed.destroy_process_group()


if __name__ == "__main__":
    raise SystemExit(main())
