import json
import zipfile
from pathlib import Path

import pytest
import yaml

from scripts.github_training import (
    TrainingRequestError,
    package_stage,
    prepare_stage,
    validate_request,
)


def request_for(stage):
    request = {
        "phase": "train_stage",
        "stage_percent": stage,
        "teacher_run_id": 123456,
        "previous_stage_run_id": None if stage == 20 else 123455,
        "approved_ids": [f"pt-{index:03d}" for index in range(1, 21)],
    }
    return request


def candidate_file(path, count=21):
    rows = []
    for index in range(1, count + 1):
        rows.append({
            "id": f"pt-{index:03d}",
            "quality_passed": True,
            "approved": False,
            "messages": [
                {"role": "user", "content": f"Question {index}"},
                {"role": "assistant", "content": f"Verified answer {index}"},
            ],
        })
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    return path


def test_setup_request_is_valid_without_gpu():
    assert validate_request({"phase": "setup"}, "development")["phase"] == "setup"


@pytest.mark.parametrize("stage", (20, 40, 60, 80, 100))
def test_stage_must_match_its_branch(stage):
    values = validate_request(request_for(stage), f"training/{stage}-percent")
    assert values["stage_percent"] == stage
    assert values["previous_stage_percent"] == (stage - 20 if stage > 20 else None)


def test_stage_rejects_branch_mismatch():
    with pytest.raises(TrainingRequestError, match="must run from"):
        validate_request(request_for(40), "training/20-percent")


def test_stage_requires_twenty_unique_ids():
    request = request_for(20)
    request["approved_ids"] = ["pt-001"] * 20
    with pytest.raises(TrainingRequestError, match="duplicates"):
        validate_request(request, "training/20-percent")


def test_later_stage_requires_previous_run():
    request = request_for(60)
    request["previous_stage_run_id"] = None
    with pytest.raises(TrainingRequestError, match="previous_stage_run_id"):
        validate_request(request, "training/60-percent")


@pytest.mark.parametrize("stage", (20, 40, 60, 80, 100))
def test_prepare_stage_creates_runtime_configs_and_approval_file(stage, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = Path(__file__).resolve().parents[1]
    config_dir = Path("configs/training/stages")
    config_dir.mkdir(parents=True)
    for path in (root / "configs/training/stages").glob("stage_*.yaml"):
        (config_dir / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    eval_path = Path("configs/training/distillation_eval.yaml")
    eval_path.parent.mkdir(parents=True, exist_ok=True)
    eval_path.write_text(
        (root / "configs/training/distillation_eval.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    request_path = Path("data/github/run-request.json")
    request_path.parent.mkdir(parents=True)
    request_path.write_text(json.dumps(request_for(stage)), encoding="utf-8")
    candidates = candidate_file(tmp_path / "teacher_candidates.jsonl")

    previous_zip = None
    if stage > 20:
        previous_zip = tmp_path / "previous.zip"
        with zipfile.ZipFile(previous_zip, "w") as archive:
            archive.writestr("adapter_config.json", '{"r":16}')
            archive.writestr("adapter_model.safetensors", b"weights")

    class Args:
        request = request_path
        branch = f"training/{stage}-percent"
        candidate_file = candidates
        previous_adapter_zip = previous_zip

    prepare_stage(Args())

    approved = [
        json.loads(line)
        for line in Path("data/generated/teacher_candidates.jsonl").read_text().splitlines()
        if json.loads(line)["approved"]
    ]
    assert len(approved) == 20
    runtime = yaml.safe_load(Path("configs/training/stages/runtime_stage.yaml").read_text())
    evaluation = yaml.safe_load(Path("configs/training/stages/runtime_eval.yaml").read_text())
    assert runtime["stage_percent"] == stage
    assert runtime["output_dir"] == f"outputs/klod-stage-{stage}"
    assert runtime["previous_adapter"] == (None if stage == 20 else "outputs/previous-stage-adapter")
    assert evaluation["student_adapter"] == f"outputs/klod-stage-{stage}"
    assert evaluation["blind_output_path"].endswith(f"stage_{stage}.jsonl")


def test_package_stage_checks_adapter_and_creates_artifacts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    adapter = Path("outputs/klod-stage-20")
    adapter.mkdir(parents=True)
    (adapter / "adapter_config.json").write_text('{"r":16}')
    (adapter / "adapter_model.safetensors").write_bytes(b"weights")
    (adapter / "training_metrics.json").write_text(json.dumps({"training_examples": 20}))
    evaluation = Path("evaluation/distillation_blind_stage_20.jsonl")
    evaluation.parent.mkdir()
    evaluation.write_text('{"id":"eval-1","answer_a":"A","answer_b":"B"}\n')

    class Args:
        stage = 20
        adapter_dir = adapter
        output_dir = Path("output")

    package_stage(Args())

    with zipfile.ZipFile("output/klod-stage-20-adapter.zip") as archive:
        assert "adapter_config.json" in archive.namelist()
        assert "adapter_model.safetensors" in archive.namelist()
    with zipfile.ZipFile("output/klod-stage-20-results.zip") as archive:
        assert "distillation_blind_stage_20.jsonl" in archive.namelist()
        assert not any("answer_key" in name for name in archive.namelist())


def test_candidate_with_failed_quality_screen_cannot_be_approved(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = Path(__file__).resolve().parents[1]
    config_dir = Path("configs/training/stages")
    config_dir.mkdir(parents=True)
    for path in (root / "configs/training/stages").glob("stage_*.yaml"):
        (config_dir / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    eval_path = Path("configs/training/distillation_eval.yaml")
    eval_path.parent.mkdir(parents=True, exist_ok=True)
    eval_path.write_text((root / eval_path).read_text(encoding="utf-8"), encoding="utf-8")
    request_path = Path("data/github/run-request.json")
    request_path.parent.mkdir(parents=True)
    request_path.write_text(json.dumps(request_for(20)), encoding="utf-8")
    candidates = candidate_file(tmp_path / "teacher_candidates.jsonl")
    rows = [json.loads(line) for line in candidates.read_text().splitlines()]
    rows[0]["quality_passed"] = False
    candidates.write_text("".join(json.dumps(row) + "\n" for row in rows))

    class Args:
        request = request_path
        branch = "training/20-percent"
        candidate_file = candidates
        previous_adapter_zip = None

    with pytest.raises(TrainingRequestError, match="automated quality checks"):
        prepare_stage(Args())
