import argparse
import base64
import json
import math
import os
import random
from collections import Counter
from pathlib import Path

import torch
from torch import nn
from torch.nn import functional as F


VOCAB_SIZE = 512
EMBEDDING_SIZE = 128
HIDDEN_SIZE = 128
MAX_SEQUENCE_LENGTH = 144
EXPECTED_PARAMETERS = 264192


class ByteBPE:
    def __init__(self, merges=None):
        self.merges = [tuple(pair) for pair in (merges or [])]
        self.token_bytes = [bytes([value]) for value in range(256)]
        for left, right in self.merges:
            self.token_bytes.append(self.token_bytes[left] + self.token_bytes[right])

    @staticmethod
    def _merge_sequence(sequence, left, right, new_id):
        merged = []
        index = 0
        while index < len(sequence):
            if index + 1 < len(sequence) and sequence[index] == left and sequence[index + 1] == right:
                merged.append(new_id)
                index += 2
            else:
                merged.append(sequence[index])
                index += 1
        return merged

    def fit(self, texts, vocab_size=VOCAB_SIZE):
        if vocab_size < 256 or vocab_size > 65536:
            raise ValueError("vocab_size must be between 256 and 65536")
        sequences = [list(text.encode("utf-8")) for text in texts]
        target_merges = vocab_size - 256
        for _ in range(target_merges):
            counts = Counter()
            for sequence in sequences:
                counts.update(zip(sequence, sequence[1:]))
            if not counts:
                break
            (left, right), frequency = counts.most_common(1)[0]
            new_id = 256 + len(self.merges)
            self.merges.append((left, right))
            self.token_bytes.append(self.token_bytes[left] + self.token_bytes[right])
            sequences = [self._merge_sequence(sequence, left, right, new_id) for sequence in sequences]
        return self

    def encode(self, text):
        sequence = list(text.encode("utf-8"))
        for offset, (left, right) in enumerate(self.merges):
            sequence = self._merge_sequence(sequence, left, right, 256 + offset)
        return sequence

    def decode(self, token_ids):
        return b"".join(self.token_bytes[int(token_id)] for token_id in token_ids).decode("utf-8", errors="replace")


class MobileLanguageModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.embedding = nn.Embedding(VOCAB_SIZE, EMBEDDING_SIZE)
        self.input_norm = nn.LayerNorm(EMBEDDING_SIZE)
        self.lstm = nn.LSTM(EMBEDDING_SIZE, HIDDEN_SIZE, num_layers=1, batch_first=True)
        self.output_norm = nn.LayerNorm(HIDDEN_SIZE)
        self.lm_head = nn.Linear(HIDDEN_SIZE, VOCAB_SIZE, bias=True)

    def forward(self, input_ids, state=None):
        embedded = self.input_norm(self.embedding(input_ids))
        hidden, state = self.lstm(embedded, state)
        logits = self.lm_head(self.output_norm(hidden))
        return logits, state


def read_samples(path):
    samples = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid JSON on line {line_number}: {error}") from error
        mode = item.get("mode")
        prompt = item.get("prompt")
        answer = item.get("answer")
        if mode not in ("chat", "build") or not isinstance(prompt, str) or not prompt.strip() or not isinstance(answer, str) or not answer.strip():
            raise ValueError(f"Invalid dialogue sample on line {line_number}")
        prefix = f"Modo: {mode}\nUsuário: {prompt.strip()}\nKodex: "
        suffix = answer.strip() + "\n<fim>\n"
        samples.append((prefix, suffix))
    if len(samples) < 20:
        raise ValueError("At least 20 curated dialogue samples are required")
    return samples


def encode_samples(samples, tokenizer):
    encoded = []
    for prefix, suffix in samples:
        prefix_ids = tokenizer.encode(prefix)
        suffix_ids = tokenizer.encode(suffix)
        if len(suffix_ids) >= MAX_SEQUENCE_LENGTH:
            suffix_ids = suffix_ids[:MAX_SEQUENCE_LENGTH - 2]
        prefix_limit = max(8, MAX_SEQUENCE_LENGTH - len(suffix_ids))
        if len(prefix_ids) > prefix_limit:
            prefix_ids = prefix_ids[-prefix_limit:]
        ids = prefix_ids + suffix_ids
        if len(ids) < 3:
            continue
        inputs = ids[:-1]
        targets = ids[1:]
        masked_targets = targets[:]
        for index in range(max(0, len(prefix_ids) - 1)):
            masked_targets[index] = -100
        encoded.append((inputs, masked_targets))
    return encoded


def make_batch(samples, indices, device):
    selected = [samples[index] for index in indices]
    length = max(len(item[0]) for item in selected)
    inputs = torch.zeros((len(selected), length), dtype=torch.long)
    targets = torch.full((len(selected), length), -100, dtype=torch.long)
    for row, (input_ids, target_ids) in enumerate(selected):
        inputs[row, :len(input_ids)] = torch.tensor(input_ids, dtype=torch.long)
        targets[row, :len(target_ids)] = torch.tensor(target_ids, dtype=torch.long)
    return inputs.to(device), targets.to(device)


def evaluate(model, samples, device, batch_size=8):
    model.eval()
    losses = []
    with torch.no_grad():
        for start in range(0, len(samples), batch_size):
            indices = list(range(start, min(start + batch_size, len(samples))))
            inputs, targets = make_batch(samples, indices, device)
            logits, _ = model(inputs)
            loss = F.cross_entropy(logits.reshape(-1, VOCAB_SIZE), targets.reshape(-1), ignore_index=-100)
            if torch.isfinite(loss):
                losses.append(float(loss.item()))
    model.train()
    return sum(losses) / max(1, len(losses))


def quantize_tensor(tensor):
    values = tensor.detach().cpu().float().contiguous().numpy().reshape(-1)
    maximum = float(abs(values).max()) if values.size else 0.0
    scale = maximum / 127.0 if maximum > 0 else 1.0
    quantized = values.clip(-127 * scale, 127 * scale)
    quantized = (quantized / scale).round().clip(-127, 127).astype("int8")
    raw = quantized.tobytes()
    return {"scale": scale, "data": base64.b64encode(raw).decode("ascii"), "count": int(values.size)}


def export_javascript(model, tokenizer, out_path, steps, train_loss, validation_loss, train_count, validation_count):
    state = {name: quantize_tensor(tensor) for name, tensor in model.state_dict().items()}
    payload = {
        "version": "0.3.0",
        "architecture": "single-layer LSTM language model",
        "parameterCount": sum(parameter.numel() for parameter in model.parameters()),
        "vocabSize": VOCAB_SIZE,
        "embeddingSize": EMBEDDING_SIZE,
        "hiddenSize": HIDDEN_SIZE,
        "maxContextTokens": MAX_SEQUENCE_LENGTH,
        "merges": tokenizer.merges,
        "tensors": state,
        "training": {
            "method": "next-token supervised dialogue fine-tuning from random initialization",
            "steps": steps,
            "trainExamples": train_count,
            "validationExamples": validation_count,
            "trainLoss": train_loss,
            "validationLoss": validation_loss,
            "pretrainedWeightsUsed": False
        }
    }
    if payload["parameterCount"] != EXPECTED_PARAMETERS:
        raise RuntimeError(f"Expected {EXPECTED_PARAMETERS} trainable parameters, got {payload['parameterCount']}")
    out_path.write_text(
        "window.KODEX_MLM_DATA=" + json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + ";\n",
        encoding="utf-8"
    )


def main():
    parser = argparse.ArgumentParser(description="Train and export the 264,192-parameter Kodex mobile language model.")
    parser.add_argument("--data", type=Path, default=Path("training/data/mobile_dialogue.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("kodex-model.js"))
    parser.add_argument("--steps", type=int, default=500)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if args.steps < 1 or args.batch_size < 1:
        raise ValueError("steps and batch-size must be positive")

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))
    device = torch.device("cpu")

    samples = read_samples(args.data)
    tokenizer = ByteBPE().fit([part for pair in samples for part in pair], VOCAB_SIZE)
    encoded = encode_samples(samples, tokenizer)
    order = list(range(len(encoded)))
    random.shuffle(order)
    validation_count = max(1, min(len(order) // 8, 16))
    validation_indices = order[:validation_count]
    training_indices = order[validation_count:]
    train_samples = [encoded[index] for index in training_indices]
    validation_samples = [encoded[index] for index in validation_indices]

    model = MobileLanguageModel().to(device)
    parameter_count = sum(parameter.numel() for parameter in model.parameters())
    if parameter_count != EXPECTED_PARAMETERS:
        raise RuntimeError(f"Architecture has {parameter_count} parameters, expected {EXPECTED_PARAMETERS}")
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.001, weight_decay=0.01)
    model.train()
    recent_losses = []
    for step in range(1, args.steps + 1):
        indices = [random.randrange(len(train_samples)) for _ in range(min(args.batch_size, len(train_samples)))]
        inputs, targets = make_batch(train_samples, indices, device)
        logits, _ = model(inputs)
        loss = F.cross_entropy(logits.reshape(-1, VOCAB_SIZE), targets.reshape(-1), ignore_index=-100)
        if not torch.isfinite(loss):
            raise FloatingPointError(f"Non-finite loss at step {step}")
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        recent_losses.append(float(loss.item()))
        if step == 1 or step % 100 == 0 or step == args.steps:
            print(f"step={step}/{args.steps} train_loss={sum(recent_losses[-50:]) / min(50, len(recent_losses)):.4f}", flush=True)

    final_train_loss = evaluate(model, train_samples, device)
    final_validation_loss = evaluate(model, validation_samples, device)
    model.eval()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    export_javascript(model, tokenizer, args.output, args.steps, final_train_loss, final_validation_loss, len(train_samples), len(validation_samples))
    print(json.dumps({
        "output": str(args.output),
        "parameter_count": parameter_count,
        "vocabulary_size": 256 + len(tokenizer.merges),
        "merges": len(tokenizer.merges),
        "train_examples": len(train_samples),
        "validation_examples": len(validation_samples),
        "training_steps": args.steps,
        "train_loss": round(final_train_loss, 4),
        "validation_loss": round(final_validation_loss, 4),
        "bytes": args.output.stat().st_size
    }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
