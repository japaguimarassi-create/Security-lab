from __future__ import annotations

from collections import Counter
from dataclasses import dataclass


def _merge_pair(sequence: list[int], left: int, right: int, new_id: int) -> list[int]:
    output: list[int] = []
    index = 0
    while index < len(sequence):
        if index + 1 < len(sequence) and sequence[index] == left and sequence[index + 1] == right:
            output.append(new_id)
            index += 2
        else:
            output.append(sequence[index])
            index += 1
    return output


@dataclass
class ByteBPETokenizer:
    merges: list[tuple[int, int]]

    @property
    def vocab_size(self) -> int:
        return 256 + len(self.merges)

    @classmethod
    def train(
        cls,
        texts: list[str],
        vocab_size: int = 1024,
        min_pair_frequency: int = 2,
    ) -> "ByteBPETokenizer":
        if vocab_size < 256:
            raise ValueError("vocab_size must be >= 256")
        if min_pair_frequency < 1:
            raise ValueError("min_pair_frequency must be positive")
        sequences = [list(text.encode("utf-8")) for text in texts if text]
        merges: list[tuple[int, int]] = []
        while 256 + len(merges) < vocab_size:
            counts: Counter[tuple[int, int]] = Counter()
            for sequence in sequences:
                counts.update(zip(sequence, sequence[1:]))
            if not counts:
                break
            pair, frequency = min(counts.items(), key=lambda item: (-item[1], item[0]))
            if frequency < min_pair_frequency:
                break
            new_id = 256 + len(merges)
            sequences = [_merge_pair(sequence, pair[0], pair[1], new_id) for sequence in sequences]
            merges.append(pair)
        return cls(merges=merges)

    def encode(self, text: str) -> list[int]:
        sequence = list(text.encode("utf-8"))
        for rank, (left, right) in enumerate(self.merges):
            sequence = _merge_pair(sequence, left, right, 256 + rank)
        return sequence

    def decode(self, token_ids: list[int]) -> str:
        token_bytes: list[bytes] = [bytes([index]) for index in range(256)]
        for left, right in self.merges:
            token_bytes.append(token_bytes[left] + token_bytes[right])
        output = bytearray()
        for token_id in token_ids:
            if not isinstance(token_id, int) or token_id < 0 or token_id >= len(token_bytes):
                continue
            output.extend(token_bytes[token_id])
        return output.decode("utf-8", errors="replace")

    def to_dict(self) -> dict:
        return {
            "type": "byte-level-bpe",
            "base_vocab_size": 256,
            "vocab_size": self.vocab_size,
            "merges": [[left, right] for left, right in self.merges],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ByteBPETokenizer":
        if data.get("type") != "byte-level-bpe":
            raise ValueError("unsupported tokenizer type")
        merges = [tuple(map(int, pair)) for pair in data.get("merges", [])]
        for index, pair in enumerate(merges):
            if len(pair) != 2 or any(token < 0 or token >= 256 + index for token in pair):
                raise ValueError("invalid merge table")
        return cls(merges=merges)
