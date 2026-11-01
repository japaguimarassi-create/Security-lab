import argparse
import json
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--language", default="por_Latn")
    parser.add_argument("--limit", type=int, default=10000)
    parser.add_argument("--output", type=Path, default=Path("data/raw/fineweb2-pt.jsonl"))
    args = parser.parse_args()
    if args.limit < 1:
        raise SystemExit("--limit must be positive")
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise SystemExit("Install the data extra: pip install -e '.[data]'") from exc
    data = load_dataset("HuggingFaceFW/fineweb-2", name=args.language,
                        split="train", streaming=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with args.output.open("w", encoding="utf-8") as output:
        for row in data:
            text = str(row.get("text", "")).strip()
            if not text:
                continue
            output.write(json.dumps({
                "text": text, "source_url": row.get("url", ""),
                "license": "ODC-By-1.0", "language": args.language,
                "attribution": "FineWeb2 / HuggingFaceFW"
            }, ensure_ascii=False) + "\n")
            count += 1
            if count >= args.limit:
                break
    print(f"Saved {count} documents to {args.output}")

if __name__ == "__main__":
    main()
