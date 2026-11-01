import json
import subprocess
import sys
import yaml

def test_weighted_mixture_keeps_source_provenance(tmp_path):
    first = tmp_path / "pt.jsonl"
    second = tmp_path / "en.jsonl"
    first.write_text("\n".join(json.dumps({"text": f"Portuguese {i}"}) for i in range(5)), encoding="utf-8")
    second.write_text("\n".join(json.dumps({"text": f"English {i}"}) for i in range(5)), encoding="utf-8")
    config = tmp_path / "mixture.yaml"
    config.write_text(yaml.safe_dump({"sources": [
        {"name": "pt", "path": str(first), "weight": 0.7},
        {"name": "en", "path": str(second), "weight": 0.3}
    ]}), encoding="utf-8")
    output = tmp_path / "mixture.jsonl"
    subprocess.run([
        sys.executable, "scripts/build_mixture.py", "--config", str(config),
        "--output", str(output), "--max-documents", "10", "--seed", "4"
    ], check=True, capture_output=True, text=True)
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 10
    assert {row["mixture_source"] for row in rows} == {"pt", "en"}
