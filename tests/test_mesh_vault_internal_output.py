import pytest

from klod.mesh.crypto import decrypt_bytes, encrypt_bytes
from klod.mesh.vault import seal_directory, unseal_directory


SECRET = "0123456789abcdef0123456789abcdef0123456789abcdef"


def test_seal_and_unseal_archive_inside_source_tree(tmp_path):
    source = tmp_path / "project"
    source.mkdir()
    (source / "README.md").write_text("private source", encoding="utf-8")
    destination = source / "dist" / "project.grmesh"
    restored = tmp_path / "restored"

    seal_directory(source, destination, SECRET)
    assert destination.is_file()
    assert unseal_directory(destination, restored, SECRET) > 0
    assert (restored / "README.md").read_text(encoding="utf-8") == "private source"
    assert not (restored / "dist" / "project.grmesh").exists()


def test_internal_vault_output_must_use_grmesh_extension(tmp_path):
    source = tmp_path / "project"
    source.mkdir()
    with pytest.raises(ValueError, match=".grmesh"):
        seal_directory(source, source / "archive.tar.gz", SECRET)


def test_internal_vault_does_not_overwrite_source_files(tmp_path):
    source = tmp_path / "project"
    source.mkdir()
    original = source / "module.py"
    original.write_text("print('original')", encoding="utf-8")
    destination = source / "source.grmesh"

    seal_directory(source, destination, SECRET)
    assert original.read_text(encoding="utf-8") == "print('original')"
    restored = tmp_path / "restored"
    unseal_directory(destination, restored, SECRET)
    assert (restored / "module.py").read_text(encoding="utf-8") == "print('original')"
