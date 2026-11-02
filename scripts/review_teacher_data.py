import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("data/generated/teacher_candidates.jsonl"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    destination = args.output or args.input
    if not args.input.is_file():
        raise SystemExit(f"Candidate dataset not found: {args.input}")

    rows = []
    with args.input.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{args.input}:{line_number}: invalid JSON") from exc
            if not isinstance(row, dict):
                raise SystemExit(f"{args.input}:{line_number}: expected a JSON object")
            rows.append(row)

    approved = rejected = skipped = 0
    for index, row in enumerate(rows, 1):
        if not row.get("quality_passed", False):
            print(f"\n[{index}/{len(rows)}] {row.get('id', 'unknown')} - AUTO-REJECTED: {row.get('quality_issue')}")
            row["approved"] = False
            row["review_status"] = "rejected_by_quality_gate"
            rejected += 1
            continue
        messages = row.get("messages", [])
        if len(messages) < 2:
            print(f"\n[{index}/{len(rows)}] {row.get('id', 'unknown')} - INVALID MESSAGE FORMAT")
            row["approved"] = False
            row["review_status"] = "rejected_invalid"
            rejected += 1
            continue
        print("\n" + "=" * 88)
        print(f"[{index}/{len(rows)}] {row.get('id')} | {row.get('domain')} | {row.get('language')}")
        print("\nPROMPT:\n" + messages[-2]["content"])
        print("\nTEACHER ANSWER:\n" + messages[-1]["content"])
        while True:
            choice = input("\nApprove this answer? [y]es / [n]o / [s]kip / [q]uit: ").strip().lower()
            if choice in {"y", "yes", "n", "no", "s", "skip", "q", "quit"}:
                break
            print("Enter y, n, s or q.")
        if choice in {"q", "quit"}:
            skipped += len(rows) - index + 1
            break
        if choice in {"y", "yes"}:
            row["approved"] = True
            row["review_status"] = "approved"
            row["review_notes"] = "Explicitly approved in interactive review"
            approved += 1
        elif choice in {"n", "no"}:
            row["approved"] = False
            row["review_status"] = "rejected_by_reviewer"
            rejected += 1
        else:
            row["approved"] = False
            row["review_status"] = "pending"
            skipped += 1

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
    temporary.replace(destination)
    print(json.dumps({
        "approved": approved, "rejected": rejected, "skipped": skipped,
        "candidate_file": str(destination),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
