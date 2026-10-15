import argparse
import hashlib
import json
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


MAX_EXAMPLE_BYTES = 64 * 1024


def normalize_text(value):
    value = unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))
    value = "".join(char for char in value if char in "\n\t" or ord(char) >= 32)
    return value.strip()


def canonical_key(value):
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def normalize_corpus(input_paths, output_path, report_path):
    records = []
    seen = set()
    answers_by_prompt = defaultdict(set)
    duplicates = 0
    input_rows = 0
    input_bytes = 0
    modes = Counter()

    for raw_path in input_paths:
        path = Path(raw_path)
        if not path.is_file():
            raise FileNotFoundError(f"Corpus source not found: {path}")
        raw = path.read_bytes()
        input_bytes += len(raw)
        for line_number, line in enumerate(raw.decode("utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            input_rows += 1
            try:
                item = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {error.msg}") from error
            if not isinstance(item, dict):
                raise ValueError(f"{path}:{line_number}: each line must be a JSON object.")
            if isinstance(item.get("prompt"), str) and isinstance(item.get("answer"), str):
                record = {
                    "mode": str(item.get("mode") or "chat").strip().lower(),
                    "prompt": normalize_text(item["prompt"]),
                    "answer": normalize_text(item["answer"]),
                }
                if not record["prompt"] or not record["answer"]:
                    raise ValueError(f"{path}:{line_number}: prompt and answer must not be blank.")
                key = "pair\0" + canonical_key(record["mode"]) + "\0" + canonical_key(record["prompt"]) + "\0" + canonical_key(record["answer"])
                answers_by_prompt[canonical_key(record["prompt"])].add(canonical_key(record["answer"]))
                modes[record["mode"]] += 1
            elif isinstance(item.get("text"), str):
                text = normalize_text(item["text"])
                if not text:
                    continue
                record = {"text": text}
                key = "text\0" + canonical_key(text)
                modes["text"] += 1
            else:
                raise ValueError(f"{path}:{line_number}: expected prompt/answer or text fields.")
            encoded = json.dumps(record, ensure_ascii=False).encode("utf-8")
            if len(encoded) > MAX_EXAMPLE_BYTES:
                raise ValueError(f"{path}:{line_number}: example exceeds 64 KiB.")
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
            records.append(record)

    if len(records) < 10:
        raise ValueError(f"Only {len(records)} unique examples remain; at least 10 are required.")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    encoded_corpus = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(encoded_corpus, encoding="utf-8")
    temporary.replace(output)
    multi_answer_prompts = sum(1 for answers in answers_by_prompt.values() if len(answers) > 1)
    report = {
        "status": "prepared_with_small_corpus_warning" if len(records) < 1000 else "prepared",
        "input_files": [str(path) for path in input_paths],
        "input_bytes": input_bytes,
        "input_examples": input_rows,
        "unique_examples": len(records),
        "duplicates_removed": duplicates,
        "examples_by_mode": dict(modes),
        "prompts_with_multiple_normalized_answers": multi_answer_prompts,
        "output_file": str(output),
        "output_bytes": output.stat().st_size,
        "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "warnings": [
            "The available dialogue corpus is too small to establish broad language ability."
        ] if len(records) < 1000 else [],
    }
    if report_path:
        destination = Path(report_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp_report = destination.with_suffix(destination.suffix + ".tmp")
        temp_report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp_report.replace(destination)
    return report


def main():
    parser = argparse.ArgumentParser(description="Normalize and deduplicate Kodex's local dialogue corpus.")
    parser.add_argument("--input", action="append", required=True, help="JSONL source; repeat to merge multiple sources.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", default="")
    args = parser.parse_args()
    print(json.dumps(normalize_corpus(args.input, args.output, args.report), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
