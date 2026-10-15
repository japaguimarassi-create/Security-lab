import argparse
import json
from pathlib import Path

import torch

from kodex_lm import KodexLanguageModel, ModelConfig, decode_bytes, encode_bytes


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, default=Path("training/checkpoints/kodex-smoke.pt"))
    parser.add_argument("--prompt", default="def sum_numbers(a, b):\n")
    parser.add_argument("--max-new-tokens", type=int, default=160)
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--top-k", type=int, default=40)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.max_new_tokens < 1 or args.temperature <= 0 or args.top_k < 1:
        raise SystemExit("max-new-tokens, temperature, and top-k must be positive")
    device_name = "cuda" if args.device == "cuda" or (args.device == "auto" and torch.cuda.is_available()) else "cpu"
    if device_name == "cuda" and not torch.cuda.is_available():
        raise SystemExit("CUDA was requested but is not available")

    checkpoint_path = args.checkpoint.resolve()
    if not checkpoint_path.is_file():
        raise SystemExit(f"Checkpoint not found: {checkpoint_path}")
    payload = torch.load(checkpoint_path, map_location=device_name, weights_only=True)
    config = ModelConfig(**payload["config"])
    model = KodexLanguageModel(config).to(device_name)
    model.load_state_dict(payload["model_state_dict"])
    model.eval()

    context = torch.tensor([encode_bytes(args.prompt)], dtype=torch.long, device=device_name)
    if context.numel() == 0:
        context = torch.zeros((1, 1), dtype=torch.long, device=device_name)

    with torch.no_grad():
        for _ in range(args.max_new_tokens):
            input_ids = context[:, -config.block_size:]
            logits, _ = model(input_ids)
            next_logits = logits[:, -1, :] / args.temperature
            top_k = min(args.top_k, next_logits.size(-1))
            threshold = torch.topk(next_logits, top_k).values[:, -1].unsqueeze(-1)
            next_logits = next_logits.masked_fill(next_logits < threshold, float("-inf"))
            probabilities = torch.softmax(next_logits, dim=-1)
            next_token = torch.multinomial(probabilities, num_samples=1)
            context = torch.cat((context, next_token), dim=1)

    print(decode_bytes(context[0].tolist()))
    print(json.dumps({
        "status": "generated",
        "checkpoint": str(checkpoint_path),
        "pretrained_weights": False,
        "warning": "This is a tiny experimental model trained on a smoke corpus, not a capable programming assistant."
    }, sort_keys=True))


if __name__ == "__main__":
    main()