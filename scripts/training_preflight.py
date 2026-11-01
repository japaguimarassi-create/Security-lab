import argparse
import importlib.util
import json
from pathlib import Path

import yaml

from klod.distillation import validate_sft_messages


REQUIREMENTS = {
    "teacher": ("configs/distillation_prompts.jsonl", 20,
                {"prompt", "domain", "language"}, "configs/training/distillation.yaml"),
    "pretrain": ("data/processed/mixture.jsonl", 20, {"text"},
                 "configs/training/continued_pretraining.yaml"),
    "sft": ("data/processed/sft.jsonl", 20, {"messages"},
            "configs/training/sft.yaml"),
    "dpo": ("data/processed/preferences.jsonl", 100,
            {"prompt", "chosen", "rejected"}, "configs/training/dpo.yaml"),
}


def validate_record(item: object, stage: str | None = None,
                    require_approval: bool = False) -> str | None:
    if not isinstance(item, dict):
        return "expected a JSON object"
    required = REQUIREMENTS[stage][2] if stage else set()
    missing = sorted(required.difference(item))
    if missing:
        return "missing fields: " + ", ".join(missing)
    if require_approval and (
        item.get("approved") is not True or item.get("quality_passed") is not True
    ):
        return "teacher example is not both approved and quality-screened"
    if stage == "teacher":
        for field in ("prompt", "domain", "language"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                return f"{field} must be non-empty text"
    elif stage == "pretrain":
        if not isinstance(item.get("text"), str) or not item["text"].strip():
            return "text must be non-empty"
    elif stage == "sft":
        return validate_sft_messages(item.get("messages"))
    elif stage == "dpo":
        for field in ("prompt", "chosen", "rejected"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                return f"{field} must be non-empty text"
        if item["chosen"].strip() == item["rejected"].strip():
            return "chosen and rejected responses must differ"
    return None


def inspect_dataset(path: Path, required_fields: set[str], minimum: int,
                    require_approval: bool = False, stage: str | None = None):
    if not path.is_file():
        return {"exists": False, "rows": 0, "valid": False,
                "reason": f"Missing {path}"}
    rows = valid = invalid = unapproved = 0
    invalid_examples = []
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            rows += 1
            try:
                item = json.loads(line)
                reason = validate_record(item, stage, require_approval)
                if reason is None and not required_fields.issubset(item):
                    reason = "required fields are missing"
                if reason is None:
                    valid += 1
                else:
                    invalid += 1
                    if require_approval and isinstance(item, dict) and (
                        item.get("approved") is not True or item.get("quality_passed") is not True
                    ):
                        unapproved += 1
                    if len(invalid_examples) < 5:
                        invalid_examples.append({
                            "line": line_number,
                            "reason": reason,
                        })
            except json.JSONDecodeError:
                invalid += 1
                if len(invalid_examples) < 5:
                    invalid_examples.append({
                        "line": line_number,
                        "reason": "invalid JSON",
                    })
    return {
        "exists": True,
        "rows": rows,
        "valid_rows": valid,
        "invalid_rows": invalid,
        "unapproved_rows": unapproved,
        "invalid_examples": invalid_examples,
        "valid": valid >= minimum and invalid == 0,
        "minimum_rows": minimum,
        "approval_required": require_approval,
    }


def inspect_gpu():
    try:
        import torch
    except ImportError:
        return {"available": False, "reason": "PyTorch is not installed"}
    if not torch.cuda.is_available():
        return {"available": False, "reason": "CUDA GPU not detected",
                "torch": torch.__version__}
    device = torch.cuda.get_device_properties(0)
    return {
        "available": True,
        "name": device.name,
        "vram_gib": round(device.total_memory / (1024 ** 3), 2),
        "bf16": bool(torch.cuda.is_bf16_supported()),
        "torch": torch.__version__,
        "visible_gpus": torch.cuda.device_count(),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=REQUIREMENTS, required=True)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()

    default_dataset, minimum, fields, default_config = REQUIREMENTS[args.stage]
    config_path = args.config or Path(default_config)
    if not config_path.is_file():
        raise SystemExit(f"Training config not found: {config_path}")
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(cfg, dict):
        raise SystemExit(f"Training config must be a YAML object: {config_path}")
    configured_dataset = (
        cfg.get("seed_prompts_path", default_dataset)
        if args.stage == "teacher"
        else cfg.get("dataset_path", default_dataset)
    )
    dataset = inspect_dataset(
        args.dataset or Path(configured_dataset),
        fields,
        minimum,
        require_approval=bool(cfg.get("require_approval", False)),
        stage=args.stage,
    )
    gpu = inspect_gpu()
    quantized = bool(cfg.get("load_in_4bit", False))
    bnb_available = importlib.util.find_spec("bitsandbytes") is not None
    issues = []

    cuda_required = args.stage != "teacher" or bool(cfg.get("require_cuda", True))
    if cuda_required and not gpu["available"]:
        issues.append("A CUDA GPU is required by this training configuration.")
    if quantized and not bnb_available:
        issues.append("Install bitsandbytes for the configured 4-bit QLoRA stage.")
    if quantized and gpu["available"] and gpu.get("vram_gib", 0) < 12:
        issues.append("GPU has less than 12 GiB VRAM; reduce sequence length/batch or use a larger GPU.")
    if not dataset["valid"]:
        issues.append("Dataset is missing, malformed, unapproved or below the minimum row count.")

    result = {
        "stage": args.stage,
        "dataset": dataset,
        "gpu": gpu,
        "qlora_4bit": quantized,
        "bitsandbytes_installed": bnb_available,
        "teacher_model": cfg.get("teacher_model") if args.stage == "teacher" else None,
        "ready": not issues,
        "issues": issues,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if issues:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
