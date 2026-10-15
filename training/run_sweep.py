import argparse
import concurrent.futures
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRAINER = ROOT / "training" / "train_transformer.py"
LEARNING_RATES = (0.0001, 0.0002, 0.0003, 0.0005, 0.0008)
BATCH_SIZES = (4, 8, 16)
WEIGHT_DECAYS = (0.0, 0.005, 0.01, 0.03)
MAX_TRIALS = 1_000_000
MAX_WORKERS = 32


def trial_config(index, seed):
    rng = random.Random(seed + index * 104729)
    return {
        "trial": index,
        "seed": rng.randrange(1, 2**31 - 1),
        "learning_rate": rng.choice(LEARNING_RATES),
        "batch_size": rng.choice(BATCH_SIZES),
        "weight_decay": rng.choice(WEIGHT_DECAYS)
    }


def run_trial(item):
    index, config, args, output_root = item
    trial_dir = output_root / f"trial-{index:07d}"
    command = [
        sys.executable,
        str(TRAINER),
        "--data", str(args.data.resolve()),
        "--out-dir", str(trial_dir),
        "--steps", str(args.steps),
        "--batch-size", str(config["batch_size"]),
        "--learning-rate", str(config["learning_rate"]),
        "--weight-decay", str(config["weight_decay"]),
        "--seed", str(config["seed"]),
        "--device", "cpu",
        "--eval-every", str(max(1, args.steps // 2)),
        "--eval-batches", str(args.eval_batches)
    ]
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=args.trial_timeout_seconds,
            check=False
        )
        result_path = trial_dir / "result.json"
        if completed.returncode != 0 or not result_path.is_file():
            return {
                **config,
                "status": "failed",
                "return_code": completed.returncode,
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "log_tail": completed.stdout[-4000:]
            }
        result = json.loads(result_path.read_text(encoding="utf-8"))
        return {
            **config,
            "status": "completed",
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "trainable_parameters": result["trainable_parameters"],
            "best_validation_loss": result["best_validation_loss"],
            "checkpoint": str((trial_dir / "best.pt").relative_to(ROOT))
        }
    except subprocess.TimeoutExpired as error:
        return {
            **config,
            "status": "timeout",
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "log_tail": (error.stdout or b"").decode("utf-8", errors="replace")[-2000:] if isinstance(error.stdout, bytes) else (error.stdout or "")[-2000:]
        }
    except Exception as error:
        return {
            **config,
            "status": "failed",
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "error": str(error)
        }


def main():
    parser = argparse.ArgumentParser(description="Plan and run bounded concurrent Kodex model experiments.")
    parser.add_argument("--data", type=Path, default=Path("training/data"))
    parser.add_argument("--out-dir", type=Path, default=Path("training/runs/sweep"))
    parser.add_argument("--trials", type=int, default=1_000_000)
    parser.add_argument("--execute", type=int, default=0)
    parser.add_argument("--workers", type=int, default=max(1, min(2, os.cpu_count() or 1)))
    parser.add_argument("--steps", type=int, default=100)
    parser.add_argument("--eval-batches", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--trial-timeout-seconds", type=int, default=1800)
    args = parser.parse_args()

    if args.trials < 1 or args.trials > MAX_TRIALS:
        raise ValueError(f"trials must be between 1 and {MAX_TRIALS:,}.")
    if args.execute < 0 or args.execute > args.trials:
        raise ValueError("execute must be between zero and trials.")
    if args.workers < 1 or args.workers > MAX_WORKERS:
        raise ValueError(f"workers must be between 1 and {MAX_WORKERS}.")
    if args.steps < 1 or args.eval_batches < 1 or args.trial_timeout_seconds < 1:
        raise ValueError("steps, eval-batches and trial-timeout-seconds must be positive.")
    if not args.data.is_file():
        raise FileNotFoundError(f"Training dataset not found: {args.data}")

    output_root = args.out_dir.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    plan = {
        "system": "Kodex bounded concurrent experiment scheduler",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "logical_trials_requested": args.trials,
        "executions_requested": args.execute,
        "workers": args.workers,
        "steps_per_experiment": args.steps,
        "seed": args.seed,
        "config_space": {
            "learning_rates": LEARNING_RATES,
            "batch_sizes": BATCH_SIZES,
            "weight_decays": WEIGHT_DECAYS
        },
        "scheduling": "Trials are generated lazily from their index; only --execute starts training processes. Concurrency is bounded by --workers.",
        "calendar_equivalence": "Not claimed. Number of trials or steps is not equivalent to years of learning.",
        "data_sha256": __import__("hashlib").sha256(args.data.read_bytes()).hexdigest()
    }
    (output_root / "manifest.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(plan, ensure_ascii=False), flush=True)
    if args.execute == 0:
        print("Plan only: no training processes were started. Pass --execute N to run N actual trials.", flush=True)
        return 0

    started = time.monotonic()
    results_path = output_root / "results.jsonl"
    results_path.write_text("", encoding="utf-8")
    completed = 0
    failed = 0
    best_result = None
    next_index = 0
    pending = {}
    with concurrent.futures.ProcessPoolExecutor(max_workers=min(args.workers, args.execute)) as executor:
        while next_index < args.execute and len(pending) < args.workers:
            config = trial_config(next_index, args.seed)
            future = executor.submit(run_trial, (next_index, config, args, output_root))
            pending[future] = next_index
            next_index += 1

        while pending:
            done, _ = concurrent.futures.wait(pending, return_when=concurrent.futures.FIRST_COMPLETED)
            for future in done:
                pending.pop(future, None)
                result = future.result()
                with results_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(result, ensure_ascii=False) + "\n")
                if result["status"] == "completed":
                    completed += 1
                    if best_result is None or result["best_validation_loss"] < best_result["best_validation_loss"]:
                        best_result = result
                else:
                    failed += 1
                print(json.dumps({"progress": completed + failed, "total": args.execute, **result}, ensure_ascii=False), flush=True)
                if next_index < args.execute:
                    config = trial_config(next_index, args.seed)
                    next_future = executor.submit(run_trial, (next_index, config, args, output_root))
                    pending[next_future] = next_index
                    next_index += 1

    summary = {
        **plan,
        "completed_experiments": completed,
        "failed_experiments": failed,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "best_experiment": best_result,
        "result_file": str(results_path)
    }
    (output_root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0 if completed > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
