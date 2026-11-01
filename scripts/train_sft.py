import argparse
import json
from pathlib import Path

import yaml
from datasets import Dataset
from peft import LoraConfig, PeftModel
from transformers import AutoTokenizer
from trl import SFTConfig, SFTTrainer

from klod.distillation import read_sft_rows
from klod.training import load_training_model


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/training/sft.yaml"))
    args = parser.parse_args()
    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    source = Path(cfg["dataset_path"])
    if not source.is_file():
        raise SystemExit(f"Dataset not found: {source}")
    rows = read_sft_rows(
        source,
        minimum=int(cfg.get("minimum_examples", 20)),
        require_approval=bool(cfg.get("require_approval", False)),
    )
    tokenizer = AutoTokenizer.from_pretrained(cfg["base_model"])
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    dataset = Dataset.from_list(rows)
    split = dataset.train_test_split(test_size=float(cfg.get("validation_ratio", 0.05)),
                                     seed=int(cfg.get("seed", 42)))
    model, precision = load_training_model(
        cfg["base_model"], bool(cfg.get("load_in_4bit", True)), True)
    previous_adapter = cfg.get("previous_adapter")
    peft_config = None
    if previous_adapter:
        if not Path(previous_adapter).is_dir():
            raise SystemExit(f"Previous LoRA adapter not found: {previous_adapter}")
        model = PeftModel.from_pretrained(model, previous_adapter, is_trainable=True)
    else:
        lora = cfg["lora"]
        peft_config = LoraConfig(r=int(lora["rank"]), lora_alpha=int(lora["alpha"]),
            lora_dropout=float(lora["dropout"]), target_modules=lora["target_modules"],
            task_type="CAUSAL_LM")
    train_args = SFTConfig(
        output_dir=cfg["output_dir"], max_length=int(cfg["max_sequence_length"]),
        packing=bool(cfg.get("packing", False)), assistant_only_loss=True,
        max_steps=int(cfg.get("max_steps", -1)),
        num_train_epochs=float(cfg.get("num_train_epochs", 3)),
        learning_rate=float(cfg["learning_rate"]),
        warmup_ratio=float(cfg.get("warmup_ratio", 0.03)),
        per_device_train_batch_size=int(cfg["per_device_train_batch_size"]),
        per_device_eval_batch_size=int(cfg.get("per_device_eval_batch_size", 1)),
        gradient_accumulation_steps=int(cfg["gradient_accumulation_steps"]),
        eval_strategy=cfg.get("eval_strategy", "steps"),
        eval_steps=int(cfg.get("eval_steps", 200)),
        save_strategy=cfg.get("save_strategy", "steps"),
        save_steps=int(cfg.get("save_steps", 200)),
        save_total_limit=int(cfg["save_total_limit"]),
        bf16=precision["bf16"], fp16=bool(precision["cuda"] and not precision["bf16"]),
        use_cpu=not precision["cuda"], optim=cfg.get("optim", "adamw_torch"),
        dataloader_pin_memory=bool(precision["cuda"]), dataloader_num_workers=0,
        gradient_checkpointing=True, report_to="none", seed=int(cfg.get("seed", 42)))
    trainer_kwargs = {
        "model": model, "args": train_args, "train_dataset": split["train"],
        "eval_dataset": split["test"], "processing_class": tokenizer
    }
    if peft_config is not None:
        trainer_kwargs["peft_config"] = peft_config
    trainer = SFTTrainer(**trainer_kwargs)
    trainer.train()
    metrics = trainer.evaluate()
    trainer.save_model(cfg["output_dir"])
    tokenizer.save_pretrained(cfg["output_dir"])
    metrics_payload = {
        "base_model": cfg["base_model"],
        "adapter_path": cfg["output_dir"],
        "training_examples": len(rows),
        "train_examples": len(split["train"]),
        "validation_examples": len(split["test"]),
        "global_step": int(trainer.state.global_step),
        "precision": precision,
        "evaluation_metrics": metrics,
    }
    metrics_path = Path(cfg["output_dir"]) / "training_metrics.json"
    metrics_path.write_text(
        json.dumps(metrics_payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print({"saved_to": cfg["output_dir"], "metrics_file": str(metrics_path),
           "training_examples": len(rows), "evaluation": metrics})


if __name__ == "__main__":
    main()
