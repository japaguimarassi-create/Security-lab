import json
import os
import resource
import subprocess
import sys
from pathlib import Path

os.environ["KLOD_FORCE_CPU"] = "1"
os.environ["KLOD_CPU_THREADS"] = "4"

import torch
import yaml


def main():
    torch.set_num_threads(4)
    if torch.cuda.is_available():
        raise SystemExit("CPU smoke test must use a CPU-only PyTorch runtime.")

    dataset = Path("data/generated/cpu_smoke.jsonl")
    dataset.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for index in range(20):
        rows.append({
            "id": f"cpu-smoke-{index + 1:03d}",
            "approved": True,
            "quality_passed": True,
            "messages": [
                {"role": "system", "content": "You are a concise and accurate assistant."},
                {"role": "user", "content": f"Give one practical reason to test software. Example {index + 1}."},
                {"role": "assistant", "content": f"Testing software helps detect defects before users encounter them. Example {index + 1}."},
            ],
        })
    dataset.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\\n" for row in rows),
        encoding="utf-8",
    )

    config = {
        "base_model": "Qwen/Qwen3-1.7B-Base",
        "previous_adapter": None,
        "dataset_path": str(dataset),
        "require_approval": True,
        "minimum_examples": 20,
        "require_cuda": False,
        "output_dir": "outputs/cpu-smoke-adapter",
        "max_sequence_length": 96,
        "num_train_epochs": 1,
        "max_steps": 1,
        "learning_rate": 0.00002,
        "warmup_ratio": 0.0,
        "per_device_train_batch_size": 1,
        "per_device_eval_batch_size": 1,
        "gradient_accumulation_steps": 1,
        "validation_ratio": 0.1,
        "eval_strategy": "no",
        "save_strategy": "no",
        "save_total_limit": 1,
        "load_in_4bit": False,
        "bf16": False,
        "fp16": False,
        "packing": False,
        "optim": "adamw_torch",
        "seed": 42,
        "lora": {
            "rank": 8,
            "alpha": 16,
            "dropout": 0.05,
            "target_modules": [
                "q_proj",
                "k_proj",
                "v_proj",
                "o_proj",
                "gate_proj",
                "up_proj",
                "down_proj",
            ],
        },
    }
    config_path = Path("configs/training/cpu_smoke.yaml")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    subprocess.run(
        [sys.executable, "scripts/train_sft.py", "--config", str(config_path)],
        check=True,
        env=os.environ.copy(),
    )

    adapter = Path(config["output_dir"])
    required = ("adapter_config.json", "training_metrics.json")
    for name in required:
        if not (adapter / name).is_file():
            raise SystemExit(f"CPU smoke test did not create {name}.")
    if not any((adapter / name).is_file() for name in ("adapter_model.safetensors", "adapter_model.bin")):
        raise SystemExit("CPU smoke test did not save LoRA weights.")

    metrics = json.loads((adapter / "training_metrics.json").read_text(encoding="utf-8"))
    payload = {
        "model": config["base_model"],
        "device": "cpu",
        "dtype": "float32",
        "cuda_available": False,
        "training_examples": metrics["training_examples"],
        "global_step": metrics["global_step"],
        "precision": metrics["precision"],
        "peak_rss_mib": round(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024, 1),
        "adapter_path": str(adapter),
        "trainer": "scripts/train_sft.py",
        "optimizer_step_completed": metrics["global_step"] >= 1,
    }
    if not payload["optimizer_step_completed"]:
        raise SystemExit("The CPU SFTTrainer did not complete an optimizer step.")
    (adapter / "cpu-smoke.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
