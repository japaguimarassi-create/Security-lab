import pytest

from klod.mesh.crypto import (
    RelativityCorpusMismatch,
    VaultAuthenticationError,
    decrypt_bytes,
    encrypt_bytes,
)
from klod.mesh.vault import seal_directory, unseal_directory


SECRET = "0123456789abcdef0123456789abcdef0123456789abcdef"


def test_encryption_roundtrip_and_randomized_ciphertext():
    first = encrypt_bytes(b"mesh source payload", SECRET)
    second = encrypt_bytes(b"mesh source payload", SECRET)
    assert first != second
    assert decrypt_bytes(first, SECRET) == b"mesh source payload"


def test_wrong_secret_and_tampering_are_rejected():
    payload = encrypt_bytes(b"confidential", SECRET)
    with pytest.raises(VaultAuthenticationError):
        decrypt_bytes(payload, "a" * 48)
    modified = bytearray(payload)
    modified[-1] ^= 1
    with pytest.raises(VaultAuthenticationError):
        decrypt_bytes(bytes(modified), SECRET)


def test_directory_bundle_roundtrip_excludes_secrets_and_runtime_data(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "main.py").write_text("print('mesh')", encoding="utf-8")
    (source / ".env").write_text("PRIVATE=never-bundle", encoding="utf-8")
    (source / "data").mkdir()
    (source / "data" / "state.sqlite3").write_bytes(b"database")
    encrypted = tmp_path / "bundle.grmesh"
    target = tmp_path / "restored"
    seal_directory(source, encrypted, SECRET)
    unseal_directory(encrypted, target, SECRET)
    assert (target / "main.py").read_text(encoding="utf-8") == "print('mesh')"
    assert not (target / ".env").exists()
    assert not (target / "data" / "state.sqlite3").exists()


def test_archive_path_traversal_is_rejected(tmp_path):
    import io
    import tarfile
    from klod.mesh.crypto import encrypt_bytes

    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w:gz") as archive:
        info = tarfile.TarInfo("../escape.txt")
        info.size = 1
        archive.addfile(info, io.BytesIO(b"x"))
    encrypted = tmp_path / "unsafe.grmesh"
    encrypted.write_bytes(encrypt_bytes(raw.getvalue(), SECRET))
    with pytest.raises(ValueError, match="unsafe path"):
        unseal_directory(encrypted, tmp_path / "out", SECRET)
