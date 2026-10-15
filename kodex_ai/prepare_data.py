from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from kodex_ai.corpus import load_records


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate, deduplicate and report a Kodex JSONL or text corpus.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    input_path = Path(args.input)
    records = load_records(input_path)
    digest = hashlib.sha256()
    total_chars = 0
    for record in records:
        digest.update(record.encode("utf-8"))
        digest.update(b"\n")
        total_chars += len(record)
    report = {
        "input": str(input_path),
        "unique_examples": len(records),
        "characters": total_chars,
        "sha256_of_cleaned_records": digest.hexdigest(),
        "validation": "passed",
        "notes": [
            "This checks file structure, UTF-8 text, de-duplication, and size limits; it does not verify factual correctness or content licenses.",
            "Keep a separate validation set and verify licensing, privacy, and provenance before using large external corpora.",
        ],
    }
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps({"text": record}, ensure_ascii=False) + "\n")
        report["cleaned_output"] = str(output)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
