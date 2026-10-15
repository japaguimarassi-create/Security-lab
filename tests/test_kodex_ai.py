from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import torch

from kodex_ai.corpus import load_records, split_records
from kodex_ai.model import KodexTransformer, ModelConfig, default_parameter_count, parameter_count
from kodex_ai.sweep import claim_trial, connect_db, enqueue_trials, finish_trial, summarize
from kodex_ai.tokenizer import ByteBPETokenizer


class TokenizerTests(unittest.TestCase):
    def test_bpe_round_trip_preserves_utf8_text(self):
        texts = ["Olá mundo", "Olá mundo de programação", "programação em português"]
        tokenizer = ByteBPETokenizer.train(texts, vocab_size=320, min_pair_frequency=1)
        for text in texts:
            self.assertEqual(tokenizer.decode(tokenizer.encode(text)), text)

    def test_tokenizer_serialization_round_trips(self):
        tokenizer = ByteBPETokenizer.train(["código", "código local", "localização"], 300, 1)
        restored = ByteBPETokenizer.from_dict(tokenizer.to_dict())
        self.assertEqual(restored.merges, tokenizer.merges)
        self.assertEqual(restored.decode(restored.encode("código localizado")), "código localizado")

    def test_invalid_merge_tables_are_rejected(self):
        with self.assertRaises(ValueError):
            ByteBPETokenizer.from_dict({"type": "byte-level-bpe", "merges": [[256, 0]]})


class CorpusTests(unittest.TestCase):
    def test_loads_and_deduplicates_jsonl_dialogues(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corpus.jsonl"
            path.write_text(
                json.dumps({"prompt": "O que é uma variável?", "answer": "Um nome para um valor."}, ensure_ascii=False)
                + "\n"
                + json.dumps({"prompt": "O que é uma variável?", "answer": "Um nome para um valor."}, ensure_ascii=False)
                + "\n"
                + json.dumps({"text": "Uma tarefa diferente."}, ensure_ascii=False)
                + "\n",
                encoding="utf-8",
            )
            records = load_records(path)
            self.assertEqual(len(records), 2)
            train, validation = split_records(records, seed=7)
            self.assertEqual(len(train), 1)
            self.assertEqual(len(validation), 1)

    def test_source_code_indentation_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corpus.jsonl"
            path.write_text(
                json.dumps({"text": "def first():\n    return 1"}, ensure_ascii=False) + "\n"
                + json.dumps({"text": "def second():\n  return 2"}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            records = load_records(path)
            self.assertIn("def first():\n    return 1", records)
            self.assertIn("def second():\n  return 2", records)

    def test_malformed_jsonl_is_reported_with_line_number(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corpus.jsonl"
            path.write_text('{"text":"ok"}\n{ malformed }\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "line 2"):
                load_records(path)


class ModelTests(unittest.TestCase):
    def test_default_model_has_more_than_two_million_parameters(self):
        self.assertEqual(default_parameter_count(1024), 2_002_048)

    def test_small_model_forward_and_causal_mask(self):
        config = ModelConfig(vocab_size=300, block_size=16, n_layer=1, n_head=2, n_embd=16, n_ff=32, dropout=0)
        model = KodexTransformer(config).eval()
        ids_a = torch.tensor([[65, 66, 67, 68]])
        ids_b = torch.tensor([[65, 66, 99, 100]])
        logits_a, loss = model(ids_a, ids_a)
        logits_b, _ = model(ids_b, ids_b)
        self.assertEqual(tuple(logits_a.shape), (1, 4, 300))
        self.assertTrue(torch.isfinite(loss))
        self.assertTrue(torch.allclose(logits_a[:, :2], logits_b[:, :2], atol=1e-6))

    def test_parameter_count_matches_tensors(self):
        config = ModelConfig(vocab_size=320, block_size=16, n_layer=1, n_head=2, n_embd=16, n_ff=32, dropout=0)
        model = KodexTransformer(config)
        self.assertEqual(parameter_count(model), sum(p.numel() for p in model.parameters() if p.requires_grad))
        self.assertGreater(parameter_count(model), 0)


class SweepQueueTests(unittest.TestCase):
    def test_queue_plans_claims_and_records_a_trial(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "jobs.sqlite3"
            report = enqueue_trials(db, trials=5, seed=3, steps=2, output_root=Path(directory) / "runs")
            self.assertEqual(report["inserted"], 5)
            self.assertEqual(enqueue_trials(db, 5, 3, 2, Path(directory) / "runs")["inserted"], 0)
            trial = claim_trial(db)
            self.assertIsNotNone(trial)
            finish_trial(db, trial["trial_id"], 0)
            summary = summarize(db)
            self.assertEqual(summary["total_trials"], 5)
            self.assertEqual(summary["counts"]["completed"], 1)
            self.assertEqual(summary["counts"]["pending"], 4)

    def test_plan_rejects_unbounded_or_invalid_job_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                enqueue_trials(Path(directory) / "jobs.sqlite3", 0)
            with self.assertRaises(ValueError):
                enqueue_trials(Path(directory) / "jobs.sqlite3", 10_000_001)


if __name__ == "__main__":
    unittest.main()
