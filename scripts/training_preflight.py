import argparse
import importlib.util
import json
from pathlib import Path
import yaml

REQUIREMENTS = {
    "pretrain": ("data/processed/mixture.jsonl", 20, {"text"}, "configs/training/continued_pretraining.yaml"),
    "sft": ("data/processed/sft.jsonl", 20, {"messages"}, "configs/training/sft.yaml"),
    "dpo": ("data/processed/preferences.jsonl", 100, {"prompt", "chosen", "rejected"}, "configs/training/dpo.yaml")
}

def inspect_dataset(path: Path, required_fields: set[str], minimum: int):
    if not path.is_file():
        return {"exists": False, "rows": 0, "valid": False, "reason": f"Missing {path}"}
    rows = valid = invalid = 0
    with path.open(encoding="utf-8") as source:
        for line in source:
            if not line.strip():
                continue
            rows += 1
            try:
                item = json.loads(line)
                if required_fields.issubset(item.keys()):
                    valid += 1
                else:
                    invalid += 1
            except (ValueError, TypeError):
                invalid += 1
    return {"exists": True, "rows": rows, "valid_rows": valid,
            "invalid_rows": invalid, "valid": valid >= minimum and invalid == 0,
            "minimum_rows": minimum}

def inspect_gpu():
    try:
        import torch
    except ImportError:
        return {"available": False, "reason": "PyTorch is not installed"}
    if not torch.cuda.is_available():
        return {"available": False, "reason": "CUDA GPU not detected", "torch": torch.__version__}
    device = torch.cuda.get_device_properties(0)
    return {"available": True, "name": device.name,
            "vram_gib": round(device.total_memory / (1024 ** 3), 2),
            "bf16": bool(torch.cuda.is_bf16_supported()), "torch": torch.__version__}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=REQUIREMENTS, required=True)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()
    default_dataset, minimum, fields, default_config = REQUIREMENTS[args.stage]
    config_path = args.config or Path(default_config)
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    dataset = inspect_dataset(args.dataset or Path(cfg.get("dataset_path", default_dataset)), fields, minimum)
    gpu = inspect_gpu()
    quantized = bool(cfg.get("load_in_4bit", False))
    bnb_available = importlib.util.find_spec("bitsandbytes") is not None
    issues = []
    if not gpu["available"]:
        issues.append("A CUDA GPU is required for this 1.7B QLoRA training configuration.")
    if quantized and not bnb_available:
        issues.append("Install bitsandbytes for the configured 4-bit QLoRA training.")
    if quantized and gpu["available"] and gpu.get("vram_gib", 0) < 12:
        issues.append("GPU has less than 12 GiB VRAM; reduce sequence length/batch or use a larger GPU.")
    if not dataset["valid"]:
        issues.append("Dataset is missing, malformed or below the minimum reviewed row count.")
    result = {"stage": args.stage, "dataset": dataset, "gpu": gpu,
              "qlora_4bit": quantized, "bitsandbytes_installed": bnb_available,
              "ready": not issues, "issues": issues}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if issues:
        raise SystemExit(2)

if __name__ == "__main__":
    main()
