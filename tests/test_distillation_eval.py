import json

import pytest

from scripts.evaluate_teacher_student import read_eval_prompts


def test_read_eval_prompts_deduplicates_and_preserves_domains(tmp_path):
    path = tmp_path / "heldout.jsonl"
    rows = [
        {"id": "a", "domain": "science", "language": "pt", "prompt": " Explique energia "},
        {"id": "b", "domain": "science", "language": "pt", "prompt": "explique energia"},
        {"id": "c", "domain": "history", "language": "pt", "prompt": "Explique a Revolução Industrial"},
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    result = read_eval_prompts(path)
    assert [row["id"] for row in result] == ["a", "c"]
    assert result[0]["domain"] == "science"


def test_read_eval_prompts_requires_five_unique_prompts(tmp_path):
    path = tmp_path / "heldout.jsonl"
    row = {"prompt": "Uma pergunta"}
    path.write_text("\n".join(json.dumps(row) for _ in range(5)), encoding="utf-8")
    with pytest.raises(ValueError, match="five unique"):
        read_eval_prompts(path)


def test_read_eval_prompts_rejects_empty_prompt(tmp_path):
    path = tmp_path / "heldout.jsonl"
    path.write_text(json.dumps({"prompt": "  "}), encoding="utf-8")
    with pytest.raises(ValueError, match="non-empty"):
        read_eval_prompts(path)
