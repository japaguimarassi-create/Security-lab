from __future__ import annotations

import argparse
import io
import os
import tarfile
from pathlib import Path, PurePosixPath

from .crypto import decrypt_bytes, encrypt_bytes

EXCLUDED_DIRS = {
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".ruff_cache",
    ".mypy_cache", "node_modules", "dist", "build", ".tox", ".idea",
    ".ssh", ".aws", ".azure", ".gpu-mesh", "secrets",
    "data", "models", "outputs", "checkpoints", "target",
}
EXCLUDED_SUFFIXES = {
    ".sqlite", ".sqlite3", ".db", ".pem", ".key", ".p12", ".pfx",
    ".safetensors", ".gguf", ".pt", ".pth", ".bin", ".grmesh",
}
MAX_ARCHIVE_BYTES = 4 * 1024 * 1024 * 1024


def _excluded(relative: Path) -> bool:
    if any(part in EXCLUDED_DIRS for part in relative.parts):
        return True
    name = relative.name.lower()
    if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
        return True
    if any(name.endswith(suffix) for suffix in EXCLUDED_SUFFIXES):
        return True
    return False


def seal_directory(source: str | Path, output: str | Path, master_secret: str | bytes) -> int:
    root = Path(source).resolve()
    destination = Path(output).resolve()
    if not root.is_dir():
        raise ValueError("Source directory does not exist")
    if destination == root or destination.is_dir():
        raise ValueError("Encrypted output must be a file path")
    if root in destination.parents and destination.suffix.lower() != ".grmesh":
        raise ValueError("An output inside the source tree must use the .grmesh extension")
    temporary = destination.with_name(destination.name + ".tmp")
    excluded_outputs = {destination, temporary}
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz", compresslevel=6) as archive:
        for item in sorted(root.rglob("*")):
            if item.is_symlink() or not item.is_file():
                continue
            if item.resolve() in excluded_outputs:
                continue
            relative = item.relative_to(root)
            if _excluded(relative):
                continue
            archive.add(item, arcname=relative.as_posix(), recursive=False)
    raw_archive = buffer.getvalue()
    encrypted = encrypt_bytes(raw_archive, master_secret)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_bytes(encrypted)
    os.chmod(temporary, 0o600)
    temporary.replace(destination)
    os.chmod(destination, 0o600)
    return len(encrypted)


def unseal_directory(encrypted_file: str | Path, destination: str | Path,
                     master_secret: str | bytes) -> int:
    payload = Path(encrypted_file).read_bytes()
    archive_bytes = decrypt_bytes(payload, master_secret)
    if len(archive_bytes) > MAX_ARCHIVE_BYTES:
        raise ValueError("Decrypted archive exceeds the extraction limit")
    root = Path(destination).resolve()
    root.mkdir(parents=True, exist_ok=True)
    total_written = 0
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
        members = archive.getmembers()
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or not path.parts or any(part in ("", ".", "..") for part in path.parts):
                raise ValueError("Archive contains an unsafe path")
            if not (member.isfile() or member.isdir()):
                raise ValueError("Archive contains an unsupported filesystem entry")
            if member.size < 0 or member.size > MAX_ARCHIVE_BYTES:
                raise ValueError("Archive member exceeds the extraction limit")
            target = (root / Path(*path.parts)).resolve()
            if os.path.commonpath((str(root), str(target))) != str(root):
                raise ValueError("Archive path escapes the destination")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                os.chmod(target, 0o700)
                continue
            total_written += member.size
            if total_written > MAX_ARCHIVE_BYTES:
                raise ValueError("Archive expands beyond the extraction limit")
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise ValueError("Archive member cannot be read")
            with source, target.open("xb") as output:
                while chunk := source.read(1024 * 1024):
                    output.write(chunk)
            os.chmod(target, 0o600)
    return total_written


def main() -> None:
    parser = argparse.ArgumentParser(prog="gpu-mesh-vault")
    subparsers = parser.add_subparsers(dest="command", required=True)
    seal = subparsers.add_parser("seal")
    seal.add_argument("--source", default=".")
    seal.add_argument("--output", required=True)
    seal.add_argument("--secret-env", default="GPU_MESH_MASTER_SECRET")
    open_parser = subparsers.add_parser("open")
    open_parser.add_argument("--input", required=True)
    open_parser.add_argument("--destination", required=True)
    open_parser.add_argument("--secret-env", default="GPU_MESH_MASTER_SECRET")
    args = parser.parse_args()
    secret = os.environ.get(args.secret_env)
    if not secret:
        raise SystemExit(f"Missing required environment variable: {args.secret_env}")
    if args.command == "seal":
        size = seal_directory(args.source, args.output, secret)
        print(f"Encrypted source bundle written ({size} bytes)")
    else:
        size = unseal_directory(args.input, args.destination, secret)
        print(f"Source bundle authenticated and extracted ({size} bytes)")


if __name__ == "__main__":
    main()
