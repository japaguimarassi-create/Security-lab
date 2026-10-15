import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from training.build_mobile_mlm import (
    EXPECTED_PARAMETERS,
    VOCAB_SIZE,
    ByteBPE,
    MobileLanguageModel,
    read_samples,
)


class MobileLanguageModelTests(unittest.TestCase):
    def test_model_has_exact_trainable_parameter_count(self):
        model = MobileLanguageModel()
        count = sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad)
        self.assertEqual(count, EXPECTED_PARAMETERS)
        self.assertEqual(count, 264192)

    def test_byte_bpe_round_trips_portuguese_and_code(self):
        examples = [
            "Olá! Vamos conversar em português.\n",
            "function add(a, b) { return a + b; }",
            "Usuário: como você está?\nKodex: Estou bem.\n<fim>\n",
        ] * 12
        tokenizer = ByteBPE().fit(examples, VOCAB_SIZE)
        for example in examples:
            self.assertEqual(tokenizer.decode(tokenizer.encode(example)), example)
        self.assertGreaterEqual(256 + len(tokenizer.merges), 256)
        self.assertLessEqual(256 + len(tokenizer.merges), VOCAB_SIZE)

    def test_corpus_includes_chat_and_build_modes(self):
        samples = read_samples(ROOT / "training/data/mobile_dialogue.jsonl")
        modes = {prefix.splitlines()[0].removeprefix("Modo: ") for prefix, _ in samples}
        self.assertIn("chat", modes)
        self.assertIn("build", modes)
        self.assertGreaterEqual(len(samples), 50)
        self.assertIn("Histórico:\n", samples[0][0])
        self.assertTrue(any("Histórico:\nUsuário:" in prefix or "Histórico:\nKodex:" in prefix for prefix, _ in samples))


if __name__ == "__main__":
    unittest.main()
