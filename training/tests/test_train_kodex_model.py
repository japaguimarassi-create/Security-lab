import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import torch

from training.train_kodex_model import get_batch, load_records, parse_args, split_records


class KodexTrainerTests(unittest.TestCase):
    def test_argument_parser_exposes_unique_moe_and_sweep_options(self):
        with patch.object(sys, "argv", [
            "train_kodex_model.py",
            "--router-aux-loss-coef", "0.02",
            "--dropout", "0.15",
            "--max-seq-len", "64",
        ]):
            args = parse_args()
        self.assertEqual(args.router_aux_loss_coef, 0.02)
        self.assertEqual(args.dropout, 0.15)
        self.assertEqual(args.block_size, 64)

    def test_training_corpus_is_validated_and_split_without_overlap(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "corpus.jsonl"
            examples = [
                {"mode": "chat", "prompt": f"pergunta {index}", "answer": f"resposta {index}"}
                for index in range(20)
            ]
            source.write_text("".join(json.dumps(example, ensure_ascii=False) + "\n" for example in examples), encoding="utf-8")
            records, digest = load_records(source)
            train, validation, test = split_records(records, seed=71)
            self.assertEqual(len(records), 20)
            self.assertEqual(len(train) + len(validation) + len(test), 20)
            self.assertEqual(len(set(train) & set(validation)), 0)
            self.assertEqual(len(set(train) & set(test)), 0)
            self.assertEqual(len(set(validation) & set(test)), 0)
            self.assertEqual(len(digest), 64)
            self.assertIn("Usuário:", records[0])

    def test_batching_handles_short_and_full_contexts(self):
        short_tokens = torch.arange(7, dtype=torch.long)
        x_short, y_short = get_batch(short_tokens, batch_size=3, block_size=128, device=torch.device("cpu"))
        self.assertEqual(tuple(x_short.shape), (3, 6))
        self.assertEqual(tuple(y_short.shape), (3, 6))
        self.assertTrue(torch.equal(x_short[:, 1:], y_short[:, :-1]))
        long_tokens = torch.arange(512, dtype=torch.long)
        x_long, y_long = get_batch(long_tokens, batch_size=2, block_size=64, device=torch.device("cpu"))
        self.assertEqual(tuple(x_long.shape), (2, 64))
        self.assertEqual(tuple(y_long.shape), (2, 64))
        self.assertTrue(torch.equal(x_long[:, 1:], y_long[:, :-1]))


if __name__ == "__main__":
    unittest.main()
