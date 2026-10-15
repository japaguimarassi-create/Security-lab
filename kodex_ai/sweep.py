from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import random
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAX_PLANNABLE_TRIALS = 10_000_000
MAX_WORKERS = 32
LEARNING_RATES = (0.0001, 0.0002, 0.0003, 0.0005)
DROPOUTS = (0.0, 0.05, 0.1, 0.15, 0.2)
WEIGHT_DECAYS = (0.0, 0.01, 0.05)
BATCH_SIZES = (2, 4, 8, 16)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect_db(path: str | Path, initialize: bool = True) -> sqlite3.Connection:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=30000")
    connection.execute("PRAGMA synchronous=NORMAL")
    if not initialize:
        return connection
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS trials (
            trial_id TEXT PRIMARY KEY,
            trial_index INTEGER NOT NULL,
            seed INTEGER NOT NULL,
            learning_rate REAL NOT NULL,
            dropout REAL NOT NULL,
            weight_decay REAL NOT NULL,
            batch_size INTEGER NOT NULL,
            steps INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending', 'running', 'completed', 'failed')),
            created_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            exit_code INTEGER,
            output_dir TEXT NOT NULL,
            error TEXT,
            validation_loss REAL
        )
        """
    )
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(trials)")}
    if "validation_loss" not in columns:
        connection.execute("ALTER TABLE trials ADD COLUMN validation_loss REAL")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_trials_status ON trials(status, trial_index)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_trials_validation_loss ON trials(status, validation_loss)")
    connection.commit()
    return connection

def enqueue_trials(
    db_path: str | Path,
    trials: int,
    seed: int = 42,
    steps: int = 100,
    output_root: str | Path = "artifacts/kodex-sweep",
) -> dict:
    if not 1 <= trials <= MAX_PLANNABLE_TRIALS:
        raise ValueError(f"trials must be between 1 and {MAX_PLANNABLE_TRIALS:,}")
    if steps < 1:
        raise ValueError("steps must be positive")
    rng = random.Random(seed)
    output_root = str(output_root)
    connection = connect_db(db_path)
    inserted = 0
    try:
        connection.execute("BEGIN IMMEDIATE")
        now = utc_now()
        rows = []
        for index in range(trials):
            trial_id = f"s{seed}-t{index:08d}"
            config = {
                "trial_id": trial_id,
                "trial_index": index,
                "seed": seed + index,
                "learning_rate": rng.choice(LEARNING_RATES),
                "dropout": rng.choice(DROPOUTS),
                "weight_decay": rng.choice(WEIGHT_DECAYS),
                "batch_size": rng.choice(BATCH_SIZES),
                "steps": steps,
                "status": "pending",
                "created_at": now,
                "output_dir": str(Path(output_root) / trial_id),
            }
            rows.append(tuple(config.values()))
            if len(rows) >= 5000:
                cursor = connection.executemany(
                    """
                    INSERT OR IGNORE INTO trials (
                        trial_id, trial_index, seed, learning_rate, dropout,
                        weight_decay, batch_size, steps, status, created_at, output_dir
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
                inserted += cursor.rowcount
                rows.clear()
        if rows:
            cursor = connection.executemany(
                """
                INSERT OR IGNORE INTO trials (
                    trial_id, trial_index, seed, learning_rate, dropout,
                    weight_decay, batch_size, steps, status, created_at, output_dir
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            inserted += cursor.rowcount
        total_trials = connection.execute("SELECT COUNT(*) FROM trials").fetchone()[0]
        if total_trials > MAX_PLANNABLE_TRIALS:
            raise ValueError(f"Queue would exceed the {MAX_PLANNABLE_TRIALS:,}-trial limit")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    return {"requested": trials, "inserted": inserted, "duplicates_skipped": trials - inserted, "database": str(db_path)}


def claim_trial(db_path: str | Path):
    connection = connect_db(db_path, initialize=False)
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT * FROM trials WHERE status='pending' ORDER BY trial_index, created_at LIMIT 1"
        ).fetchone()
        if row is None:
            connection.commit()
            return None
        cursor = connection.execute(
            "UPDATE trials SET status='running', started_at=? WHERE trial_id=? AND status='pending'",
            (utc_now(), row["trial_id"]),
        )
        if cursor.rowcount != 1:
            connection.rollback()
            return None
        connection.commit()
        return dict(row)
    finally:
        connection.close()


def finish_trial(db_path: str | Path, trial_id: str, return_code: int, error: str | None = None) -> None:
    connection = connect_db(db_path, initialize=False)
    try:
        validation_loss = None
        row = connection.execute("SELECT output_dir FROM trials WHERE trial_id=?", (trial_id,)).fetchone()
        if return_code == 0 and row:
            summary_path = Path(row["output_dir"]) / "training_summary.json"
            if not summary_path.is_absolute():
                summary_path = ROOT / summary_path
            try:
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
                candidate = summary.get("final_metrics", {}).get("validation_loss")
                if candidate is not None:
                    validation_loss = float(candidate)
            except (OSError, ValueError, TypeError):
                validation_loss = None
        connection.execute(
            "UPDATE trials SET status=?, finished_at=?, exit_code=?, error=?, validation_loss=? WHERE trial_id=?",
            ("completed" if return_code == 0 else "failed", utc_now(), return_code, error, validation_loss, trial_id),
        )
        connection.commit()
    finally:
        connection.close()


def trial_worker(db_path: str, dataset: str, device: str, timeout: int, log_root: str, stop: threading.Event):
    trial = claim_trial(db_path)
    if not trial:
        return None
    output_dir = Path(trial["output_dir"])
    log_dir = Path(log_root)
    output_dir_path = output_dir if output_dir.is_absolute() else ROOT / output_dir
    log_dir_path = log_dir if log_dir.is_absolute() else ROOT / log_dir
    log_dir_path.mkdir(parents=True, exist_ok=True)
    output_dir_path.mkdir(parents=True, exist_ok=True)
    log_path = log_dir_path / f"{trial['trial_id']}.log"
    command = [
        sys.executable, "-m", "kodex_ai.train",
        "--data", dataset,
        "--output-dir", str(output_dir_path),
        "--steps", str(trial["steps"]),
        "--batch-size", str(trial["batch_size"]),
        "--learning-rate", str(trial["learning_rate"]),
        "--dropout", str(trial["dropout"]),
        "--weight-decay", str(trial["weight_decay"]),
        "--seed", str(trial["seed"]),
        "--split-seed", str(trial.get("split_seed", 42)),
        "--device", device,
    ]
    started = time.monotonic()
    try:
        with log_path.open("w", encoding="utf-8") as log_file:
            log_file.write(json.dumps({"trial": trial, "command": command}, ensure_ascii=False) + "\n")
            log_file.flush()
            completed = subprocess.run(
                command,
                cwd=ROOT,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                timeout=timeout if timeout > 0 else None,
                check=False,
            )
        finish_trial(db_path, trial["trial_id"], completed.returncode)
        return {
            "trial_id": trial["trial_id"],
            "status": "completed" if completed.returncode == 0 else "failed",
            "exit_code": completed.returncode,
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "log": str(log_path),
        }
    except subprocess.TimeoutExpired:
        finish_trial(db_path, trial["trial_id"], 124, f"Timed out after {timeout} seconds")
        return {"trial_id": trial["trial_id"], "status": "failed", "exit_code": 124, "error": "timeout", "log": str(log_path)}
    except Exception as error:
        finish_trial(db_path, trial["trial_id"], 1, str(error)[:1000])
        return {"trial_id": trial["trial_id"], "status": "failed", "exit_code": 1, "error": str(error), "log": str(log_path)}


def summarize(db_path: str | Path) -> dict:
    db_file = Path(db_path)
    connection = connect_db(db_file, initialize=not db_file.exists())
    try:
        counts = {row["status"]: row["count"] for row in connection.execute(
            "SELECT status, COUNT(*) AS count FROM trials GROUP BY status"
        )}
        pending = connection.execute("SELECT COUNT(*) FROM trials").fetchone()[0]
        best = connection.execute(
            """
            SELECT trial_id, output_dir, validation_loss FROM trials
            WHERE status='completed' AND validation_loss IS NOT NULL
            ORDER BY validation_loss ASC
            LIMIT 10
            """
        ).fetchall()
        best_metrics = [
            {"trial_id": row["trial_id"], "validation_loss": row["validation_loss"], "output_dir": row["output_dir"]}
            for row in best
        ]
        return {
            "total_trials": pending,
            "counts": {key: counts.get(key, 0) for key in ("pending", "running", "completed", "failed")},
            "best_completed_validation_loss": best_metrics[:10],
        }
    finally:
        connection.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Durable, bounded-concurrency queue for Kodex training experiments.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan = subparsers.add_parser("plan", help="Create experiment rows without launching training")
    plan.add_argument("--trials", type=int, default=1_000_000)
    plan.add_argument("--steps", type=int, default=100)
    plan.add_argument("--seed", type=int, default=42)
    plan.add_argument("--db", default="artifacts/kodex-sweep/jobs.sqlite3")
    plan.add_argument("--output-root", default="artifacts/kodex-sweep/runs")

    run = subparsers.add_parser("run", help="Run queued experiments using a bounded local worker pool")
    run.add_argument("--workers", type=int, default=1)
    run.add_argument("--max-completions", type=int, default=1, help="0 drains pending jobs; otherwise limit this run")
    run.add_argument("--db", default="artifacts/kodex-sweep/jobs.sqlite3")
    run.add_argument("--data", default="training/data/mobile_dialogue.jsonl")
    run.add_argument("--device", choices=("auto", "cpu", "cuda", "mps"), default="auto")
    run.add_argument("--timeout", type=int, default=0, help="Per-trial timeout in seconds; 0 disables the timeout")
    run.add_argument("--log-root", default="artifacts/kodex-sweep/logs")

    status = subparsers.add_parser("status", help="Summarize the persisted experiment queue")
    status.add_argument("--db", default="artifacts/kodex-sweep/jobs.sqlite3")

    retry = subparsers.add_parser("retry-failed", help="Requeue failed trials for an explicit repeat")
    retry.add_argument("--db", default="artifacts/kodex-sweep/jobs.sqlite3")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "plan":
        report = enqueue_trials(args.db, args.trials, args.seed, args.steps, args.output_root)
        report["queue"] = summarize(args.db)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    if args.command == "status":
        print(json.dumps(summarize(args.db), ensure_ascii=False, indent=2))
        return 0
    if args.command == "retry-failed":
        connection = connect_db(args.db)
        try:
            cursor = connection.execute(
                "UPDATE trials SET status='pending', started_at=NULL, finished_at=NULL, exit_code=NULL, error=NULL WHERE status='failed'"
            )
            connection.commit()
            print(json.dumps({"requeued": cursor.rowcount, "queue": summarize(args.db)}, ensure_ascii=False, indent=2))
            return 0
        finally:
            connection.close()
    cpu_limit = max(1, os.cpu_count() or 1)
    worker_limit = min(MAX_WORKERS, cpu_limit)
    if not 1 <= args.workers <= worker_limit:
        raise ValueError(f"workers must be between 1 and {worker_limit} for this machine")
    if args.max_completions < 0:
        raise ValueError("max-completions cannot be negative")
    summary = summarize(args.db)
    if summary["counts"]["pending"] == 0:
        print("No pending trials. Run the plan command first.")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    limit = args.max_completions
    target = args.workers if limit == 0 else min(limit, args.workers)
    completed = 0
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        pending = set()
        for _ in range(target):
            pending.add(pool.submit(trial_worker, args.db, args.data, args.device, args.timeout, args.log_root, threading.Event()))
        while pending:
            done, pending = concurrent.futures.wait(pending, return_when=concurrent.futures.FIRST_COMPLETED)
            for future in done:
                result = future.result()
                if result:
                    results.append(result)
                    completed += 1
                    print(json.dumps(result, ensure_ascii=False))
            can_start_more = limit == 0 or completed + len(pending) < limit
            while can_start_more and len(pending) < args.workers:
                if summarize(args.db)["counts"]["pending"] == 0:
                    break
                future = pool.submit(trial_worker, args.db, args.data, args.device, args.timeout, args.log_root, threading.Event())
                pending.add(future)
                if limit and completed + len(pending) >= limit:
                    break
    print(json.dumps({"queue": summarize(args.db), "finished_this_run": completed}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
