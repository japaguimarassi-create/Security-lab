import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prepare_corpus import prepare_corpus, resolve_source


class PrepareCorpusTests(unittest.TestCase):
    def test_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source, error = resolve_source(root, "../outside.py")
            self.assertIsNone(source)
            self.assertEqual(error, "path_not_relative_or_contains_parent")

    def test_only_approved_sources_are_included_and_duplicates_are_removed(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "source"
            root.mkdir()
            content = "def add(left, right):\n    return left + right\n"
            (root / "good.py").write_text(content, encoding="utf-8")
            (root / "duplicate.py").write_text(content, encoding="utf-8")
            token = "ghp_" + "A" * 35
            (root / "secret.py").write_text(f"TOKEN = '{token}'\n", encoding="utf-8")
            (root / "restricted.py").write_text("print('not approved')\n", encoding="utf-8")

            common = {
                "training_permitted": True,
                "license": "MIT",
                "source_url": "https://github.com/example/project/blob/0123456789abcdef/file.py",
                "commit": "0123456789abcdef",
            }
            entries = [
                {**common, "path": "good.py"},
                {**common, "path": "duplicate.py"},
                {**common, "path": "secret.py"},
                {**common, "path": "restricted.py", "license": "GPL-3.0-only"},
                {**common, "path": "good.py", "training_permitted": False},
            ]
            manifest = base / "manifest.jsonl"
            manifest.write_text(
                "\n".join(json.dumps(entry) for entry in entries) + "\n",
                encoding="utf-8",
            )
            output = base / "prepared.txt"
            report_path = base / "report.json"

            summary = prepare_corpus(manifest, root, output, report_path, 100_000)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            prepared = output.read_text(encoding="utf-8")

            self.assertEqual(summary["included_files"], 1)
            self.assertEqual(summary["excluded_files"], 4)
            self.assertEqual(prepared, content.strip() + "\n")
            reasons = {row.get("reason") for row in report["records"] if row["decision"] == "exclude"}
            self.assertIn("exact_duplicate", reasons)
            self.assertIn("binary_marker_or_possible_secret", reasons)
            self.assertIn("license_not_allowlisted", reasons)
            self.assertIn("training_permission_not_true", reasons)

    def test_source_outside_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "root"
            root.mkdir()
            outside = base / "outside.py"
            outside.write_text("print(1)", encoding="utf-8")
            source, error = resolve_source(root, "../outside.py")
            self.assertIsNone(source)
            self.assertEqual(error, "path_not_relative_or_contains_parent")


if __name__ == "__main__":
    unittest.main()