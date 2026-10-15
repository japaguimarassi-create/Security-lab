import unittest

import torch

from training.model import ByteTokenizer, KodexGPT, ModelConfig


class TransformerModelTests(unittest.TestCase):
    def test_default_model_exceeds_parameter_target_by_a_large_margin(self):
        model = KodexGPT()
        self.assertEqual(model.parameter_count(), 1678592)
        self.assertGreater(model.parameter_count(), 780000)

    def test_byte_tokenizer_round_trips_portuguese_and_unicode(self):
        tokenizer = ByteTokenizer()
        text = "Kodex: programação, ação, 你好, 🧠"
        self.assertEqual(tokenizer.decode(tokenizer.encode(text)), text)
        encoded = tokenizer.encode(text, add_eos=True)
        self.assertEqual(encoded[-1], tokenizer.eos_id)
        self.assertEqual(tokenizer.vocab_size, 257)

    def test_forward_shape_loss_and_gradients(self):
        model = KodexGPT(ModelConfig(max_seq_len=16, dropout=0.0))
        inputs = torch.randint(0, 257, (2, 16))
        targets = torch.randint(0, 257, (2, 16))
        logits, loss = model(inputs, targets)
        self.assertEqual(tuple(logits.shape), (2, 16, 257))
        self.assertEqual(loss.ndim, 0)
        loss.backward()
        self.assertIsNotNone(model.token_embedding.weight.grad)
        self.assertTrue(torch.isfinite(model.token_embedding.weight.grad).all())

    def test_causal_attention_does_not_change_earlier_logits_when_future_changes(self):
        torch.manual_seed(22)
        model = KodexGPT(ModelConfig(max_seq_len=16, dropout=0.0)).eval()
        first = torch.randint(0, 257, (1, 16))
        second = first.clone()
        second[:, 9:] = (second[:, 9:] + 31) % 257
        with torch.no_grad():
            first_logits, _ = model(first)
            second_logits, _ = model(second)
        self.assertTrue(torch.allclose(first_logits[:, :9], second_logits[:, :9], atol=1e-5, rtol=1e-5))

    def test_invalid_context_is_rejected(self):
        with self.assertRaises(ValueError):
            ModelConfig(max_seq_len=4).validate()
        model = KodexGPT(ModelConfig(max_seq_len=8, dropout=0.0))
        with self.assertRaises(ValueError):
            model(torch.zeros((1, 9), dtype=torch.long))


if __name__ == "__main__":
    unittest.main()
