import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_kaggle_notebook_is_valid_and_uses_one_visible_t4():
    path = ROOT / "notebooks/KLOD_Kaggle_Teacher_Distillation.ipynb"
    notebook = json.loads(path.read_text(encoding="utf-8"))
    assert notebook["nbformat"] == 4
    assert len(notebook["cells"]) >= 15
    code = "\n".join(
        "".join(cell.get("source", []))
        for cell in notebook["cells"]
        if cell.get("cell_type") == "code"
    )
    assert 'os.environ["CUDA_VISIBLE_DEVICES"] = "0"' in code
    assert "pull --ff-only origin development" in code
    assert "rm -rf KLOD-AI" not in code
    assert "training_preflight.py --stage teacher" in code
    assert "generate_teacher_data.py" in code
    assert "approve_teacher_data.py --minimum 20" in code
    assert "train_sft.py --config configs/training/distillation_sft.yaml" in code
    assert "evaluate_teacher_student.py" in code
    assert "distillation_answer_key.json" in code
    assert "The answer key is intentionally excluded." in code


def test_distillation_configs_have_consistent_teacher_student_roles():
    teacher = yaml.safe_load(
        (ROOT / "configs/training/distillation.yaml").read_text(encoding="utf-8")
    )
    student = yaml.safe_load(
        (ROOT / "configs/training/distillation_sft.yaml").read_text(encoding="utf-8")
    )
    evaluation = yaml.safe_load(
        (ROOT / "configs/training/distillation_eval.yaml").read_text(encoding="utf-8")
    )
    assert teacher["teacher_model"] == "Qwen/Qwen3-1.7B"
    assert teacher["student_base_model"] == student["base_model"]
    assert evaluation["teacher_model"] == teacher["teacher_model"]
    assert evaluation["student_base_model"] == student["base_model"]
    assert student["require_approval"] is True
    assert student["minimum_examples"] >= 20
    assert student["load_in_4bit"] is True
    assert teacher["teacher_model"] != student["base_model"]


def test_heldout_prompts_are_not_in_teacher_seed_prompts():
    seed_path = ROOT / "configs/distillation_prompts.jsonl"
    heldout_path = ROOT / "data/eval/distillation_heldout.jsonl"
    seed_prompts = {
        json.loads(line)["prompt"].strip().casefold()
        for line in seed_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    heldout_prompts = [
        json.loads(line)["prompt"].strip().casefold()
        for line in heldout_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(heldout_prompts) >= 5
    assert not (seed_prompts & set(heldout_prompts))



def test_generated_training_data_and_blind_key_are_ignored():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "data/generated/*" in ignored
    assert "evaluation/distillation_blind.jsonl" in ignored
    assert "evaluation/distillation_answer_key.json" in ignored
