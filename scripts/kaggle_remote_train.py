import argparse
import base64
import copy
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path


NOTEBOOK_RELATIVE_PATH = Path("notebooks/KLOD_Kaggle_Teacher_Distillation.ipynb")
MINIMUM_APPROVED = 20
MAX_KERNEL_SECONDS = 12 * 60 * 60
TERMINAL_SUCCESS = ("COMPLETE", "SUCCEEDED", "SUCCESS")
TERMINAL_FAILURE = ("ERROR", "FAILED", "CANCELLED")


class RunnerError(RuntimeError):
    pass


def execute(command, check=True, quiet=False):
    result = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    output = result.stdout or ""
    if output.strip() and not quiet:
        print(output.rstrip())
    if check and result.returncode != 0:
        raise RunnerError(
            "Command failed with exit code "
            + str(result.returncode)
            + ": "
            + " ".join(command)
            + "\n"
            + output[-12000:]
        )
    return output, result.returncode


def check_environment():
    if sys.version_info < (3, 11):
        raise RunnerError("Python 3.11 or newer is required by the current Kaggle CLI.")
    if shutil.which("kaggle") is None:
        raise RunnerError(
            "Kaggle CLI not found. Install it with: "
            "python -m pip install --upgrade kaggle"
        )
    execute(["kaggle", "--version"], quiet=True)
    try:
        execute(
            ["kaggle", "kernels", "list", "--mine", "--page-size", "1"],
            quiet=True,
        )
    except RunnerError as exc:
        raise RunnerError(
            "Kaggle authentication failed. Sign in with the Kaggle CLI or "
            "configure the API token at ~/.kaggle/kaggle.json. "
            "Never paste the token into chat or commit it to GitHub.\n"
            + str(exc)
        ) from exc


def repository_root():
    root = Path(__file__).resolve().parents[1]
    notebook = root / NOTEBOOK_RELATIVE_PATH
    if not notebook.is_file():
        raise RunnerError("Run this script from a complete Security-lab checkout.")
    branch, code = execute(
        ["git", "-C", str(root), "branch", "--show-current"],
        quiet=True,
        check=False,
    )
    active_branch = branch.strip()
    allowed = active_branch == "development" or re.fullmatch(
        r"training/(20|40|60|80|100)-percent", active_branch
    )
    if code == 0 and not allowed:
        raise RunnerError(
            "This automation is restricted to development and staged training branches."
        )
    return root

def notebook_cell(cell_type, source):
    cell = {
        "cell_type": cell_type,
        "metadata": {},
        "source": source.splitlines(keepends=True),
    }
    if cell_type == "code":
        cell["execution_count"] = None
        cell["outputs"] = []
    return cell


def save_notebook(base, cells, destination):
    notebook = copy.deepcopy(base)
    notebook["cells"] = cells
    notebook.setdefault("metadata", {}).setdefault("kaggle", {})["accelerator"] = "GPU"
    destination.write_text(
        json.dumps(notebook, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )


def make_kernel_workspace(workdir, username, slug, title, notebook_name, notebook):
    folder = workdir / slug
    folder.mkdir(parents=True, exist_ok=True)
    save_notebook(notebook, notebook["cells"], folder / notebook_name)
    metadata = {
        "id": username + "/" + slug,
        "title": title,
        "code_file": notebook_name,
        "language": "python",
        "kernel_type": "notebook",
        "is_private": "true",
        "enable_gpu": "true",
        "enable_internet": "true",
        "machine_shape": "NvidiaTeslaT4",
        "dataset_sources": [],
        "competition_sources": [],
        "kernel_sources": [],
        "model_sources": [],
    }
    (folder / "kernel-metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return folder, username + "/" + slug


def push_kernel(folder):
    execute(
        [
            "kaggle",
            "kernels",
            "push",
            "--path",
            str(folder),
            "--timeout",
            str(MAX_KERNEL_SECONDS),
            "--accelerator",
            "NvidiaTeslaT4",
        ]
    )


def poll_kernel(kernel_ref, poll_seconds, max_wait_seconds):
    deadline = time.monotonic() + max_wait_seconds
    last_status = ""
    while time.monotonic() < deadline:
        status, code = execute(
            ["kaggle", "kernels", "status", kernel_ref],
            check=False,
            quiet=True,
        )
        if code != 0:
            raise RunnerError(
                "Could not read Kaggle run status for "
                + kernel_ref
                + ":\n"
                + status[-6000:]
            )
        normalized = status.upper()
        if status.strip() != last_status:
            print("Kaggle status:", status.strip())
            last_status = status.strip()
        if any(token in normalized for token in TERMINAL_SUCCESS):
            return status
        if any(token in normalized for token in TERMINAL_FAILURE):
            logs, _ = execute(
                ["kaggle", "kernels", "logs", kernel_ref],
                check=False,
                quiet=True,
            )
            raise RunnerError(
                "Kaggle reported a failed run for "
                + kernel_ref
                + ".\nStatus:\n"
                + status
                + "\nLogs, when available:\n"
                + logs[-12000:]
            )
        time.sleep(poll_seconds)
    raise RunnerError(
        "Timed out while waiting for "
        + kernel_ref
        + ". Check the private notebook in Kaggle before retrying."
    )


def download_kernel_outputs(kernel_ref, destination):
    destination.mkdir(parents=True, exist_ok=True)
    execute(
        [
            "kaggle",
            "kernels",
            "output",
            kernel_ref,
            "--path",
            str(destination),
            "--force",
            "--file-pattern",
            r".*\.zip$",
        ]
    )


def extract_candidate_file(output_dir, extraction_dir):
    archives = list(output_dir.rglob("*.zip"))
    for archive in archives:
        try:
            with zipfile.ZipFile(archive) as bundle:
                members = [
                    member
                    for member in bundle.namelist()
                    if member.endswith("teacher_candidates.jsonl")
                ]
                if members:
                    extraction_dir.mkdir(parents=True, exist_ok=True)
                    candidate = extraction_dir / "teacher_candidates.jsonl"
                    candidate.write_bytes(bundle.read(members[0]))
                    return candidate
        except zipfile.BadZipFile:
            continue
    raise RunnerError(
        "The teacher run completed, but its teacher_candidates.jsonl archive "
        "was not found among the Kaggle ZIP outputs."
    )


def load_candidates(candidate_file):
    candidates = []
    with candidate_file.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RunnerError(
                    "Invalid candidate JSON on line " + str(line_number)
                ) from exc
            if not isinstance(item, dict):
                raise RunnerError(
                    "Candidate line " + str(line_number) + " is not a JSON object."
                )
            candidates.append(item)
    if not candidates:
        raise RunnerError("The teacher generated an empty candidate file.")
    return candidates


def message_content(item, index):
    messages = item.get("messages")
    if not isinstance(messages, list) or len(messages) < 2:
        return "(message unavailable)"
    message = messages[index]
    if not isinstance(message, dict):
        return "(message unavailable)"
    return str(message.get("content", "(message unavailable)"))


def review_candidates(candidates):
    eligible = sum(item.get("quality_passed") is True for item in candidates)
    approved_ids = []
    print("\nHuman review required.")
    print("Candidates:", len(candidates), "| eligible after automatic checks:", eligible)
    print("Automatic checks do not establish factual accuracy.")
    print("Approve only answers you have personally checked. Default is NO.\n")
    for index, item in enumerate(candidates, 1):
        candidate_id = str(item.get("id", ""))
        quality_passed = item.get("quality_passed") is True
        print("\n" + "=" * 76)
        print(
            str(index)
            + "/"
            + str(len(candidates))
            + " | "
            + candidate_id
            + " | "
            + str(item.get("domain", "unknown"))
            + " | "
            + str(item.get("language", "unknown"))
            + " | quality_passed="
            + str(quality_passed)
        )
        print("\nQUESTION\n" + message_content(item, -2))
        print("\nTEACHER ANSWER\n" + message_content(item, -1))
        if not quality_passed or not candidate_id:
            print("\nNot eligible for approval.")
            continue
        while True:
            answer = input("\nApprove this answer? [y/N/q]: ").strip().lower()
            if answer in ("y", "yes", "s", "sim"):
                approved_ids.append(candidate_id)
                break
            if answer in ("", "n", "no", "nao", "não"):
                break
            if answer in ("q", "quit", "exit", "sair"):
                raise RunnerError("Review interrupted. No training was started.")
            print("Enter y, n, or q.")
    if len(approved_ids) < MINIMUM_APPROVED:
        raise RunnerError(
            "Only "
            + str(len(approved_ids))
            + " examples were approved. At least "
            + str(MINIMUM_APPROVED)
            + " reviewed examples are required; training was not started."
        )
    print("\nApproved examples:", len(approved_ids))
    return approved_ids


def build_training_notebook(
    base, candidate_bytes, approved_ids, stage_percent=20, previous_adapter_bytes=None
):
    allowed_stages = (20, 40, 60, 80, 100)
    if stage_percent not in allowed_stages:
        raise RunnerError("stage_percent must be one of 20, 40, 60, 80, 100.")
    if stage_percent == 20 and previous_adapter_bytes is not None:
        raise RunnerError("The 20% stage must start from the base model.")
    if stage_percent > 20 and not previous_adapter_bytes:
        raise RunnerError("Stages above 20% require the previous stage adapter ZIP.")

    stage_output = f"outputs/klod-stage-{stage_percent}"
    runtime_config = "configs/training/stages/runtime_stage.yaml"
    cells = copy.deepcopy(base["cells"][:7])
    cells.append(
        notebook_cell(
            "markdown",
            f"## Training stage: {stage_percent}%\\n\\n"
            "This stage runs one of five SFT epochs. It continues from the "
            "previous stage adapter when applicable.\\n",
        )
    )

    encoded_candidates = base64.b64encode(candidate_bytes).decode("ascii")
    approved_json = json.dumps(approved_ids, ensure_ascii=False)
    encoded_previous = (
        base64.b64encode(previous_adapter_bytes).decode("ascii")
        if previous_adapter_bytes
        else None
    )
    injection = (
        "import base64\\n"
        "import json\\n"
        "import zipfile\\n"
        "from pathlib import Path\\n"
        "import yaml\\n"
        "candidate_file = Path('data/generated/teacher_candidates.jsonl')\\n"
        "candidate_file.parent.mkdir(parents=True, exist_ok=True)\\n"
        "candidate_file.write_bytes(base64.b64decode("
        + repr(encoded_candidates)
        + "))\\n"
        "candidates = [json.loads(line) for line in candidate_file.read_text(encoding='utf-8').splitlines() if line.strip()]\\n"
        "approved_ids = set(json.loads("
        + repr(approved_json)
        + "))\\n"
        "approved_count = 0\\n"
        "for item in candidates:\\n"
        "    item['approved'] = item.get('id') in approved_ids and item.get('quality_passed') is True\\n"
        "    item['review_status'] = 'approved' if item['approved'] else 'pending_or_rejected'\\n"
        "    if item['approved']:\\n"
        "        item['review_notes'] = 'Human-reviewed before staged SFT'\\n"
        "        approved_count += 1\\n"
        "candidate_file.write_text(''.join(json.dumps(item, ensure_ascii=False) + '\\\\n' for item in candidates), encoding='utf-8')\\n"
        "print('Approved examples:', approved_count)\\n"
        "assert approved_count >= "
        + str(MINIMUM_APPROVED)
        + ", 'Insufficient reviewed examples.'\\n"
        "stage_config = Path("
        + repr(f"configs/training/stages/stage_{stage_percent}.yaml")
        + ")\\n"
        "config = yaml.safe_load(stage_config.read_text(encoding='utf-8'))\\n"
    )
    if encoded_previous:
        injection += (
            "previous_zip = Path('/kaggle/working/previous-stage-adapter.zip')\\n"
            "previous_zip.write_bytes(base64.b64decode("
            + repr(encoded_previous)
            + "))\\n"
            "previous_dir = Path('outputs/previous-stage-adapter').resolve()\\n"
            "previous_dir.mkdir(parents=True, exist_ok=True)\\n"
            "with zipfile.ZipFile(previous_zip) as archive:\\n"
            "    for member in archive.infolist():\\n"
            "        target = (previous_dir / member.filename).resolve()\\n"
            "        if previous_dir != target and previous_dir not in target.parents:\\n"
            "            raise ValueError('Unsafe path in previous adapter archive')\\n"
            "        archive.extract(member, previous_dir)\\n"
            "config['previous_adapter'] = str(previous_dir)\\n"
        )
    else:
        injection += "config['previous_adapter'] = None\\n"
    injection += (
        "config['output_dir'] = "
        + repr(stage_output)
        + "\\n"
        "config['num_train_epochs'] = 1\\n"
        "config['max_steps'] = -1\\n"
        "config['seed'] = 42 + "
        + str(stage_percent // 20 - 1)
        + "\\n"
        "runtime_config = Path("
        + repr(runtime_config)
        + ")\\n"
        "runtime_config.parent.mkdir(parents=True, exist_ok=True)\\n"
        "runtime_config.write_text(yaml.safe_dump(config, sort_keys=False), encoding='utf-8')\\n"
        "print('Stage:', "
        + str(stage_percent)
        + ", 'output:', config['output_dir'], 'previous adapter:', config['previous_adapter'])\\n"
    )
    cells.append(notebook_cell("code", injection))
    cells.extend(copy.deepcopy(base["cells"][11:]))
    for cell in cells[9:]:
        if cell.get("cell_type") != "code":
            continue
        source = "".join(cell.get("source", []))
        source = source.replace(
            "configs/training/distillation_sft.yaml", runtime_config
        )
        source = source.replace("outputs/klod-teacher-distilled", stage_output)
        cell["source"] = source.splitlines(keepends=True)
    return cells

def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_zip(path):
    if not path.is_file() or path.stat().st_size == 0:
        raise RunnerError("Expected output file is missing or empty: " + str(path))
    try:
        with zipfile.ZipFile(path) as archive:
            bad_member = archive.testzip()
            if bad_member:
                raise RunnerError(
                    "Corrupt ZIP member in " + str(path) + ": " + bad_member
                )
            return archive.namelist()
    except zipfile.BadZipFile as exc:
        raise RunnerError("Invalid ZIP file: " + str(path)) from exc


def make_report(destination, username, teacher_ref, student_ref, candidates,
                approved_ids, adapter_zip, results_zip):
    result_members = validate_zip(results_zip)
    adapter_members = validate_zip(adapter_zip)
    if not any(name.endswith("adapter_config.json") for name in adapter_members):
        raise RunnerError("Adapter archive is missing adapter_config.json.")
    if not any(
        name.endswith("adapter_model.safetensors")
        or name.endswith("adapter_model.bin")
        for name in adapter_members
    ):
        raise RunnerError("Adapter archive is missing adapter model weights.")

    metrics_text = "Not found in results archive."
    approved_count = len(approved_ids)
    with zipfile.ZipFile(results_zip) as archive:
        metrics_name = next(
            (
                name
                for name in archive.namelist()
                if name.endswith("training_metrics.json")
            ),
            None,
        )
        approved_name = next(
            (
                name
                for name in archive.namelist()
                if name.endswith("teacher_approved.jsonl")
            ),
            None,
        )
        if metrics_name:
            try:
                metrics = json.loads(archive.read(metrics_name).decode("utf-8"))
                metrics_text = json.dumps(
                    metrics, ensure_ascii=False, indent=2
                )[:10000]
            except (UnicodeDecodeError, json.JSONDecodeError):
                metrics_text = archive.read(metrics_name).decode(
                    "utf-8", errors="replace"
                )[:10000]
        if approved_name:
            approved_count = sum(
                1
                for line in archive.read(approved_name).decode("utf-8").splitlines()
                if line.strip()
            )

    generated_at = datetime.now(timezone.utc).isoformat()
    report = (
        "KLOD REMOTE TRAINING REPORT\n"
        "Generated at (UTC): " + generated_at + "\n"
        "Kaggle account: " + username + "\n"
        "Teacher run: https://www.kaggle.com/code/" + teacher_ref + "\n"
        "Student training run: https://www.kaggle.com/code/" + student_ref + "\n"
        "Candidates generated: " + str(len(candidates)) + "\n"
        "Examples approved by human review: " + str(approved_count) + "\n"
        "Minimum approval gate: " + str(MINIMUM_APPROVED) + "\n\n"
        "DELIVERABLES\n"
        "Adapter ZIP: " + adapter_zip.name + "\n"
        "Adapter bytes: " + str(adapter_zip.stat().st_size) + "\n"
        "Adapter SHA-256: " + sha256_file(adapter_zip) + "\n"
        "Results ZIP: " + results_zip.name + "\n"
        "Results bytes: " + str(results_zip.stat().st_size) + "\n"
        "Results SHA-256: " + sha256_file(results_zip) + "\n\n"
        "ADAPTER ARCHIVE CONTENTS\n"
        + "\n".join(adapter_members[:80])
        + "\n\nRESULTS ARCHIVE CONTENTS\n"
        + "\n".join(result_members[:120])
        + "\n\nTRAINING METRICS\n"
        + metrics_text
        + "\n\nLIMITATIONS\n"
        "A successful run only confirms that this configured training job completed. "
        "It does not prove broad intelligence or superiority over the teacher. "
        "Review the blind evaluation separately before drawing quality conclusions. "
        "The blind answer key is intentionally not downloaded by this automation.\n"
    )
    destination.write_text(report, encoding="utf-8")


def choose_output_directory():
    downloads = Path.home() / "storage" / "downloads"
    base = downloads if downloads.is_dir() else Path.home()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = base / ("KLOD-Kaggle-" + timestamp)
    output.mkdir(parents=True, exist_ok=False)
    return output


def main():
    parser = argparse.ArgumentParser(
        description="Run the KLOD teacher/SFT pipeline on Kaggle from Termux."
    )
    parser.add_argument("--username", help="Your authorized Kaggle username.")
    parser.add_argument(
        "--workdir",
        type=Path,
        help="Temporary working directory. Defaults to a folder under ~/.cache.",
    )
    parser.add_argument("--poll-seconds", type=int, default=45)
    parser.add_argument("--max-wait-hours", type=float, default=12)
    args = parser.parse_args()

    if args.poll_seconds < 10:
        raise RunnerError("--poll-seconds must be at least 10.")
    if args.max_wait_hours <= 0 or args.max_wait_hours > 12:
        raise RunnerError("--max-wait-hours must be greater than 0 and at most 12.")

    root = repository_root()
    username = (args.username or input("Kaggle username: ")).strip().lower()
    if not re.fullmatch(r"[A-Za-z0-9_-]{2,64}", username):
        raise RunnerError("Invalid Kaggle username format.")

    check_environment()
    base = json.loads(
        (root / NOTEBOOK_RELATIVE_PATH).read_text(encoding="utf-8")
    )
    if len(base.get("cells", [])) < 19:
        raise RunnerError("The source Kaggle notebook does not match the expected layout.")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    default_work = Path.home() / ".cache" / ("klod-kaggle-" + timestamp)
    workdir = args.workdir.expanduser().resolve() if args.workdir else default_work
    workdir.mkdir(parents=True, exist_ok=True)
    output_dir = choose_output_directory()
    max_wait = int(args.max_wait_hours * 60 * 60)

    teacher_cells = copy.deepcopy(base["cells"][:9])
    teacher_cells.append(
        notebook_cell(
            "markdown",
            "## 5. Export teacher candidates\n\n"
            "The candidate file is packaged for local human review. No student "
            "training occurs in this first run.\n",
        )
    )
    teacher_cells.append(
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
    teacher_nb = copy.deepcopy(base)
    teacher_nb["cells"] = teacher_cells
    teacher_folder, teacher_ref = make_kernel_workspace(
        workdir,
        username,
        "klod-teacher-generation",
        "KLOD Teacher Generation",
        "klod_teacher_generation.ipynb",
        teacher_nb,
    )

    print("\nPHASE 1/2: generate teacher candidates on Kaggle.")
    push_kernel(teacher_folder)
    poll_kernel(teacher_ref, args.poll_seconds, max_wait)
    teacher_output = workdir / "teacher-output"
    download_kernel_outputs(teacher_ref, teacher_output)
    candidate_file = extract_candidate_file(
        teacher_output, workdir / "teacher-extracted"
    )
    candidate_bytes = candidate_file.read_bytes()
    candidates = load_candidates(candidate_file)
    approved_ids = review_candidates(candidates)

    print("\nPHASE 2/2: train and evaluate the student on Kaggle.")
    training_cells = build_training_notebook(base, candidate_bytes, approved_ids)
    training_nb = copy.deepcopy(base)
    training_nb["cells"] = training_cells
    student_folder, student_ref = make_kernel_workspace(
        workdir,
        username,
        "klod-student-training",
        "KLOD Student Training",
        "klod_student_training.ipynb",
        training_nb,
    )
    push_kernel(student_folder)
    poll_kernel(student_ref, args.poll_seconds, max_wait)

    student_output = workdir / "student-output"
    download_kernel_outputs(student_ref, student_output)
    adapter_candidates = list(student_output.rglob("klod-teacher-distilled-adapter.zip"))
    results_candidates = list(student_output.rglob("klod-teacher-distillation-results.zip"))
    if not adapter_candidates or not results_candidates:
        found = [str(path) for path in student_output.rglob("*") if path.is_file()]
        raise RunnerError(
            "Kaggle run finished, but one or both expected ZIP files were not downloaded. "
            "Files found:\n" + "\n".join(found[:80])
        )

    adapter_zip = output_dir / "klod-teacher-distilled-adapter.zip"
    results_zip = output_dir / "klod-teacher-distillation-results.zip"
    shutil.copy2(adapter_candidates[0], adapter_zip)
    shutil.copy2(results_candidates[0], results_zip)
    report_path = output_dir / "RELATORIO_KLOD.txt"
    make_report(
        report_path,
        username,
        teacher_ref,
        student_ref,
        candidates,
        approved_ids,
        adapter_zip,
        results_zip,
    )

    print("\nRUN COMPLETED.")
    print("Output directory:", output_dir)
    print("Adapter:", adapter_zip)
    print("Results:", results_zip)
    print("Report:", report_path)
    print("The blind evaluation answer key was not downloaded.")


if __name__ == "__main__":
    try:
        main()
    except (RunnerError, OSError, ValueError, KeyboardInterrupt) as error:
        print("\nSTOPPED:", str(error), file=sys.stderr)
        sys.exit(1)
