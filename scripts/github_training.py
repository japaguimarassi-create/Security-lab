import argparse
import hashlib
import json
import os
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

STAGES = (20, 40, 60, 80, 100)


class TrainingRequestError(ValueError):
    pass


def load_request(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TrainingRequestError(f"Cannot read training request: {exc}") from exc
    if not isinstance(data, dict):
        raise TrainingRequestError("Training request must be a JSON object.")
    return data


def _is_run_id(value):
    return not isinstance(value, bool) and isinstance(value, (str, int)) and str(value).isdigit() and int(value) > 0


def validate_request(request, branch):
    phase = request.get("phase")
    if phase not in ("setup", "generate", "train_stage"):
        raise TrainingRequestError("phase must be setup, generate or train_stage.")

    stage = request.get("stage_percent")
    match = re.fullmatch(r"training/(20|40|60|80|100)-percent", branch or "")
    branch_stage = int(match.group(1)) if match else None

    if phase == "generate":
        if branch != "development":
            raise TrainingRequestError("Teacher generation must run from development.")
        if stage is not None:
            raise TrainingRequestError("Teacher generation does not accept stage_percent.")

    if phase == "train_stage":
        if stage not in STAGES:
            raise TrainingRequestError("stage_percent must be 20, 40, 60, 80 or 100.")
        if branch_stage != stage:
            raise TrainingRequestError(f"Stage {stage}% must run from training/{stage}-percent.")
        if not _is_run_id(request.get("teacher_run_id")):
            raise TrainingRequestError("teacher_run_id must be a valid GitHub Actions run ID.")
        approved = request.get("approved_ids")
        if not isinstance(approved, list) or len(approved) < 20:
            raise TrainingRequestError("At least 20 manually reviewed candidate IDs are required.")
        if any(not isinstance(value, str) or not value.strip() for value in approved):
            raise TrainingRequestError("approved_ids must contain non-empty string IDs.")
        if len(approved) != len(set(approved)):
            raise TrainingRequestError("approved_ids cannot contain duplicates.")
        previous = request.get("previous_stage_run_id")
        if stage == 20 and previous not in (None, "", 0):
            raise TrainingRequestError("The 20% stage must start from the base model.")
        if stage > 20 and not _is_run_id(previous):
            raise TrainingRequestError(f"The {stage}% stage requires previous_stage_run_id.")

    if phase == "setup" and branch_stage is not None and stage not in (None, branch_stage):
        raise TrainingRequestError(f"{branch} can only be configured for stage {branch_stage}%.")

    previous_percent = stage - 20 if phase == "train_stage" and stage > 20 else None
    return {
        "phase": phase,
        "stage_percent": stage,
        "teacher_run_id": request.get("teacher_run_id"),
        "previous_stage_run_id": request.get("previous_stage_run_id"),
        "previous_stage_percent": previous_percent,
        "approved_ids": request.get("approved_ids", []),
    }


def validate_command(args):
    request = load_request(args.request)
    result = validate_request(request, args.branch)
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as output:
            for key in ("phase", "stage_percent", "teacher_run_id",
                        "previous_stage_run_id", "previous_stage_percent"):
                value = result[key]
                output.write(f"{key}={'' if value is None else value}\n")
            output.write("approved_ids=" + json.dumps(result["approved_ids"], separators=(",", ":")) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _read_candidates(path):
    rows = []
    seen = set()
    with Path(path).open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise TrainingRequestError(f"{path}:{line_number}: invalid JSON.") from exc
            if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"]:
                raise TrainingRequestError(f"{path}:{line_number}: candidate ID is missing.")
            if row["id"] in seen:
                raise TrainingRequestError(f"Duplicate candidate ID: {row['id']}")
            seen.add(row["id"])
            rows.append(row)
    return rows


def _extract_adapter(archive_path, target):
    target = Path(target)
    if target.exists():
        import shutil
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        if archive.testzip():
            raise TrainingRequestError("Previous adapter archive is corrupt.")
        root = target.resolve()
        for item in archive.infolist():
            destination = (target / item.filename).resolve()
            if not destination.is_relative_to(root):
                raise TrainingRequestError("Previous adapter archive contains an unsafe path.")
        archive.extractall(target)
    names = {path.name for path in target.rglob("*") if path.is_file()}
    if "adapter_config.json" not in names:
        raise TrainingRequestError("Previous adapter archive is missing adapter_config.json.")
    if not ({"adapter_model.safetensors", "adapter_model.bin"} & names):
        raise TrainingRequestError("Previous adapter archive is missing model weights.")
    return target


def prepare_stage(args):
    request = load_request(args.request)
    values = validate_request(request, args.branch)
    if values["phase"] != "train_stage":
        raise TrainingRequestError("prepare-stage requires phase=train_stage.")

    candidates = _read_candidates(args.candidate_file)
    candidate_map = {row["id"]: row for row in candidates}
    approved_ids = values["approved_ids"]
    unknown = sorted(set(approved_ids) - set(candidate_map))
    if unknown:
        raise TrainingRequestError("Unknown candidate IDs: " + ", ".join(unknown))
    rejected = sorted(
        candidate_id for candidate_id in approved_ids
        if candidate_map[candidate_id].get("quality_passed") is not True
    )
    if rejected:
        raise TrainingRequestError("Approved IDs failed automated quality checks: " + ", ".join(rejected))

    output = Path("data/generated/teacher_candidates.jsonl")
    output.parent.mkdir(parents=True, exist_ok=True)
    for row in candidates:
        row["approved"] = row["id"] in set(approved_ids)
        row["review_status"] = "approved" if row["approved"] else "pending"
        if row["approved"]:
            row["review_notes"] = "Explicitly approved in the GitHub stage request."
    output.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in candidates),
        encoding="utf-8",
    )

    stage = values["stage_percent"]
    previous_adapter = None
    if stage > 20:
        if not args.previous_adapter_zip:
            raise TrainingRequestError("Stages above 20% require the previous adapter archive.")
        previous_adapter = _extract_adapter(
            args.previous_adapter_zip, "outputs/previous-stage-adapter"
        )

    config_path = Path(f"configs/training/stages/stage_{stage}.yaml")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["previous_adapter"] = str(previous_adapter) if previous_adapter else None
    config["dataset_path"] = "data/processed/teacher_approved.jsonl"
    config["output_dir"] = f"outputs/klod-stage-{stage}"
    runtime_config = Path("configs/training/stages/runtime_stage.yaml")
    runtime_config.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    eval_config_path = Path("configs/training/distillation_eval.yaml")
    eval_config = yaml.safe_load(eval_config_path.read_text(encoding="utf-8"))
    eval_config["student_adapter"] = config["output_dir"]
    eval_config["blind_output_path"] = f"evaluation/distillation_blind_stage_{stage}.jsonl"
    eval_config["answer_key_path"] = f"evaluation/distillation_answer_key_stage_{stage}.json"
    runtime_eval = Path("configs/training/stages/runtime_eval.yaml")
    runtime_eval.write_text(yaml.safe_dump(eval_config, sort_keys=False), encoding="utf-8")

    print(json.dumps({
        "stage_percent": stage,
        "approved_examples": len(approved_ids),
        "candidate_count": len(candidates),
        "training_config": str(runtime_config),
        "evaluation_config": str(runtime_eval),
        "previous_adapter": str(previous_adapter) if previous_adapter else None,
    }, ensure_ascii=False, indent=2))


def record_generation(args):
    candidates = _read_candidates(args.candidate_file)
    path = Path(args.output) / "teacher_run.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        "github_sha": os.environ.get("GITHUB_SHA"),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "teacher_model": "Qwen/Qwen3-1.7B",
        "candidate_count": len(candidates),
        "candidate_sha256": hashlib.sha256(Path(args.candidate_file).read_bytes()).hexdigest(),
        "minimum_approved_examples": 20,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def package_stage(args):
    stage = args.stage
    adapter_dir = Path(args.adapter_dir)
    output_dir = Path(args.output_dir)
    evaluation = Path(f"evaluation/distillation_blind_stage_{stage}.jsonl")
    metrics = adapter_dir / "training_metrics.json"
    if not adapter_dir.is_dir() or not (adapter_dir / "adapter_config.json").is_file():
        raise TrainingRequestError("Trained adapter directory is incomplete.")
    if not any((adapter_dir / name).is_file() for name in ("adapter_model.safetensors", "adapter_model.bin")):
        raise TrainingRequestError("Trained adapter weights are missing.")
    if not metrics.is_file():
        raise TrainingRequestError("Training metrics are missing.")
    if not evaluation.is_file():
        raise TrainingRequestError("Blind evaluation output is missing.")

    output_dir.mkdir(parents=True, exist_ok=True)
    adapter_zip = output_dir / f"klod-stage-{stage}-adapter.zip"
    with zipfile.ZipFile(adapter_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in adapter_dir.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(adapter_dir).as_posix())

    metadata = {
        "stage_percent": stage,
        "stage_index": stage // 20,
        "stage_total": 5,
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        "github_sha": os.environ.get("GITHUB_SHA"),
        "previous_adapter_used": stage > 20,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "training_metrics": json.loads(metrics.read_text(encoding="utf-8")),
        "blind_evaluation_file": evaluation.name,
        "answer_key_published": False,
    }
    metadata_path = output_dir / f"stage-{stage}-metadata.json"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path = output_dir / f"RELATORIO_KLOD_{stage}pct.md"
    report_path.write_text(
        f"# KLOD training stage {stage}%\n\n"
        f"- Stage: {stage // 20}/5\n"
        f"- GitHub run: {metadata['github_run_id']}\n"
        f"- Approved examples: {metadata['training_metrics'].get('training_examples', 'not reported')}\n"
        f"- Adapter: {adapter_zip.name}\n"
        f"- Blind evaluation: {evaluation.name}\n"
        "- The teacher/student answer key is intentionally excluded from public artifacts.\n",
        encoding="utf-8",
    )
    results_zip = output_dir / f"klod-stage-{stage}-results.zip"
    with zipfile.ZipFile(results_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(metrics, "training_metrics.json")
        archive.write(evaluation, evaluation.name)
        archive.write(metadata_path, metadata_path.name)
        archive.write(report_path, report_path.name)
    print(json.dumps({
        "adapter_artifact": str(adapter_zip),
        "results_artifact": str(results_zip),
        "report": str(report_path),
    }, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate-request")
    validate.add_argument("--request", type=Path, default=Path("data/github/run-request.json"))
    validate.add_argument("--branch", default=os.environ.get("GITHUB_REF_NAME", "development"))
    validate.set_defaults(func=validate_command)

    prepare = commands.add_parser("prepare-stage")
    prepare.add_argument("--request", type=Path, default=Path("data/github/run-request.json"))
    prepare.add_argument("--branch", default=os.environ.get("GITHUB_REF_NAME", "development"))
    prepare.add_argument("--candidate-file", type=Path, required=True)
    prepare.add_argument("--previous-adapter-zip", type=Path)
    prepare.set_defaults(func=prepare_stage)

    record = commands.add_parser("record-generation")
    record.add_argument("--candidate-file", type=Path, default=Path("data/generated/teacher_candidates.jsonl"))
    record.add_argument("--output", type=Path, default=Path("data/generated"))
    record.set_defaults(func=record_generation)

    package = commands.add_parser("package-stage")
    package.add_argument("--stage", type=int, choices=STAGES, required=True)
    package.add_argument("--adapter-dir", type=Path, required=True)
    package.add_argument("--output-dir", type=Path, default=Path("output"))
    package.set_defaults(func=package_stage)

    args = parser.parse_args()
    try:
        args.func(args)
    except (OSError, ValueError, zipfile.BadZipFile, yaml.YAMLError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
