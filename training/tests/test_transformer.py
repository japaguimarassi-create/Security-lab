import json
import sys
import tempfile
import unittest
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from training.train_transformer import (
    EOS_ID,
    EXPECTED_PARAMETERS,
    MODEL_CONFIG,
    KodexTransformer,
    count_parameters,
    encode_text,
    read_records,
    split_records
)
from training.run_sweep import MAX_TRIALS, trial_config


class TransformerTrainingTests(unittest.TestCase):
    def test_transformer_exceeds_requested_parameter_threshold(self):
        model = KodexTransformer()
        count = count_parameters(model)
        self.assertEqual(count, EXPECTED_PARAMETERS)
        self.assertGreater(count, 780000)
        self.assertGreater(count, 1_500_000)
        self.assertEqual(count, 1958977)

    def test_causal_transformer_returns_logits_for_every_input_token(self):
        model = KodexTransformer()
        model.eval()
        tokens = torch.randint(0, MODEL_CONFIG["vocab_size"], (2, 24))
        with torch.no_grad():
            logits = model(tokens)
        self.assertEqual(tuple(logits.shape), (2, 24, MODEL_CONFIG["vocab_size"]))
        self.assertTrue(torch.isfinite(logits).all().item())

    def test_utf8_encoding_preserves_accented_text_bytes_and_eos(self):
        encoded = encode_text("Olá, código.")
        self.assertEqual(encoded[:-1], list("Olá, código.".encode("utf-8")))
        self.assertEqual(encoded[-1], EOS_ID)

    def test_jsonl_corpus_reader_creates_dialogue_training_text(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "data.jsonl"
            path.write_text(
                json.dumps({"mode": "chat", "prompt": "Oi", "answer": "Olá"}) + "\n" +
                json.dumps({"mode": "build", "history": [{"role": "user", "text": "x"}], "prompt": "Crie", "answer": "Feito"}) + "\n",
                encoding="utf-8"
            )
            records = read_records(path)
        self.assertEqual(len(records), 2)
        self.assertIn("Usuário: Oi", records[0])
        self.assertIn("Kodex: Olá", records[0])
        self.assertIn("Usuário: x", records[1])
        self.assertIn("Kodex: Feito", records[1])

    def test_train_validation_split_is_deterministic_and_disjoint(self):
        records = [f"sample {index}" for index in range(20)]
        train_a, val_a = split_records(records, 7)
        train_b, val_b = split_records(records, 7)
        self.assertEqual(train_a, train_b)
        self.assertEqual(val_a, val_b)
        self.assertEqual(len(val_a), 2)
        self.assertEqual(len(train_a) + len(val_a), len(records))
        self.assertTrue(all(sample[-1] == EOS_ID for sample in train_a + val_a))

    def test_sweep_generates_deterministic_trial_configurations(self):
        self.assertEqual(MAX_TRIALS, 1_000_000)
        self.assertEqual(trial_config(123, 42), trial_config(123, 42))
        self.assertNotEqual(trial_config(123, 42)["seed"], trial_config(124, 42)["seed"])
        self.assertIn(trial_config(123, 42)["learning_rate"], (0.0001, 0.0002, 0.0003, 0.0005, 0.0008))


if __name__ == "__main__":
    unittest.main()
