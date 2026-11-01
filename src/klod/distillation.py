import json
import re
from pathlib import Path
from typing import Iterator


def read_seed_prompts(path: Path) -> list[dict]:
    rows = []
    seen = set()
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            prompt = row.get("prompt")
            domain = row.get("domain")
            language = row.get("language", "pt")
            if not isinstance(prompt, str) or not prompt.strip():
                raise ValueError(f"{path}:{line_number}: prompt must be non-empty text")
            if not isinstance(domain, str) or not domain.strip():
                raise ValueError(f"{path}:{line_number}: domain must be non-empty text")
            if not isinstance(language, str) or not language.strip():
                raise ValueError(f"{path}:{line_number}: language must be non-empty text")
            normalized = re.sub(r"\s+", " ", prompt.casefold()).strip()
            if normalized in seen:
                continue
            seen.add(normalized)
            rows.append({
                "id": str(row.get("id") or f"seed-{line_number:05d}"),
                "domain": domain.strip(),
                "language": language.strip(),
                "prompt": prompt.strip(),
            })
    if not rows:
        raise ValueError(f"No valid prompts found in {path}")
    return rows


def answer_quality_issue(prompt: str, answer: str, min_chars: int = 40,
                         max_chars: int = 16000) -> str | None:
    if not isinstance(answer, str) or not answer.strip():
        return "empty_answer"
    value = answer.strip()
    if value.casefold() == prompt.strip().casefold():
        return "prompt_echo"
    if len(value) < min_chars:
        return "answer_too_short"
    if len(value) > max_chars:
        return "answer_too_long"
    tokens = re.findall(r"\w+", value.casefold())
    if len(tokens) >= 40 and len(set(tokens)) / len(tokens) < 0.22:
        return "excessive_repetition"
    if len(value.splitlines()) > 250:
        return "too_many_lines"
    return None


def approved_candidates(path: Path) -> Iterator[dict]:
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            if row.get("approved") is not True:
                continue
            if row.get("quality_passed") is not True:
                raise ValueError(f"{path}:{line_number}: candidate did not pass automated quality checks")
            messages = row.get("messages")
            if not isinstance(messages, list) or len(messages) < 2:
                raise ValueError(f"{path}:{line_number}: approved candidate has invalid messages")
            if any(not isinstance(item, dict) for item in messages):
                raise ValueError(f"{path}:{line_number}: messages must be JSON objects")
            if messages[-1].get("role") != "assistant":
                raise ValueError(f"{path}:{line_number}: final message must be assistant")
            if any(item.get("role") not in {"system", "user", "assistant"}
                   or not isinstance(item.get("content"), str)
                   or not item["content"].strip() for item in messages):
                raise ValueError(f"{path}:{line_number}: every message needs a valid role and text content")
            approved = dict(row)
            approved["review_status"] = "approved"
            yield approved


def export_approved(input_path: Path, output_path: Path, minimum: int = 20) -> dict:
    if minimum < 1:
        raise ValueError("minimum must be at least 1")
    rows = list(approved_candidates(input_path))
    if len(rows) < minimum:
        raise ValueError(f"Only {len(rows)} approved examples; at least {minimum} are required")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
    temporary.replace(output_path)
    domains = {}
    for row in rows:
        domain = str(row.get("domain", "general"))
        domains[domain] = domains.get(domain, 0) + 1
    return {"approved_examples": len(rows), "domains": domains, "output": str(output_path)}
