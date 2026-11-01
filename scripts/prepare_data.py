import argparse
import hashlib
import json
import re
import sqlite3
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

ALLOWED = {"ODC-By-1.0", "CC-BY-4.0", "CC-BY-SA-4.0", "CC0-1.0", "MIT", "Apache-2.0"}

def acceptable(row, min_chars, max_chars):
    text = unicodedata.normalize("NFC", str(row.get("text", "")))
    text = re.sub(r"\s+", " ", text).strip()
    url = urlparse(str(row.get("source_url", "")))
    words = text.split()
    alpha_ratio = sum(char.isalpha() for char in text) / max(1, len(text))
    if len(text) < min_chars or len(text) > max_chars:
        return None
    if url.scheme != "https" or not url.netloc:
        return None
    if row.get("license") not in ALLOWED or not str(row.get("attribution", "")).strip():
        return None
    if alpha_ratio < 0.25 or len(words) < 30:
        return None
    if len(set(words)) / max(1, len(words)) < 0.12:
        return None
    return text

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--min-chars", type=int, default=500)
    parser.add_argument("--max-chars", type=int, default=100000)
    parser.add_argument("--dedupe-db", type=Path, default=Path("data/processed/dedupe.sqlite3"))
    args = parser.parse_args()
    if args.min_chars < 1 or args.max_chars < args.min_chars:
        raise SystemExit("Invalid text length limits")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.dedupe_db.parent.mkdir(parents=True, exist_ok=True)
    kept = rejected = duplicates = 0
    with sqlite3.connect(args.dedupe_db) as dedupe:
        dedupe.execute("CREATE TABLE IF NOT EXISTS hashes (digest TEXT PRIMARY KEY)")
        dedupe.execute("DELETE FROM hashes")
        with args.input.open(encoding="utf-8") as source, args.output.open("w", encoding="utf-8") as target:
            for line in source:
                try:
                    row = json.loads(line)
                    text = acceptable(row, args.min_chars, args.max_chars)
                    if text is None:
                        rejected += 1
                        continue
                    digest = hashlib.sha256(text.casefold().encode("utf-8")).hexdigest()
                    cursor = dedupe.execute("INSERT OR IGNORE INTO hashes(digest) VALUES(?)", (digest,))
                    if cursor.rowcount == 0:
                        duplicates += 1
                        continue
                    row.update(text=text, content_hash=digest)
                    target.write(json.dumps(row, ensure_ascii=False) + "\n")
                    kept += 1
                    if kept % 1000 == 0:
                        dedupe.commit()
                except (ValueError, TypeError, UnicodeError):
                    rejected += 1
        dedupe.commit()
    print(json.dumps({"kept": kept, "rejected": rejected, "duplicates": duplicates}))

if __name__ == "__main__":
    main()
