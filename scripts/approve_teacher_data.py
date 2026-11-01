import argparse
import json
from pathlib import Path

from klod.distillation import export_approved


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("data/generated/teacher_candidates.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/teacher_approved.jsonl"))
    parser.add_argument("--minimum", type=int, default=20)
    args = parser.parse_args()
    try:
        result = export_approved(args.input, args.output, args.minimum)
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
