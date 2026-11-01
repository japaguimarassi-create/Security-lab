import json
from pathlib import Path

import pytest

from scripts.kaggle_remote_train import (
    MINIMUM_APPROVED,
    RunnerError,
    build_training_notebook,
    review_candidates,
)


def load_notebook():
    path = (
        Path(__file__).resolve().parents[1]
        / "notebooks"
        / "KLOD_Kaggle_Teacher_Distillation.ipynb"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def test_training_notebook_injects_reviewed_data_and_skips_teacher_generation():
    base = load_notebook()
    candidate_bytes = (
        '{"id":"pt-001","quality_passed":true,"messages":'
        '[{"role":"user","content":"Question"},{"role":"assistant","content":"Answer"}]}\n'
    ).encode("utf-8")

    cells = build_training_notebook(base, candidate_bytes, ["pt-001"])
    sources = ["".join(cell.get("source", [])) for cell in cells]
    code = sources[8]

    compile(code, "<kaggle-training-injection>", "exec")
    assert "pt-001" in code
    assert "base64.b64decode" in code
    assert "approve_teacher_data.py" in "\n".join(sources)
    assert "train_sft.py" in "\n".join(sources)
    assert "evaluate_teacher_student.py" in "\n".join(sources)
    assert not any("generate_teacher_data.py" in source for source in sources)


def test_review_never_approves_by_default(monkeypatch):
    candidate = {
        "id": "pt-001",
        "domain": "general",
        "language": "pt",
        "quality_passed": True,
        "messages": [
            {"role": "user", "content": "Question"},
            {"role": "assistant", "content": "Answer"},
        ],
    }
    monkeypatch.setattr("builtins.input", lambda _: "")
    with pytest.raises(RunnerError, match="At least 20 reviewed examples"):
        review_candidates([candidate])


def test_review_requires_explicit_approval_and_minimum(monkeypatch):
    candidates = [
        {
            "id": f"pt-{index:03d}",
            "domain": "general",
            "language": "pt",
            "quality_passed": True,
            "messages": [
                {"role": "user", "content": f"Question {index}"},
                {"role": "assistant", "content": f"Answer {index}"},
            ],
        }
        for index in range(1, MINIMUM_APPROVED + 1)
    ]
    monkeypatch.setattr("builtins.input", lambda _: "y")
    approved = review_candidates(candidates)
    assert len(approved) == MINIMUM_APPROVED
