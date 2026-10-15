import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath


ALLOWED_LICENSES = {
    "Apache-2.0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "CC0-1.0",
    "ISC",
    "MIT",
    "Unlicense",
}
ALLOWED_SUFFIXES = {
    ".c", ".cc", ".cpp", ".cs", ".css", ".go", ".h", ".hpp", ".html",
    ".java", ".js", ".jsx", ".kt", ".md", ".php", ".py", ".rb", ".rs",
    ".sh", ".sql", ".swift", ".toml", ".ts", ".tsx", ".xml", ".yaml", ".yml",
}
BLOCKED_PARTS = {
    ".git", ".hg", ".svn", ".venv", "build", "coverage", "dist", "node_modules",
    "target", "vendor", "__pycache__",
}
BLOCKED_NAMES = {
    ".env", ".env.local", ".env.production", "authorized_keys", "credentials",
    "id_rsa", "id_ed25519",
}
SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{30,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{24,}\b"),
]


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def secret_pattern_found(text):
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def read_manifest(path):
    entries = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid JSONL manifest on line {line_number}: {error.msg}") from error
        if not isinstance(entry, dict):
            raise ValueError(f"Manifest line {line_number} must be a JSON object")
        entries.append((line_number, entry))
    return entries


def resolve_source(root, relative_path):
    if not isinstance(relative_path, str) or not relative_path.strip():
        return None, "invalid_path"
    rel = PurePosixPath(relative_path)
    if rel.is_absolute() or any(part in {"..", ""} for part in rel.parts):
        return None, "path_not_relative_or_contains_parent"
    if any(part in BLOCKED_PARTS for part in rel.parts):
        return None, "blocked_directory"
    if rel.name.lower() in BLOCKED_NAMES or rel.name.lower().startswith(".env."):
        return None, "sensitive_filename"
    if Path(rel.name).suffix.lower() not in ALLOWED_SUFFIXES:
        return None, "unsupported_extension"

    candidate = root.joinpath(*rel.parts)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError):
        return None, "missing_or_outside_root"
    current = root
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            return None, "symlink_source"
    if not resolved.is_file():
        return None, "not_a_regular_file"
    return resolved, None


def prepare_corpus(manifest_path, root_path, output_path, report_path, max_bytes):
    root = root_path.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("root must be a directory")
    seen_content = set()
    records = []
    report = []
    included_bytes = 0

    for line_number, entry in read_manifest(manifest_path):
        source_url = entry.get("source_url")
        commit = entry.get("commit")
        license_id = entry.get("license")
        training_permitted = entry.get("training_permitted")

        if training_permitted is not True:
            report.append({"line": line_number, "decision": "exclude", "reason": "training_permission_not_true"})
            continue
        if license_id not in ALLOWED_LICENSES:
            report.append({"line": line_number, "decision": "exclude", "reason": "license_not_allowlisted"})
            continue
        if not isinstance(source_url, str) or not source_url.startswith(("https://", "http://")):
            report.append({"line": line_number, "decision": "exclude", "reason": "source_url_missing"})
            continue
        if not isinstance(commit, str) or not commit.strip():
            report.append({"line": line_number, "decision": "exclude", "reason": "source_commit_missing"})
            continue

        resolved, error = resolve_source(root, entry.get("path"))
        if error:
            report.append({"line": line_number, "decision": "exclude", "reason": error})
            continue

        file_bytes = resolved.stat().st_size
        if file_bytes == 0 or file_bytes > max_bytes:
            report.append({"line": line_number, "decision": "exclude", "reason": "empty_or_oversized_file"})
            continue

        try:
            raw = resolved.read_bytes()
            text = raw.decode("utf-8")
        except (OSError, UnicodeDecodeError):
            report.append({"line": line_number, "decision": "exclude", "reason": "unreadable_or_non_utf8"})
            continue

        if "\x00" in text or secret_pattern_found(text):
            report.append({"line": line_number, "decision": "exclude", "reason": "binary_marker_or_possible_secret"})
            continue

        normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not normalized:
            report.append({"line": line_number, "decision": "exclude", "reason": "empty_after_normalization"})
            continue

        digest = sha256_bytes(normalized.encode("utf-8"))
        if digest in seen_content:
            report.append({"line": line_number, "decision": "exclude", "reason": "exact_duplicate"})
            continue
        seen_content.add(digest)
        records.append(normalized)
        included_bytes += len(normalized.encode("utf-8"))
        report.append({
            "line": line_number,
            "decision": "include",
            "path": entry["path"],
            "source_url": source_url,
            "commit": commit,
            "license": license_id,
            "sha256": digest,
            "bytes": len(normalized.encode("utf-8")),
        })

    if not records:
        raise ValueError("No sources passed validation; no output corpus was written")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n\n\n".join(records) + "\n", encoding="utf-8")
    summary = {
        "schema_version": 1,
        "root_name": root.name,
        "manifest": manifest_path.name,
        "included_files": len(records),
        "excluded_files": sum(1 for row in report if row["decision"] == "exclude"),
        "included_bytes": included_bytes,
        "license_allowlist": sorted(ALLOWED_LICENSES),
        "secret_scan": "heuristic; not a guarantee",
        "records": report,
    }
    report_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--max-bytes", type=int, default=1_000_000)
    args = parser.parse_args()

    if args.max_bytes < 1:
        raise SystemExit("max-bytes must be positive")

    try:
        summary = prepare_corpus(
            args.manifest.resolve(strict=True),
            args.root,
            args.output,
            args.report,
            args.max_bytes,
        )
    except (OSError, ValueError) as error:
        raise SystemExit(str(error)) from error
    print(json.dumps({
        "status": "corpus_prepared",
        "included_files": summary["included_files"],
        "excluded_files": summary["excluded_files"],
        "included_bytes": summary["included_bytes"],
        "report": str(args.report),
        "secret_scan": "heuristic; not a guarantee",
    }, sort_keys=True))


if __name__ == "__main__":
    main()