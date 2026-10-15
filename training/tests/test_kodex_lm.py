import sys
import unittest
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kodex_lm import KodexLanguageModel, ModelConfig


class KodexLanguageModelTests(unittest.TestCase):
    def setUp(self):
        torch.manual_seed(7)
        self.config = ModelConfig(
            vocab_size=128,
            block_size=16,
            n_layer=2,
            n_head=4,
            n_embd=32,
            n_kv_head=2,
            dropout=0.0,
        )

    def test_forward_loss_and_gradients_are_finite(self):
        model = KodexLanguageModel(self.config)
        inputs = torch.randint(0, self.config.vocab_size, (2, 12))
        targets = torch.randint(0, self.config.vocab_size, (2, 12))
        logits, loss = model(inputs, targets)
        self.assertEqual(tuple(logits.shape), (2, 12, self.config.vocab_size))
        self.assertTrue(torch.isfinite(loss).item())
        loss.backward()
        gradients = [parameter.grad for parameter in model.parameters() if parameter.grad is not None]
        self.assertTrue(gradients)
        self.assertTrue(all(torch.isfinite(gradient).all().item() for gradient in gradients))

    def test_causal_attention_does_not_leak_future_tokens(self):
        model = KodexLanguageModel(self.config)
        model.eval()
        original = torch.randint(0, self.config.vocab_size, (1, 12))
        changed = original.clone()
        changed[:, 6:] = (changed[:, 6:] + 17) % self.config.vocab_size
        with torch.no_grad():
            original_logits, _ = model(original)
            changed_logits, _ = model(changed)
        self.assertTrue(torch.allclose(original_logits[:, :6], changed_logits[:, :6], atol=1e-5, rtol=1e-5))

    def test_rejects_invalid_grouped_query_configuration(self):
        with self.assertRaises(ValueError):
            KodexLanguageModel(ModelConfig(
                vocab_size=128,
                block_size=16,
                n_layer=1,
                n_head=4,
                n_embd=32,
                n_kv_head=3,
            ))

    def test_rejects_sequence_longer_than_context(self):
        model = KodexLanguageModel(self.config)
        with self.assertRaises(ValueError):
            model(torch.zeros((1, 17), dtype=torch.long))


if __name__ == "__main__":
    unittest.main()
