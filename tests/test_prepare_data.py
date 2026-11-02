import json
import subprocess
import sys

def test_prepare_data_filters_and_deduplicates(tmp_path):
    source = tmp_path / "source.jsonl"
    output = tmp_path / "clean.jsonl"
    dedupe = tmp_path / "dedupe.sqlite3"
    text = " ".join(
        f"conceito{i} apresenta explicacao{i} exemplo{i} aplicacao{i} " for i in range(50)
    )
    row = {"text": text, "source_url": "https://example.org/a",
           "license": "CC-BY-4.0", "attribution": "Example"}
    source.write_text("\n".join(json.dumps(row) for _ in range(2)), encoding="utf-8")
    result = subprocess.run([
        sys.executable, "scripts/prepare_data.py", "--input", str(source),
        "--output", str(output), "--min-chars", "80", "--dedupe-db", str(dedupe)
    ], capture_output=True, text=True, check=True)
    stats = json.loads(result.stdout)
    assert stats["kept"] == 1
    assert stats["duplicates"] == 1
    assert len(output.read_text(encoding="utf-8").splitlines()) == 1
