import json
import shutil
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
import yaml

from scripts.kaggle_remote_train import RunnerError, build_training_notebook


ROOT = Path(__file__).resolve().parents[1]
STAGES = (20, 40, 60, 80, 100)


def base_notebook():
    path = ROOT / "notebooks" / "KLOD_Kaggle_Teacher_Distillation.ipynb"
    return json.loads(path.read_text(encoding="utf-8"))


def candidates():
    rows = []
    for index in range(1, 22):
        rows.append(
            {
                "id": f"pt-{index:03d}",
                "quality_passed": True,
                "approved": False,
                "messages": [
                    {"role": "user", "content": f"Question {index}"},
                    {"role": "assistant", "content": f"Reviewed answer {index}"},
                ],
            }
        )
    return rows


def candidate_bytes():
    return "".join(
        json.dumps(row, ensure_ascii=False) + "\n" for row in candidates()
    ).encode("utf-8")


def adapter_zip_bytes():
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("adapter_config.json", '{"r":16}')
        archive.writestr("adapter_model.safetensors", b"weights")
    return buffer.getvalue()


@pytest.mark.parametrize("stage", STAGES)
def test_stage_configs_define_one_epoch_and_twenty_percent(stage):
    path = ROOT / "configs" / "training" / "stages" / f"stage_{stage}.yaml"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert config["stage_percent"] == stage
    assert config["stage_index"] == stage // 20
    assert config["stage_total"] == 5
    assert config["num_train_epochs"] == 1
    assert config["output_dir"] == f"outputs/klod-stage-{stage}"
    assert config["minimum_examples"] == 20


@pytest.mark.parametrize("stage", STAGES)
def test_stage_notebook_builds_expected_progress_and_config(stage, tmp_path, monkeypatch):
    previous = adapter_zip_bytes() if stage > 20 else None
    cells = build_training_notebook(
        base_notebook(),
        candidate_bytes(),
        [f"pt-{index:03d}" for index in range(1, 21)],
        stage_percent=stage,
        previous_adapter_bytes=previous,
    )
    injection = "".join(cells[8]["source"])
    compile(injection, "<stage-injection>", "exec")
    assert f"stage_{stage}.yaml" in injection
    assert f"klod-stage-{stage}" in injection
    assert "num_train_epochs" in injection
    assert ("previous-stage-adapter" in injection) is (stage > 20)

    config_source = (
        ROOT / "configs" / "training" / "stages" / f"stage_{stage}.yaml"
    )
    target = tmp_path / "configs" / "training" / "stages"
    target.mkdir(parents=True)
    shutil.copy2(config_source, target / config_source.name)
    training_config = ROOT / "configs" / "training" / "distillation_eval.yaml"
    shutil.copy2(training_config, target.parent / training_config.name)
    monkeypatch.chdir(tmp_path)
    exec(compile(injection, "<stage-injection>", "exec"), {})

    runtime = yaml.safe_load(
        Path("configs/training/stages/runtime_stage.yaml").read_text()
    )
    assert runtime["num_train_epochs"] == 1
    assert runtime["output_dir"] == f"outputs/klod-stage-{stage}"
    assert len(
        [
            json.loads(line)
            for line in Path("data/generated/teacher_candidates.jsonl")
            .read_text()
            .splitlines()
            if json.loads(line).get("approved")
        ]
    ) == 20
    if stage > 20:
        assert Path(runtime["previous_adapter"]).joinpath(
            "adapter_model.safetensors"
        ).is_file()
    else:
        assert runtime["previous_adapter"] is None


def test_stages_after_twenty_percent_require_previous_adapter():
    with pytest.raises(RunnerError, match="require the previous stage"):
        build_training_notebook(
            base_notebook(), candidate_bytes(),
            [f"pt-{index:03d}" for index in range(1, 21)],
            stage_percent=40,
        )


def test_first_stage_rejects_previous_adapter():
    with pytest.raises(RunnerError, match="must start from the base"):
        build_training_notebook(
            base_notebook(), candidate_bytes(),
            [f"pt-{index:03d}" for index in range(1, 21)],
            stage_percent=20,
            previous_adapter_bytes=adapter_zip_bytes(),
        )


def test_stage_notebook_uses_stage_specific_training_config_and_output():
    cells = build_training_notebook(
        base_notebook(), candidate_bytes(),
        [f"pt-{index:03d}" for index in range(1, 21)],
        stage_percent=60,
        previous_adapter_bytes=adapter_zip_bytes(),
    )
    code = "\n".join(
        "".join(cell.get("source", []))
        for cell in cells
        if cell.get("cell_type") == "code"
    )
    assert "configs/training/stages/runtime_stage.yaml" in code
    assert "outputs/klod-stage-60" in code
    assert "outputs/klod-teacher-distilled" not in code
