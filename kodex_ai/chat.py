from __future__ import annotations

import argparse
from pathlib import Path

import torch

from kodex_ai.model import KodexTransformer, ModelConfig
from kodex_ai.tokenizer import ByteBPETokenizer


def load_checkpoint(path: str, device: torch.device):
    checkpoint_path = Path(path)
    if not checkpoint_path.is_file():
        raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    config = ModelConfig(**checkpoint["model_config"])
    tokenizer = ByteBPETokenizer.from_dict(checkpoint["tokenizer"])
    if tokenizer.vocab_size != config.vocab_size:
        raise ValueError("Checkpoint model and tokenizer vocabulary sizes do not match")
    model = KodexTransformer(config).to(device)
    model.load_state_dict(checkpoint["model_state"])
    model.eval()
    return model, tokenizer, checkpoint


def parse_args():
    parser = argparse.ArgumentParser(description="Chat with a local Kodex checkpoint without an AI API.")
    parser.add_argument("--checkpoint", default="artifacts/kodex-ai-run/checkpoint_best.pt")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda", "mps"), default="auto")
    parser.add_argument("--max-new-tokens", type=int, default=128)
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--top-k", type=int, default=40)
    parser.add_argument("--history-turns", type=int, default=4)
    return parser.parse_args()


def choose_device(value: str) -> torch.device:
    if value == "cpu":
        return torch.device("cpu")
    if value == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA was requested but is unavailable")
        return torch.device("cuda")
    if value == "mps":
        if not (hasattr(torch.backends, "mps") and torch.backends.mps.is_available()):
            raise RuntimeError("MPS was requested but is unavailable")
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def main() -> int:
    args = parse_args()
    if args.max_new_tokens < 1 or args.history_turns < 0:
        raise ValueError("max-new-tokens must be positive and history-turns cannot be negative")
    device = choose_device(args.device)
    model, tokenizer, checkpoint = load_checkpoint(args.checkpoint, device)
    parameter_total = sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad)
    print(f"Kodex local neural chat | {parameter_total:,} parameters | step {checkpoint.get('step', 0)} | {device}")
    print("This experimental model can answer incoherently. Session context is temporary; no API is called.")
    history: list[tuple[str, str]] = []
    while True:
        try:
            message = input("\nVocê > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nEncerrando chat local.")
            break
        if not message:
            continue
        if message.casefold() in {"/sair", "/exit", "exit", "quit"}:
            break
        if message.casefold() in {"/limpar", "/reset"}:
            history.clear()
            print("Contexto temporário limpo.")
            continue
        parts = history[-args.history_turns:] if args.history_turns else []
        prompt = "".join(f"Usuário: {user}\nKodex: {answer}\n" for user, answer in parts)
        prompt += f"Usuário: {message}\nKodex:"
        token_ids = tokenizer.encode(prompt)
        token_ids = token_ids[-model.config.block_size:]
        input_tensor = torch.tensor([token_ids], dtype=torch.long, device=device)
        with torch.inference_mode():
            generated = model.generate(
                input_tensor,
                max_new_tokens=args.max_new_tokens,
                temperature=args.temperature,
                top_k=args.top_k,
            )
        answer = tokenizer.decode(generated[0, len(token_ids):].tolist()).strip()
        for stop_marker in ("\nUsuário:", "\nUser:"):
            if stop_marker in answer:
                answer = answer.split(stop_marker, 1)[0].strip()
        if not answer:
            answer = "[O modelo não gerou texto útil nesta tentativa.]"
        print(f"Kodex > {answer}")
        history.append((message, answer))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
