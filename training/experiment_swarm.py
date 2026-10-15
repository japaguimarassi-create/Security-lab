import argparse
import json
import math
import random
import subprocess
import shutil
import sys
import time
from pathlib import Path


LEARNING_RATES = [1e-4, 2e-4, 3e-4, 5e-4]
WEIGHT_DECAYS = [0.01, 0.05, 0.1, 0.2]
DROPOUTS = [0.0, 0.05, 0.1, 0.15, 0.2]
SEQUENCE_LENGTHS = [64, 128]


def config_for_trial(trial_id, base_seed=42):
    rng = random.Random((base_seed + trial_id * 104729) % (2**32))
    return {
        "trial_id": trial_id,
        "seed": (base_seed + trial_id * 104729) % (2**31 - 1),
        "learning_rate": rng.choice(LEARNING_RATES),
        "weight_decay": rng.choice(WEIGHT_DECAYS),
        "dropout": rng.choice(DROPOUTS),
        "max_seq_len": rng.choice(SEQUENCE_LENGTHS),
    }


def shard_trial_count(total_trials, shard_id, shard_count):
    if total_trials <= shard_id:
        return 0
    return (total_trials - 1 - shard_id) // shard_count + 1


def trial_ids_for_shard(total_trials, shard_id, shard_count, limit=None, batch_index=0):
    if batch_index < 0:
        raise ValueError("batch_index must be non-negative.")
    width = max(1, int(limit or 1))
    start = shard_id + batch_index * width * shard_count
    ids = range(start, total_trials, shard_count)
    if limit is None:
        return ids
    return list(value for _, value in zip(range(limit), ids))


def create_parser():
    parser = argparse.ArgumentParser(
        description="Plan or execute a deterministic, sharded million-scale model experiment queue."
    )
    parser.add_argument("--mode", choices=["plan", "execute"], default="plan")
    parser.add_argument("--total-trials", type=int, default=1000000)
    parser.add_argument("--shard-id", type=int, default=0)
    parser.add_argument("--batch-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=16)
    parser.add_argument("--max-executions", type=int, default=1)
    parser.add_argument("--steps", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--base-seed", type=int, default=42)
    parser.add_argument("--data", default="training/data/mobile_dialogue.jsonl")
    parser.add_argument("--out-dir", default="artifacts/kodex-sweep")
    parser.add_argument("--trial-timeout", type=int, default=1800)
    return parser


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def main():
    args = create_parser().parse_args()
    if args.total_trials < 1 or args.total_trials > 1000000000:
        raise ValueError("total-trials must be between 1 and 1,000,000,000.")
    if args.shard_count < 1 or args.shard_count > 256:
        raise ValueError("shard-count must be between 1 and 256; GitHub Actions also caps a matrix at 256 jobs.")
    if args.shard_id < 0 or args.shard_id >= args.shard_count:
        raise ValueError("shard-id must be within [0, shard-count).")
    if args.batch_index < 0 or args.batch_index > 10000000:
        raise ValueError("batch-index must be between 0 and 10,000,000.")
    if args.max_executions < 0 or args.max_executions > 100:
        raise ValueError("max-executions must be between 0 and 100 per shard.")
    if args.steps < 1 or args.steps > 10000000:
        raise ValueError("steps must be between 1 and 10,000,000.")
    if args.batch_size < 1 or args.batch_size > 256:
        raise ValueError("batch-size must be between 1 and 256.")
    if args.trial_timeout < 1 or args.trial_timeout > 21600:
        raise ValueError("trial-timeout must be between 1 second and 6 hours.")

    trials_in_shard = shard_trial_count(args.total_trials, args.shard_id, args.shard_count)
    batch_width = max(1, args.max_executions)
    already_scheduled = min(trials_in_shard, args.batch_index * batch_width)
    trials_remaining_before_batch = max(0, trials_in_shard - already_scheduled)
    if args.mode == "plan":
        sample_ids = trial_ids_for_shard(
            args.total_trials, args.shard_id, args.shard_count, limit=min(batch_width, max(1, trials_remaining_before_batch)),
            batch_index=args.batch_index,
        )
        plan = {
            "status": "planned_not_executed",
            "total_trials": args.total_trials,
            "shard_count": args.shard_count,
            "max_parallel_jobs_per_github_actions_matrix": 256,
            "requested_shard": args.shard_id,
            "batch_index": args.batch_index,
            "trials_assigned_to_shard": trials_in_shard,
            "trials_already_scheduled_by_prior_batches": already_scheduled,
            "trials_remaining_before_batch": trials_remaining_before_batch,
            "trials_available_in_this_batch": len(sample_ids) if trials_remaining_before_batch else 0,
            "sample_configurations": [config_for_trial(trial_id, args.base_seed) for trial_id in sample_ids],
            "training_steps_per_trial_if_executed": args.steps,
            "note": "Planning creates candidate configurations, not trained models. Use the same shard-count and max-executions across successive batch-index values to avoid overlap. Real concurrency is limited by runner quotas and hardware.",
        }
        write_json(Path(args.out_dir) / "plan.json", plan)
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0

    if args.max_executions == 0:
        raise ValueError("execute mode requires max-executions >= 1.")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    candidates = trial_ids_for_shard(args.total_trials, args.shard_id, args.shard_count, args.max_executions, batch_index=args.batch_index)
    results = []
    started = time.time()
    for trial_id in candidates:
        config = config_for_trial(trial_id, args.base_seed)
        trial_dir = out_dir / f"trial-{trial_id:08d}"
        trial_dir.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable,
            "training/train_kodex_model.py",
            "--data", args.data,
            "--out-dir", str(trial_dir),
            "--steps", str(args.steps),
            "--batch-size", str(args.batch_size),
            "--seed", str(config["seed"]),
            "--learning-rate", str(config["learning_rate"]),
            "--weight-decay", str(config["weight_decay"]),
            "--dropout", str(config["dropout"]),
            "--max-seq-len", str(config["max_seq_len"]),
        ]
        run_started = time.time()
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=args.trial_timeout,
            )
            (trial_dir / "stdout.log").write_text(completed.stdout, encoding="utf-8")
            (trial_dir / "stderr.log").write_text(completed.stderr, encoding="utf-8")
            result = {
                **config,
                "status": "completed" if completed.returncode == 0 else "failed",
                "return_code": completed.returncode,
                "elapsed_seconds": round(time.time() - run_started, 2),
                "metrics": None,
            }
            if completed.returncode != 0:
                diagnostic = completed.stderr[-4000:] or completed.stdout[-2000:]
                result["error_excerpt"] = diagnostic
                print(json.dumps({
                    "event": "trial_error",
                    "trial_id": trial_id,
                    "return_code": completed.returncode,
                    "diagnostic_tail": diagnostic,
                }, ensure_ascii=False), flush=True)
            metrics_path = trial_dir / "metrics.json"
            if completed.returncode == 0 and metrics_path.is_file():
                result["metrics"] = json.loads(metrics_path.read_text(encoding="utf-8"))
            elif completed.returncode == 0:
                result["status"] = "failed"
                result["error"] = "Trainer exited successfully but did not write metrics.json."
        except subprocess.TimeoutExpired as error:
            result = {
                **config,
                "status": "timed_out",
                "return_code": None,
                "elapsed_seconds": round(time.time() - run_started, 2),
                "metrics": None,
                "error": str(error),
            }
        write_json(trial_dir / "result.json", result)
        results.append(result)
        print(json.dumps({
            "event": "trial_finished",
            "trial_id": trial_id,
            "status": result["status"],
            "validation_loss": (result.get("metrics") or {}).get("validation_loss"),
            "elapsed_seconds": result["elapsed_seconds"],
        }), flush=True)

    completed = [item for item in results if item["status"] == "completed" and item.get("metrics")]
    ranked = sorted(
        completed,
        key=lambda item: (item["metrics"].get("validation_loss", float("inf")), item["trial_id"]),
    )
    summary = {
        "status": "execution_finished_with_queue_remaining" if already_scheduled + len(candidates) < trials_in_shard else "shard_finished",
        "total_candidate_trials": args.total_trials,
        "shard_count": args.shard_count,
        "shard_id": args.shard_id,
        "batch_index": args.batch_index,
        "assigned_to_shard": trials_in_shard,
        "trials_already_scheduled_by_prior_batches": already_scheduled,
        "attempted_in_this_run": len(candidates),
        "completed": len(completed),
        "failed_or_timed_out": len(results) - len(completed),
        "not_executed_in_this_run": max(0, trials_in_shard - already_scheduled - len(candidates)),
        "steps_per_trial": args.steps,
        "elapsed_seconds": round(time.time() - started, 2),
        "best_validation_trial": ranked[0] if ranked else None,
        "results": [{key: value for key, value in item.items() if key != "metrics"} | {
            "validation_loss": (item.get("metrics") or {}).get("validation_loss"),
            "test_loss": (item.get("metrics") or {}).get("test_loss"),
        } for item in results],
        "honesty_note": "Unexecuted candidate trials remain pending. A planned experiment or a low loss does not prove human-like language ability.",
    }
    if ranked:
        best_id = ranked[0]["trial_id"]
        best_dir = out_dir / f"trial-{best_id:08d}"
        best_model = best_dir / "model-final.pt"
        best_tokenizer = best_dir / "tokenizer.json"
        if best_model.is_file() and best_tokenizer.is_file():
            shutil.copy2(best_model, out_dir / "best-model.pt")
            shutil.copy2(best_tokenizer, out_dir / "best-model-tokenizer.json")
            write_json(out_dir / "best-model-selection.json", {
                "trial_id": best_id,
                "selection_metric": "validation_loss",
                "validation_loss": ranked[0]["metrics"].get("validation_loss"),
                "test_loss": ranked[0]["metrics"].get("test_loss"),
                "source": str(best_dir / "model-final.pt"),
                "note": "The selected weights are a checkpoint, not proof of useful language quality.",
            })
    best_id = ranked[0]["trial_id"] if ranked else None
    for item in results:
        trial_dir = out_dir / f"trial-{item['trial_id']:08d}"
        checkpoint = trial_dir / "checkpoint-last.pt"
        if checkpoint.exists():
            checkpoint.unlink()
        if item["status"] == "completed":
            for log_name in ("stdout.log", "stderr.log"):
                log_path = trial_dir / log_name
                if log_path.exists():
                    log_path.unlink()
        if item["trial_id"] != best_id:
            for name in ("model-final.pt", "model-best.pt", "tokenizer.json"):
                model_path = trial_dir / name
                if model_path.exists():
                    model_path.unlink()
        else:
            tokenizer_path = trial_dir / "tokenizer.json"
            if tokenizer_path.exists():
                tokenizer_path.unlink()
    write_json(out_dir / "summary.json", summary)
    (out_dir / "results.jsonl").write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in summary["results"]),
        encoding="utf-8",
    )
    print(json.dumps({
        "event": "shard_summary",
        "attempted": summary["attempted_in_this_run"],
        "completed": summary["completed"],
        "not_executed": summary["not_executed_in_this_run"],
        "best_validation_loss": (ranked[0]["metrics"].get("validation_loss") if ranked else None),
        "summary_path": str(out_dir / "summary.json"),
    }, ensure_ascii=False), flush=True)
    return 0 if results and all(item["status"] == "completed" and item.get("metrics") for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
