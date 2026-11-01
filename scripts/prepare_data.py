import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path

ALLOWED = {"ODC-By-1.0", "CC-BY-4.0", "CC-BY-SA-4.0", "CC0-1.0", "MIT", "Apache-2.0"}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--min-chars", type=int, default=500)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    seen, kept, rejected = set(), 0, 0
    with args.input.open(encoding="utf-8") as source, args.output.open("w", encoding="utf-8") as target:
        for line in source:
            try:
                row = json.loads(line)
                text = unicodedata.normalize("NFC", str(row.get("text", "")))
                text = re.sub(r"\s+", " ", text).strip()
                license_id = str(row.get("license", ""))
                url = str(row.get("source_url", ""))
                if len(text) < args.min_chars or license_id not in ALLOWED or not url.startswith("https://"):
                    rejected += 1
                    continue
                digest = hashlib.sha256(text.casefold().encode()).hexdigest()
                if digest in seen:
                    rejected += 1
                    continue
                seen.add(digest)
                row.update(text=text, content_hash=digest)
                target.write(json.dumps(row, ensure_ascii=False) + "\n")
                kept += 1
            except (ValueError, TypeError):
                rejected += 1
    print(json.dumps({"kept": kept, "rejected": rejected, "unique": len(seen)}))

if __name__ == "__main__":
    main()
