import json

import pytest

from klod.distillation import (
    answer_quality_issue,
    approved_candidates,
    export_approved,
    read_seed_prompts,
)
from scripts.training_preflight import inspect_dataset


def test_read_seed_prompts_normalizes_and_deduplicates(tmp_path):
    path = tmp_path / "prompts.jsonl"
    rows = [
        {"id": "a", "domain": "science", "language": "pt", "prompt": " Explique gravidade "},
        {"id": "b", "domain": "science", "language": "pt", "prompt": "explique   gravidade"},
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    result = read_seed_prompts(path)
    assert len(result) == 1
    assert result[0]["prompt"] == "Explique gravidade"


def test_read_seed_prompts_rejects_missing_domain(tmp_path):
    path = tmp_path / "prompts.jsonl"
    path.write_text(json.dumps({"prompt": "Explique algo"}), encoding="utf-8")
    with pytest.raises(ValueError, match="domain"):
        read_seed_prompts(path)


def test_answer_quality_screen():
    assert answer_quality_issue("Pergunta", "Uma resposta suficientemente desenvolvida.") is None
    assert answer_quality_issue("Pergunta", "curta", min_chars=20) == "answer_too_short"
    assert answer_quality_issue("Repita", "Repita") == "prompt_echo"
    repeated = " ".join(["eco"] * 60)
    assert answer_quality_issue("Pergunta", repeated) == "excessive_repetition"


def test_export_only_keeps_human_approved_candidates(tmp_path):
    source = tmp_path / "candidates.jsonl"
    output = tmp_path / "approved.jsonl"
    messages = [
        {"role": "system", "content": "KLOD"},
        {"role": "user", "content": "Explique o conceito."},
        {"role": "assistant", "content": "Uma explicação completa e revisada."},
    ]
    rows = [
        {"id": "approved-1", "domain": "science", "approved": True,
         "quality_passed": True, "messages": messages},
        {"id": "pending-1", "domain": "math", "approved": False,
         "quality_passed": True, "messages": messages},
    ]
    source.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    result = export_approved(source, output, minimum=1)
    exported = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert result["approved_examples"] == 1
    assert exported[0]["id"] == "approved-1"
    assert exported[0]["review_status"] == "approved"


def test_export_rejects_unreviewed_low_quality_and_short_sets(tmp_path):
    source = tmp_path / "candidates.jsonl"
    output = tmp_path / "approved.jsonl"
    row = {"approved": True, "quality_passed": False, "messages": []}
    source.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="quality checks"):
        list(approved_candidates(source))
    row["quality_passed"] = True
    row["approved"] = False
    source.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="at least 20"):
        export_approved(source, output, minimum=20)


def test_preflight_requires_approved_teacher_rows_when_configured(tmp_path):
    path = tmp_path / "teacher.jsonl"
    row = {"messages": [], "approved": False, "quality_passed": True}
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    result = inspect_dataset(path, {"messages"}, 1, require_approval=True)
    assert result["valid"] is False
    assert result["unapproved_rows"] == 1
