import json
from pathlib import Path

import pytest
import yaml

from scripts.kaggle_github_runner import (
    RunnerError,
    build_teacher_notebook,
    validate_approvals,
)
from scripts.kaggle_remote_train import build_training_notebook


ROOT = Path(__file__).resolve().parents[1]


def load_notebook():
    path = ROOT / "notebooks" / "KLOD_Kaggle_Teacher_Distillation.ipynb"
    return json.loads(path.read_text(encoding="utf-8"))


def make_candidates(count=20):
    return [
        {
            "id": f"pt-{index:03d}",
            "quality_passed": True,
            "messages": [
                {"role": "user", "content": f"Question {index}"},
                {"role": "assistant", "content": f"Answer {index}"},
            ],
        }
        for index in range(1, count + 1)
    ]


def test_teacher_notebook_only_generates_candidates():
    notebook = build_teacher_notebook(load_notebook())
    sources = ["".join(cell.get("source", [])) for cell in notebook["cells"]]
    joined = "\n".join(sources)
    assert "generate_teacher_data.py" in joined
    assert "klod-teacher-candidates.zip" in joined
    assert "train_sft.py" not in joined


def test_approval_validation_accepts_only_reviewed_quality_candidates():
    candidates = make_candidates()
    approved = [item["id"] for item in candidates]
    assert validate_approvals(candidates, approved) == approved


@pytest.mark.parametrize(
    "approved",
    [
        [],
        ["unknown-id"],
        ["pt-001", "pt-001"],
    ],
)
def test_approval_validation_rejects_invalid_ids(approved):
    with pytest.raises(RunnerError):
        validate_approvals(make_candidates(), approved)


def test_approval_validation_rejects_quality_failed_candidate():
    candidates = make_candidates()
    candidates[0]["quality_passed"] = False
    with pytest.raises(RunnerError, match="automated quality checks"):
        validate_approvals(candidates, [item["id"] for item in candidates])


def test_generated_training_cell_marks_exact_approved_ids(tmp_path, monkeypatch):
    candidates = make_candidates(2)
    candidate_bytes = "".join(
        json.dumps(item, ensure_ascii=False) + "\n" for item in candidates
    ).encode("utf-8")
    cells = build_training_notebook(load_notebook(), candidate_bytes, ["pt-002"])
    generated_code = "".join(cells[8]["source"])

    monkeypatch.chdir(tmp_path)
    exec(compile(generated_code, "<generated-approval-cell>", "exec"), {})

    saved = [
        json.loads(line)
        for line in Path("data/generated/teacher_candidates.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    approved = [item["id"] for item in saved if item.get("approved") is True]
    assert approved == ["pt-002"]


def test_workflow_uses_development_request_file_and_private_token_secret():
    workflow_path = ROOT / ".github" / "workflows" / "klod-kaggle-remote.yml"
    workflow = yaml.load(workflow_path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert "push" in workflow["on"]
    assert "development" in workflow["on"]["push"]["branches"]
    assert "data/kaggle/run-request.json" in workflow["on"]["push"]["paths"]
    assert workflow["jobs"]["remote"]["env"]["KAGGLE_API_TOKEN"] == "\${{ secrets.KAGGLE_API_TOKEN }}"
    request = json.loads((ROOT / "data" / "kaggle" / "run-request.json").read_text())
    assert request["phase"] == "setup"
