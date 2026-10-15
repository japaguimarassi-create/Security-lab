from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable


MAX_CORPUS_BYTES = 512 * 1024 * 1024
MAX_EXAMPLE_CHARS = 200_000


def render_dialogue(item: dict) -> str:
    if isinstance(item.get("text"), str) and item["text"].strip():
        return item["text"].strip()
    prompt = item.get("prompt")
    answer = item.get("answer")
    if isinstance(prompt, str) and isinstance(answer, str) and prompt.strip() and answer.strip():
        mode = str(item.get("mode", "chat")).strip().lower()
        if mode == "build":
            return "Pedido de construção: " + prompt.strip() + "\nProposta: " + answer.strip()
        return "Usuário: " + prompt.strip() + "\nKodex: " + answer.strip()
    messages = item.get("messages")
    if isinstance(messages, list):
        rendered = []
        for message in messages:
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                role = str(message.get("role", "texto")).strip()[:32]
                rendered.append(role + ": " + message["content"].strip())
        if rendered:
            return "\n".join(rendered)
    return ""


def load_records(path: str | Path) -> list[str]:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Corpus not found: {source}")
    if source.stat().st_size > MAX_CORPUS_BYTES:
        raise ValueError("Corpus exceeds the 512 MiB safety limit")
    if source.suffix.lower() == ".txt" or source.suffix.lower() == ".md":
        raw = source.read_text(encoding="utf-8", errors="strict")
        chunks = [chunk.strip() for chunk in raw.split("\n\n") if chunk.strip()]
        records = [chunk for chunk in chunks if len(chunk) <= MAX_EXAMPLE_CHARS]
    else:
        records = []
        with source.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(f"Invalid JSONL on line {line_number}: {error.msg}") from error
                if not isinstance(item, dict):
                    raise ValueError(f"JSONL line {line_number} must be an object")
                text = render_dialogue(item)
                if text and len(text) <= MAX_EXAMPLE_CHARS:
                    records.append(text)
    unique: list[str] = []
    seen: set[str] = set()
    for record in records:
        clean = record.replace("\r\n", "\n").replace("\r", "\n")
        clean = "\n".join(line.rstrip() for line in clean.split("\n")).strip()
                identity = clean.casefold()
        key = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        if clean and key not in seen:
            unique.append(clean)
            seen.add(key)
    if len(unique) < 2:
        raise ValueError("At least two unique text examples are required for a train/validation split")
    return unique


def split_records(
    records: list[str],
    validation_fraction: float = 0.1,
    seed: int = 42,
) -> tuple[list[str], list[str]]:
    if not 0.05 <= validation_fraction <= 0.4:
        raise ValueError("validation_fraction must be between 0.05 and 0.4")
    if len(records) < 2:
        raise ValueError("At least two examples are required")
    import random

    indices = list(range(len(records)))
    random.Random(seed).shuffle(indices)
    validation_count = max(1, round(len(records) * validation_fraction))
    validation_count = min(validation_count, len(records) - 1)
    validation_indices = set(indices[:validation_count])
    train = [record for index, record in enumerate(records) if index not in validation_indices]
    validation = [record for index, record in enumerate(records) if index in validation_indices]
    return train, validation


def encode_records(tokenizer, records: Iterable[str]) -> list[int]:
    return tokenizer.encode("\n\n".join(records) + "\n\n")
