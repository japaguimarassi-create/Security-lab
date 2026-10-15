import argparse
import hashlib
import json
import math
from pathlib import Path

import torch
from torch.nn import functional as F

from kodex_lm import KodexLanguageModel, ModelConfig, encode_bytes


def parse_args():
    parser = argparse.ArgumentParser(description="Measure next-token loss on a separate holdout corpus.")
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.device == "cuda" and not torch.cuda.is_available():
        raise SystemExit("CUDA was requested but is not available")
    device = torch.device(
        "cuda" if args.device == "cuda" or (args.device == "auto" and torch.cuda.is_available()) else "cpu"
    )
    checkpoint_path = args.checkpoint.resolve(strict=True)
    data_path = args.data.resolve(strict=True)
    payload = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    config = ModelConfig(**payload["config"])
    model = KodexLanguageModel(config).to(device)
    model.load_state_dict(payload["model_state_dict"])
    model.eval()

    raw = data_path.read_bytes()
    text = raw.decode("utf-8")
    if payload.get("tokenizer_kind") == "byte-level-bpe":
        try:
            from tokenizers import Tokenizer
        except ImportError as error:
            raise SystemExit("Install tokenizers to evaluate a BPE checkpoint") from error
        tokenizer_json = payload.get("tokenizer_json")
        if not isinstance(tokenizer_json, str) or not tokenizer_json:
            raise SystemExit("Checkpoint has no embedded BPE tokenizer")
        tokenizer = Tokenizer.from_str(tokenizer_json)
        token_ids = tokenizer.encode(text).ids
    else:
        token_ids = encode_bytes(text)

    if len(token_ids) < 2:
        raise SystemExit("Evaluation corpus must contain at least two tokens")

    total_loss = 0.0
    total_targets = 0
    block_size = config.block_size
    with torch.no_grad():
        for start in range(0, len(token_ids) - 1, block_size):
            window = token_ids[start:start + block_size + 1]
            if len(window) < 2:
                continue
            input_ids = torch.tensor([window[:-1]], dtype=torch.long, device=device)
            targets = torch.tensor([window[1:]], dtype=torch.long, device=device)
            logits, _ = model(input_ids)
            total_loss += float(F.cross_entropy(
                logits.reshape(-1, logits.size(-1)), targets.reshape(-1), reduction="sum"
            ).item())
            total_targets += targets.numel()

    mean_loss = total_loss / total_targets
    print(json.dumps({
        "status": "evaluation_complete",
        "checkpoint": str(checkpoint_path),
        "evaluation_data": str(data_path),
        "evaluation_sha256": hashlib.sha256(raw).hexdigest(),
        "evaluation_bytes": len(raw),
        "evaluation_tokens": len(token_ids),
        "target_tokens_scored": total_targets,
        "mean_cross_entropy": mean_loss,
        "perplexity": math.exp(min(mean_loss, 80.0)),
        "pretrained_weights": payload.get("training", {}).get("pretrained_weights", False),
        "note": "Language-model loss is not a substitute for held-out coding benchmarks or executed tests.",
    }, sort_keys=True))


if __name__ == "__main__":
    main()
