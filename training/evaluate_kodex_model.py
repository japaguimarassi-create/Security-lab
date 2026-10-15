import argparse
import json
import math
import re
from pathlib import Path

import torch
from tokenizers import Tokenizer

from kodex_lm import KodexLanguageModel, ModelConfig, masked_cross_entropy
from train_kodex_model import load_records, split_records


def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate held-out generations from a Kodex sparse-Transformer checkpoint.")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--tokenizer", default="")
    parser.add_argument("--data", default="training/data/mobile_dialogue.jsonl")
    parser.add_argument("--split-seed", type=int, default=42)
    parser.add_argument("--max-samples", type=int, default=5)
    parser.add_argument("--max-new-tokens", type=int, default=64)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--top-k", type=int, default=30)
    parser.add_argument("--seed", type=int, default=701)
    parser.add_argument("--output", default="")
    return parser.parse_args()


def word_f1(reference, prediction):
    reference_words = re.findall(r"[\wÀ-ÿ]+", reference.casefold())
    prediction_words = re.findall(r"[\wÀ-ÿ]+", prediction.casefold())
    if not reference_words or not prediction_words:
        return 1.0 if reference_words == prediction_words else 0.0
    reference_counts = {}
    prediction_counts = {}
    for word in reference_words:
        reference_counts[word] = reference_counts.get(word, 0) + 1
    for word in prediction_words:
        prediction_counts[word] = prediction_counts.get(word, 0) + 1
    overlap = sum(min(count, prediction_counts.get(word, 0)) for word, count in reference_counts.items())
    if overlap == 0:
        return 0.0
    precision = overlap / len(prediction_words)
    recall = overlap / len(reference_words)
    return 2 * precision * recall / (precision + recall)


@torch.no_grad()
def generate(model, tokenizer, prefix, eos_id, max_new_tokens, temperature, top_k):
    model.eval()
    input_ids = torch.tensor([tokenizer.encode(prefix).ids], dtype=torch.long)
    prompt_length = input_ids.shape[1]
    for _ in range(max_new_tokens):
        context = input_ids[:, -model.config.block_size:]
        logits, _ = model(context)
        next_logits = logits[:, -1, :] / temperature
        if top_k > 0:
            count = min(top_k, next_logits.shape[-1])
            values, _ = torch.topk(next_logits, count)
            next_logits[next_logits < values[:, [-1]]] = -torch.inf
        next_token = torch.multinomial(torch.softmax(next_logits, dim=-1), num_samples=1)
        token_id = int(next_token.item())
        if token_id == eos_id:
            break
        input_ids = torch.cat((input_ids, next_token), dim=1)
    generated_ids = input_ids[0, prompt_length:].tolist()
    return tokenizer.decode(generated_ids, skip_special_tokens=True).strip()


def main():
    args = parse_args()
    if not 1 <= args.max_samples <= 50:
        raise ValueError("max-samples must be between 1 and 50.")
    if not 1 <= args.max_new_tokens <= 512:
        raise ValueError("max-new-tokens must be between 1 and 512.")
    if not 0 < args.temperature <= 2:
        raise ValueError("temperature must be in (0, 2].")
    if not 0 <= args.top_k <= 512:
        raise ValueError("top-k must be between 0 and 512.")

    checkpoint_path = Path(args.checkpoint)
    if not checkpoint_path.is_file():
        raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    tokenizer_path = Path(args.tokenizer) if args.tokenizer else checkpoint_path.parent / "tokenizer.json"
    if not tokenizer_path.is_file() and checkpoint_path.stem == "best-model":
        tokenizer_path = checkpoint_path.parent / "best-model-tokenizer.json"
    if not tokenizer_path.is_file():
        raise FileNotFoundError("Tokenizer JSON not found beside the checkpoint; pass --tokenizer.")
    if checkpoint.get("tokenizer_sha256"):
        import hashlib
        digest = hashlib.sha256(tokenizer_path.read_bytes()).hexdigest()
        if digest != checkpoint["tokenizer_sha256"]:
            raise ValueError("Tokenizer hash does not match this checkpoint.")

    tokenizer = Tokenizer.from_file(str(tokenizer_path))
    eos_id = tokenizer.token_to_id("[EOS]")
    if eos_id is None:
        raise ValueError("Tokenizer is missing [EOS].")
    config = ModelConfig(**checkpoint["model_config"])
    if tokenizer.get_vocab_size() != config.vocab_size:
        raise ValueError("Tokenizer vocabulary size does not match the checkpoint model config.")
    model = KodexLanguageModel(config)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()

    records, _ = load_records(args.data)
    _, _, test_records = split_records(records, args.split_seed)
    examples = []
    for record in test_records:
        match = re.match(r"^(?:Modo: ([^\n]+)\n)?Usuário: (.*?)\nKodex: (.*?)\n$", record, flags=re.DOTALL)
        if match:
            examples.append({"mode": match.group(1) or "chat", "prompt": match.group(2), "answer": match.group(3)})
    if not examples:
        raise ValueError("No prompt/answer examples found in held-out data.")

    torch.manual_seed(args.seed)
    selected = examples[:args.max_samples]
    results = []
    for example in selected:
        prefix = f"Modo: {example['mode']}\nUsuário: {example['prompt']}\nKodex: "
        prediction = generate(
            model,
            tokenizer,
            prefix,
            eos_id,
            args.max_new_tokens,
            args.temperature,
            args.top_k,
        )
        reference = example["answer"]
        normalized_prediction = " ".join(prediction.casefold().split())
        normalized_reference = " ".join(reference.casefold().split())
        results.append({
            "mode": example["mode"],
            "prompt": example["prompt"],
            "reference_answer": reference,
            "generated_answer": prediction,
            "exact_match": normalized_prediction == normalized_reference,
            "word_f1_diagnostic": round(word_f1(reference, prediction), 4),
        })

    report = {
        "checkpoint": str(checkpoint_path),
        "parameter_count": checkpoint.get("parameter_count", model.parameter_count()),
        "tokenizer_vocabulary_size": tokenizer.get_vocab_size(),
        "evaluated_samples": len(results),
        "exact_match_rate": sum(item["exact_match"] for item in results) / len(results),
        "mean_word_f1_diagnostic": sum(item["word_f1_diagnostic"] for item in results) / len(results),
        "samples": results,
        "warning": "Exact match and word F1 are rough diagnostics, not human-quality metrics. Inspect all generated samples and test results manually; the current starter corpus is too small to prove broad language capability.",
    }
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        destination = Path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(encoded, encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()
