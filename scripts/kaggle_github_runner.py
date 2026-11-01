import argparse
import copy
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from .kaggle_remote_train import (
        RunnerError,
        build_training_notebook,
        check_environment,
        download_kernel_outputs,
        extract_candidate_file,
        load_candidates,
        make_kernel_workspace,
        make_report,
        notebook_cell,
        poll_kernel,
        push_kernel,
        repository_root,
    )
except ImportError:
    from kaggle_remote_train import (
        RunnerError,
        build_training_notebook,
        check_environment,
        download_kernel_outputs,
        extract_candidate_file,
        load_candidates,
        make_kernel_workspace,
        make_report,
        notebook_cell,
        poll_kernel,
        push_kernel,
        repository_root,
    )


def load_base_notebook(root):
    path = root / "notebooks/KLOD_Kaggle_Teacher_Distillation.ipynb"
    notebook = json.loads(path.read_text(encoding="utf-8"))
    if len(notebook.get("cells", [])) < 20:
        raise RunnerError("Unexpected KLOD Kaggle notebook structure.")
    return notebook


def build_teacher_notebook(base):
    cells = copy.deepcopy(base["cells"][:9])
    cells.append(
        notebook_cell(
            "markdown",
            "## Export candidates for human review\n\n"
            "This job generates candidates only. Student training is not run "
            "until a separate reviewed request is submitted.\n",
        )
    )
    cells.append(
        notebook_cell(
            "code",
            "from pathlib import Path\n"
            "import zipfile\n"
            "candidate_file = Path('/kaggle/working/KLOD-AI/data/generated/"
            "teacher_candidates.jsonl')\n"
            "assert candidate_file.is_file(), 'Teacher candidate file not found.'\n"
            "archive = Path('/kaggle/working/klod-teacher-candidates.zip')\n"
            "with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:\n"
            "    bundle.write(candidate_file, 'teacher_candidates.jsonl')\n"
            "print('Candidate archive:', archive)\n",
        )
    )
    notebook = copy.deepcopy(base)
    notebook["cells"] = cells
    return notebook


def validate_approvals(candidates, approved_ids):
    if not isinstance(approved_ids, list) or not all(
        isinstance(value, str) and value.strip() for value in approved_ids
    ):
        raise RunnerError("approved_ids must be a JSON array of non-empty strings.")
    if len(approved_ids) != len(set(approved_ids)):
        raise RunnerError("approved_ids contains duplicate identifiers.")
    by_id = {}
    for item in candidates:
        candidate_id = item.get("id")
        if not isinstance(candidate_id, str) or not candidate_id:
            raise RunnerError("A candidate has a missing or invalid id.")
        if candidate_id in by_id:
            raise RunnerError("Duplicate candidate id: " + candidate_id)
        by_id[candidate_id] = item
    unknown = sorted(set(approved_ids) - set(by_id))
    if unknown:
        raise RunnerError("Unknown candidate IDs: " + ", ".join(unknown))
    ineligible = sorted(
        value for value in approved_ids
        if by_id[value].get("quality_passed") is not True
    )
    if ineligible:
        raise RunnerError(
            "These candidates did not pass automated quality checks: "
            + ", ".join(ineligible)
        )
    if len(approved_ids) < 20:
        raise RunnerError(
            "At least 20 manually reviewed examples are required. Received "
            + str(len(approved_ids))
            + "."
        )
    return approved_ids


def generate(username, output_dir, workdir, poll_seconds, max_wait_seconds):
    root = repository_root()
    base = load_base_notebook(root)
    notebook = build_teacher_notebook(base)
    folder, kernel_ref = make_kernel_workspace(
        workdir,
        username,
        "klod-teacher-generation",
        "KLOD Teacher Generation",
        "klod_teacher_generation.ipynb",
        notebook,
    )
    print("Submitting teacher generation to Kaggle:", kernel_ref)
    push_kernel(folder)
    poll_kernel(kernel_ref, poll_seconds, max_wait_seconds)

    downloaded = workdir / "teacher-output"
    download_kernel_outputs(kernel_ref, downloaded)
    candidate_file = extract_candidate_file(
        downloaded, workdir / "teacher-extracted"
    )
    candidates = load_candidates(candidate_file)
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / "teacher_candidates.jsonl"
    shutil.copy2(candidate_file, target)

    metadata = {
        "kernel_ref": kernel_ref,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "candidate_count": len(candidates),
        "candidate_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "minimum_approved_for_training": 20,
    }
    (output_dir / "teacher_run.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


def train_stage(
    username, candidate_file, approved_ids_json, output_dir, workdir,
    stage_percent, previous_adapter_zip, poll_seconds, max_wait_seconds
):
    import zipfile

    if stage_percent not in (20, 40, 60, 80, 100):
        raise RunnerError("stage_percent must be 20, 40, 60, 80, 100.")
    if stage_percent == 20 and previous_adapter_zip is not None:
        raise RunnerError("The 20% stage must not receive a previous adapter.")
    if stage_percent > 20 and (
        previous_adapter_zip is None or not previous_adapter_zip.is_file()
    ):
        raise RunnerError("Stages above 20% require the previous stage adapter ZIP.")

    root = repository_root()
    base = load_base_notebook(root)
    candidates = load_candidates(candidate_file)
    try:
        raw_approved = json.loads(approved_ids_json)
    except json.JSONDecodeError as exc:
        raise RunnerError("approved_ids_json is not valid JSON.") from exc
    approved_ids = validate_approvals(candidates, raw_approved)

    previous_bytes = None
    if previous_adapter_zip is not None:
        try:
            with zipfile.ZipFile(previous_adapter_zip) as archive:
                bad_member = archive.testzip()
                names = archive.namelist()
                if bad_member:
                    raise RunnerError("Previous adapter ZIP is corrupt: " + bad_member)
                if not any(name.endswith("adapter_config.json") for name in names):
                    raise RunnerError("Previous adapter ZIP has no adapter_config.json.")
                if not any(
                    name.endswith("adapter_model.safetensors")
                    or name.endswith("adapter_model.bin")
                    for name in names
                ):
                    raise RunnerError("Previous adapter ZIP has no adapter weights.")
            previous_bytes = previous_adapter_zip.read_bytes()
        except zipfile.BadZipFile as exc:
            raise RunnerError("Previous adapter is not a valid ZIP.") from exc

    notebook_cells = build_training_notebook(
        base,
        candidate_file.read_bytes(),
        approved_ids,
        stage_percent=stage_percent,
        previous_adapter_bytes=previous_bytes,
    )
    notebook = copy.deepcopy(base)
    notebook["cells"] = notebook_cells
    slug = "klod-student-stage-" + str(stage_percent)
    folder, kernel_ref = make_kernel_workspace(
        workdir,
        username,
        slug,
        "KLOD Student Training " + str(stage_percent) + "%",
        slug + ".ipynb",
        notebook,
    )
    print("Submitting KLOD stage", str(stage_percent) + "% to Kaggle:", kernel_ref)
    push_kernel(folder)
    poll_kernel(kernel_ref, poll_seconds, max_wait_seconds)

    downloaded = workdir / ("student-stage-" + str(stage_percent) + "-output")
    download_kernel_outputs(kernel_ref, downloaded)
    adapter_candidates = list(
        downloaded.rglob("klod-teacher-distilled-adapter.zip")
    )
    result_candidates = list(
        downloaded.rglob("klod-teacher-distillation-results.zip")
    )
    if not adapter_candidates or not result_candidates:
        found = [
            str(path.relative_to(downloaded))
            for path in downloaded.rglob("*")
            if path.is_file()
        ]
        raise RunnerError(
            "Kaggle finished but required stage ZIPs were not found. "
            "Downloaded files: " + ", ".join(found[:60])
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    adapter_zip = output_dir / ("klod-stage-" + str(stage_percent) + "-adapter.zip")
    results_zip = output_dir / ("klod-stage-" + str(stage_percent) + "-results.zip")
    shutil.copy2(adapter_candidates[0], adapter_zip)
    shutil.copy2(result_candidates[0], results_zip)
    report = output_dir / ("RELATORIO_KLOD_" + str(stage_percent) + "pct.txt")
    make_report(
        report,
        username,
        username + "/klod-teacher-generation",
        kernel_ref,
        candidates,
        approved_ids,
        adapter_zip,
        results_zip,
    )
    metadata = {
        "stage_percent": stage_percent,
        "stage_index": stage_percent // 20,
        "stage_total": 5,
        "previous_adapter_used": stage_percent > 20,
        "kernel_ref": kernel_ref,
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "approved_count": len(approved_ids),
    }
    (output_dir / ("stage-" + str(stage_percent) + "-metadata.json")).write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("Stage outputs validated.")
    print("Adapter:", adapter_zip)
    print("Results:", results_zip)
    print("Report:", report)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("generate", "train_stage"))
    parser.add_argument("--username", required=True)
    parser.add_argument("--candidate-file", type=Path)
    parser.add_argument("--approved-ids-json", default="[]")
    parser.add_argument("--stage-percent", type=int)
    parser.add_argument("--previous-adapter-zip", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--poll-seconds", type=int, default=45)
    parser.add_argument("--max-wait-hours", type=float, default=5.5)
    args = parser.parse_args()

    if args.poll_seconds < 10:
        raise RunnerError("--poll-seconds must be at least 10.")
    if args.max_wait_hours <= 0 or args.max_wait_hours > 5.5:
        raise RunnerError(
            "GitHub-hosted runner wait must be greater than 0 and at most 5.5 hours."
        )
    if not args.username.strip():
        raise RunnerError("Kaggle username is required.")

    check_environment()
    output_dir = args.output_dir.resolve()
    workdir = args.workdir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    workdir.mkdir(parents=True, exist_ok=True)

    if args.phase == "generate":
        generate(
            args.username.strip().lower(),
            output_dir,
            workdir,
            args.poll_seconds,
            int(args.max_wait_hours * 3600),
        )
        return

    if args.candidate_file is None or not args.candidate_file.is_file():
        raise RunnerError("--candidate-file must point to teacher_candidates.jsonl.")
    if args.stage_percent is None:
        raise RunnerError("--stage-percent is required for train_stage.")
    previous_zip = (
        args.previous_adapter_zip.expanduser().resolve()
        if args.previous_adapter_zip is not None
        else None
    )
    train_stage(
        args.username.strip().lower(),
        args.candidate_file.resolve(),
        args.approved_ids_json,
        output_dir,
        workdir,
        args.stage_percent,
        previous_zip,
        args.poll_seconds,
        int(args.max_wait_hours * 3600),
    )

if __name__ == "__main__":
    try:
        main()
    except (RunnerError, OSError, ValueError, KeyboardInterrupt) as error:
        print("STOPPED:", str(error), file=sys.stderr)
        sys.exit(1)
