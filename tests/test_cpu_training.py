import json
import tomllib
from pathlib import Path

import pytest
import yaml

from scripts.github_training import TrainingRequestError, validate_request


ROOT = Path(__file__).resolve().parents[1]


def test_cpu_smoke_request_is_limited_to_development():
    assert validate_request({"phase": "cpu_smoke"}, "development")["phase"] == "cpu_smoke"
    with pytest.raises(TrainingRequestError, match="development"):
        validate_request({"phase": "cpu_smoke"}, "training/20-percent")


def test_cpu_training_extra_does_not_install_cuda_quantization():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    extra = project["project"]["optional-dependencies"]["training-cpu"]
    assert not any("bitsandbytes" in value.lower() for value in extra)
    assert not any(value.startswith("torch") for value in extra)


@pytest.mark.parametrize("stage", (20, 40, 60, 80, 100))
def test_staged_configs_are_cpu_lora_and_memory_bounded(stage):
    path = ROOT / "configs" / "training" / "stages" / f"stage_{stage}.yaml"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert config["require_cuda"] is False
    assert config["load_in_4bit"] is False
    assert config["bf16"] is False
    assert config["max_sequence_length"] == 512
    assert config["lora"]["rank"] == 8
    assert config["lora"]["alpha"] == 16
    assert config["optim"] == "adamw_torch"


def test_teacher_and_evaluation_configs_are_cpu_bounded():
    teacher = yaml.safe_load((ROOT / "configs/training/distillation.yaml").read_text())
    evaluation = yaml.safe_load((ROOT / "configs/training/distillation_eval.yaml").read_text())
    assert teacher["require_cuda"] is False
    assert teacher["device_map"] == "cpu"
    assert teacher["max_new_tokens"] == 256
    assert evaluation["device_map"] == "cpu"
    assert evaluation["max_new_tokens"] == 256


def test_cpu_workflow_does_not_require_gpu_runner():
    workflow = (ROOT / ".github/workflows/klod-github-training.yml").read_text()
    assert "runs-on: ubuntu-latest" in workflow
    assert "ref: ${{ github.sha }}" in workflow
    assert "KLOD_FORCE_CPU: \"1\"" in workflow
    assert "torch==2.6.0+cpu" in workflow
    assert "nvidia-smi" not in workflow
