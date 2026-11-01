import argparse
import json
import os
import resource
from pathlib import Path

os.environ["KLOD_FORCE_CPU"] = "1"

import torch
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="Qwen/Qwen3-1.7B-Base")
    parser.add_argument("--output", type=Path, default=Path("outputs/cpu-smoke-adapter"))
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()

    torch.set_num_threads(max(1, args.threads))
    if torch.cuda.is_available():
        raise SystemExit("CPU smoke test must use a CPU-only PyTorch runtime.")

    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=False)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        torch_dtype=torch.float32,
        low_cpu_mem_usage=True,
        attn_implementation="eager",
        trust_remote_code=False,
    )
    model.config.use_cache = False
    model.gradient_checkpointing_enable()
    if hasattr(model, "enable_input_require_grads"):
        model.enable_input_require_grads()

    model = get_peft_model(
        model,
        LoraConfig(
            r=8,
            lora_alpha=16,
            lora_dropout=0.05,
            target_modules=[
                "q_proj",
                "k_proj",
                "v_proj",
                "o_proj",
                "gate_proj",
                "up_proj",
                "down_proj",
            ],
            task_type="CAUSAL_LM",
        ),
    )
    model.train()

    batch = tokenizer(
        "Explain why testing a program with small examples helps detect errors.",
        return_tensors="pt",
        truncation=True,
        max_length=128,
    )
    labels = batch["input_ids"].clone()
    optimizer = torch.optim.AdamW(
        [parameter for parameter in model.parameters() if parameter.requires_grad],
        lr=2e-5,
    )
    optimizer.zero_grad(set_to_none=True)
    result = model(**batch, labels=labels)
    if not torch.isfinite(result.loss):
        raise SystemExit("CPU smoke test produced a non-finite loss.")
    result.loss.backward()
    optimizer.step()

    args.output.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(args.output)
    tokenizer.save_pretrained(args.output)
    payload = {
        "model": args.model,
        "device": "cpu",
        "dtype": "float32",
        "cuda_available": False,
        "trainable_parameters": sum(
            parameter.numel() for parameter in model.parameters()
            if parameter.requires_grad
        ),
        "loss": float(result.loss.detach()),
        "peak_rss_mib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
        "adapter_path": str(args.output),
        "optimizer_step_completed": True,
    }
    (args.output / "cpu-smoke.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
