import argparse
import json
from pathlib import Path

REQUIREMENTS = {
    "pretrain": ("data/processed/pretrain.jsonl", 20, {"text"}),
    "sft": ("data/processed/sft.jsonl", 20, {"messages"}),
    "dpo": ("data/processed/preferences.jsonl", 100, {"prompt", "chosen", "rejected"})
}

def inspect_dataset(path: Path, required_fields: set[str], minimum: int):
    if not path.is_file():
        return {"exists": False, "rows": 0, "valid": False, "reason": f"Missing {path}"}
    rows = valid = 0
    bad = 0
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
                    bad += 1
            except (ValueError, TypeError):
                bad += 1
    return {
        "exists": True, "rows": rows, "valid_rows": valid,
        "invalid_rows": bad, "valid": valid >= minimum and bad == 0,
        "minimum_rows": minimum
    }

def inspect_gpu():
    try:
        import torch
    except ImportError:
        return {"available": False, "reason": "PyTorch is not installed"}
    if not torch.cuda.is_available():
        return {"available": False, "reason": "CUDA GPU not detected", "torch": torch.__version__}
    device = torch.cuda.get_device_properties(0)
    return {
        "available": True, "name": device.name,
        "vram_gib": round(device.total_memory / (1024 ** 3), 2),
        "bf16": bool(torch.cuda.is_bf16_supported()),
        "torch": torch.__version__
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=REQUIREMENTS, required=True)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--require-gpu", action="store_true")
    args = parser.parse_args()
    default_path, minimum, fields = REQUIREMENTS[args.stage]
    dataset = inspect_dataset(args.dataset or Path(default_path), fields, minimum)
    gpu = inspect_gpu()
    ready = dataset["valid"] and (gpu["available"] or not args.require_gpu)
    result = {"stage": args.stage, "dataset": dataset, "gpu": gpu, "ready": ready}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not ready:
        raise SystemExit(2)

if __name__ == "__main__":
    main()
