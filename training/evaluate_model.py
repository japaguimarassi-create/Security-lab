import argparse
import json
import re
import sys
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "training"))

from model import ByteTokenizer, KodexGPT, ModelConfig
from train_language_model import load_records, split_records


def parse_args():
    parser = argparse.ArgumentParser(description="Generate and score held-out prompts from a trained Kodex checkpoint.")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--data", default="training/data/mobile_dialogue.jsonl")
    parser.add_argument("--split-seed", type=int, default=42)
    parser.add_argument("--max-samples", type=int, default=5)
    parser.add_argument("--max-new-tokens", type=int, default=96)
    parser.add_argument("--output", default="")
    parser.add_argument("--seed", type=int, default=701)
    return parser.parse_args()


def normalized(value):
    return " ".join(value.casefold().split())


def word_f1(reference, prediction):
    ref_words = normalized(reference).split()
    pred_words = normalized(prediction).split()
    if not ref_words or not pred_words:
        return 1.0 if ref_words == pred_words else 0.0
    ref_counts = {}
    pred_counts = {}
    for word in ref_words:
        ref_counts[word] = ref_counts.get(word, 0) + 1
    for word in pred_words:
        pred_counts[word] = pred_counts.get(word, 0) + 1
    overlap = sum(min(count, pred_counts.get(word, 0)) for word, count in ref_counts.items())
    if not overlap:
        return 0.0
    precision = overlap / len(pred_words)
    recall = overlap / len(ref_words)
    return 2 * precision * recall / (precision + recall)


def recover_pair(record):
    match = re.match(r"^Usuário: (.*?)\nKodex: (.*?)\n$", record, flags=re.DOTALL)
    if not match:
        return None
    return match.group(1), match.group(2)


def main():
    args = parse_args()
    if args.max_samples < 1 or args.max_samples > 50:
        raise ValueError("max-samples must be between 1 and 50.")
    if args.max_new_tokens < 1 or args.max_new_tokens > 512:
        raise ValueError("max-new-tokens must be between 1 and 512.")
    checkpoint_path = Path(args.checkpoint)
    if not checkpoint_path.is_file():
        raise FileNotFoundError(f"Checkpoint was not found: {checkpoint_path}")
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    config = ModelConfig(**checkpoint["model_config"])
    model = KodexGPT(config)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    tokenizer = ByteTokenizer()
    records, _ = load_records(args.data)
    _, _, test_records = split_records(records, args.split_seed)
    pairs = [pair for pair in (recover_pair(record) for record in test_records) if pair is not None]
    if not pairs:
        raise ValueError("No prompt/answer records were available in the held-out split.")
    torch.manual_seed(args.seed)
    results = []
    for prompt, reference in pairs[:args.max_samples]:
        prefix = "Usuário: " + prompt + "\nKodex: "
        prompt_tokens = tokenizer.encode(prefix)
        prompt_tokens = prompt_tokens[-config.max_seq_len:]
        input_ids = torch.tensor([prompt_tokens], dtype=torch.long)
        with torch.no_grad():
            generated_ids = model.generate(input_ids, max_new_tokens=args.max_new_tokens, temperature=0.7, top_k=30)
        generated = tokenizer.decode(generated_ids[0, len(prompt_tokens):].tolist()).strip()
        generated = generated.split("\nUsuário:")[0].strip()
        results.append({
            "prompt": prompt,
            "reference_answer": reference,
            "generated_answer": generated,
            "exact_match": normalized(reference) == normalized(generated),
            "word_f1_diagnostic": round(word_f1(reference, generated), 4),
        })
    report = {
        "checkpoint": str(checkpoint_path),
        "parameter_count": checkpoint["parameter_count"],
        "evaluated_samples": len(results),
        "exact_match_rate": sum(item["exact_match"] for item in results) / len(results),
        "mean_word_f1_diagnostic": sum(item["word_f1_diagnostic"] for item in results) / len(results),
        "samples": results,
        "warning": "Word F1 is only a rough diagnostic and exact match is strict. Human review is required; this small dataset cannot establish general chat/coding quality.",
    }
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        destination = Path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(encoded, encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()
