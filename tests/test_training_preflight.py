import json

from scripts.training_preflight import inspect_dataset, validate_record


def test_preflight_rejects_non_object_json_without_crashing(tmp_path):
    source = tmp_path / "dataset.jsonl"
    source.write_text("[]\n", encoding="utf-8")
    result = inspect_dataset(source, {"messages"}, 1, stage="sft")
    assert result["valid"] is False
    assert result["invalid_rows"] == 1
    assert result["invalid_examples"][0]["reason"] == "expected a JSON object"


def test_teacher_preflight_rejects_empty_prompt_fields():
    assert validate_record(
        {"prompt": " ", "domain": "science", "language": "pt"},
        stage="teacher",
    ) == "prompt must be non-empty text"


def test_sft_preflight_requires_assistant_final_message():
    record = {
        "messages": [
            {"role": "user", "content": "question"},
            {"role": "user", "content": "not an answer"},
        ],
        "approved": True,
        "quality_passed": True,
    }
    assert validate_record(record, stage="sft", require_approval=True) == (
        "the final message must have role assistant"
    )


def test_dpo_preflight_rejects_identical_responses():
    assert validate_record(
        {"prompt": "question", "chosen": "same", "rejected": "same"},
        stage="dpo",
    ) == "chosen and rejected responses must differ"


def test_preflight_counts_malformed_json_lines(tmp_path):
    source = tmp_path / "dataset.jsonl"
    source.write_text('{"text":"valid"}\nnot-json\n', encoding="utf-8")
    result = inspect_dataset(source, {"text"}, 1, stage="pretrain")
    assert result["valid_rows"] == 1
    assert result["invalid_rows"] == 1
    assert result["valid"] is False
