import json
import zipfile
from pathlib import Path

from scripts.kaggle_github_runner import upload_previous_adapter_dataset
from scripts.kaggle_remote_train import make_kernel_workspace, notebook_cell


def make_adapter(path):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("adapter_config.json", '{"r":16}')
        archive.writestr("adapter_model.safetensors", b"adapter-weights")
    return path


def test_previous_adapter_is_uploaded_as_private_kaggle_dataset(tmp_path, monkeypatch):
    adapter = make_adapter(tmp_path / "previous.zip")
    calls = []

    def fake_execute(command, check=True, quiet=False):
        calls.append(command)
        return "ok", 0

    monkeypatch.setattr("scripts.kaggle_github_runner.execute", fake_execute)
    result = upload_previous_adapter_dataset(
        "test-user", 40, adapter, tmp_path / "work"
    )

    assert result.startswith("test-user/klod-stage-20-adapter-")
    dataset_dir = tmp_path / "work" / ("dataset-" + result.split("/", 1)[1])
    metadata = json.loads(
        (dataset_dir / "dataset-metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["id"] == result
    assert (dataset_dir / "klod-stage-20-adapter.zip").is_file()
    create_call = next(command for command in calls if command[2] == "create")
    assert "--public" not in create_call
    assert "-u" not in create_call
    assert any(command[2] == "status" for command in calls)


def test_kernel_metadata_mounts_previous_adapter_dataset(tmp_path):
    dataset_ref = "test-user/klod-stage-20-adapter-run-123"
    notebook = {
        "cells": [notebook_cell("markdown", "Stage test")],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    folder, kernel_ref = make_kernel_workspace(
        tmp_path,
        "test-user",
        "klod-stage-40-test",
        "KLOD stage 40",
        "stage.ipynb",
        notebook,
        dataset_sources=[dataset_ref],
    )
    metadata = json.loads(
        (folder / "kernel-metadata.json").read_text(encoding="utf-8")
    )
    assert kernel_ref == "test-user/klod-stage-40-test"
    assert metadata["is_private"] == "true"
    assert metadata["dataset_sources"] == [dataset_ref]


def test_generated_stage_notebook_references_dataset_without_embedding_weights():
    import json as json_module

    from scripts.kaggle_remote_train import build_training_notebook

    repo = Path(__file__).resolve().parents[1]
    base = json_module.loads(
        (repo / "notebooks" / "KLOD_Kaggle_Teacher_Distillation.ipynb").read_text()
    )
    rows = [
        {
            "id": f"pt-{index:03d}",
            "quality_passed": True,
            "messages": [
                {"role": "user", "content": f"Question {index}"},
                {"role": "assistant", "content": f"Reviewed answer {index}"},
            ],
        }
        for index in range(1, 22)
    ]
    candidates = "".join(
        json_module.dumps(row) + "\n" for row in rows
    ).encode("utf-8")
    dataset_ref = "test-user/klod-stage-20-adapter-run-123"
    cells = build_training_notebook(
        base,
        candidates,
        [row["id"] for row in rows[:20]],
        stage_percent=40,
        previous_adapter_dataset=dataset_ref,
    )
    sources = "\n".join(
        "".join(cell.get("source", [])) for cell in cells
    )
    assert dataset_ref in sources
    assert "/kaggle/input/klod-stage-20-adapter-run-123/" in sources
    assert "previous-stage-adapter.zip" not in sources
