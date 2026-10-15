import tempfile
import unittest
from pathlib import Path

from tokenizers import Tokenizer

from train_tokenizer import train_tokenizer


class TrainTokenizerTests(unittest.TestCase):
    def test_tokenizer_is_trained_from_input_text_and_round_trips(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "corpus.txt"
            sample = (
                "def add(left, right):\n"
                "    return left + right\n\n"
                "function add(left, right) {\n"
                "  return left + right;\n}\n"
            ) * 20
            source.write_text(sample, encoding="utf-8")
            output = base / "tokenizer.json"

            result = train_tokenizer(source, output, 300)
            tokenizer = Tokenizer.from_file(str(output))
            round_tripped = tokenizer.decode(tokenizer.encode(sample).ids)

            self.assertTrue(output.is_file())
            self.assertGreater(result["vocabulary_size"], 256)
            self.assertEqual(round_tripped, sample)
            self.assertEqual(result["algorithm"], "byte-level BPE")


if __name__ == "__main__":
    unittest.main()