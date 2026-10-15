import json
import tempfile
import unittest
from pathlib import Path

from training.normalize_dialogue_corpus import normalize_corpus


class DialogueCorpusTests(unittest.TestCase):
    def test_normalizes_deduplicates_and_reports_small_corpus(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.jsonl"
            records = [
                {"mode": "chat", "prompt": f"question {index}", "answer": f"answer {index}"}
                for index in range(10)
            ]
            records.append({"mode": "chat", "prompt": " QUESTION   0 ", "answer": "ANSWER 0"})
            records.append({"mode": "chat", "prompt": "question 0", "answer": "a different answer"})
            source.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
            output = root / "clean.jsonl"
            report_path = root / "report.json"
            report = normalize_corpus([str(source)], str(output), str(report_path))
            cleaned = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(report["input_examples"], 12)
            self.assertEqual(report["unique_examples"], 11)
            self.assertEqual(report["duplicates_removed"], 1)
            self.assertEqual(report["prompts_with_multiple_normalized_answers"], 1)
            self.assertEqual(len(cleaned), 11)
            self.assertTrue(report_path.exists())
            self.assertIn("too small", report["warnings"][0].lower())

    def test_invalid_json_does_not_write_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "bad.jsonl"
            source.write_text('{"prompt":"ok","answer":"yes"}\n{ broken }\n', encoding="utf-8")
            output = root / "clean.jsonl"
            with self.assertRaisesRegex(ValueError, "invalid JSON"):
                normalize_corpus([str(source)], str(output), "")
            self.assertFalse(output.exists())

    def test_blank_prompt_or_answer_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "blank.jsonl"
            rows = [{"prompt": "", "answer": "answer"}] + [
                {"prompt": f"q {i}", "answer": "a"} for i in range(10)
            ]
            source.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must not be blank"):
                normalize_corpus([str(source)], str(root / "clean.jsonl"), "")


if __name__ == "__main__":
    unittest.main()
