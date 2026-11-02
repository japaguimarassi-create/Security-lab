import argparse
from pathlib import Path
import yaml
from datasets import load_dataset
from peft import LoraConfig, PeftModel
from transformers import AutoTokenizer
from trl import DPOConfig, DPOTrainer
from klod.training import load_training_model

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/training/dpo.yaml"))
    args = parser.parse_args()
    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    path = Path(cfg["dataset_path"])
    if not path.is_file():
        raise SystemExit(f"Dataset not found: {path}")
    dataset = load_dataset("json", data_files=str(path), split="train")
    if not {"prompt", "chosen", "rejected"}.issubset(dataset.column_names):
        raise SystemExit("DPO JSONL rows must contain prompt, chosen and rejected")
    if len(dataset) < 100:
        raise SystemExit("DPO requires at least 100 human-reviewed preference pairs")
    split = dataset.train_test_split(test_size=float(cfg.get("validation_ratio", 0.05)),
                                     seed=int(cfg.get("seed", 42)))
    tokenizer = AutoTokenizer.from_pretrained(cfg["base_model"])
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "left"
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
    train_args = DPOConfig(
        output_dir=cfg["output_dir"], beta=float(cfg.get("beta", 0.1)),
        max_length=int(cfg["max_sequence_length"]),
        max_prompt_length=int(cfg.get("max_prompt_length", 2048)),
        max_steps=int(cfg["max_steps"]), learning_rate=float(cfg["learning_rate"]),
        per_device_train_batch_size=int(cfg["per_device_train_batch_size"]),
        per_device_eval_batch_size=int(cfg.get("per_device_eval_batch_size", 1)),
        gradient_accumulation_steps=int(cfg["gradient_accumulation_steps"]),
        eval_strategy="steps", eval_steps=int(cfg.get("eval_steps", 100)),
        save_strategy="steps", save_steps=int(cfg["save_steps"]),
        save_total_limit=int(cfg["save_total_limit"]),
        bf16=precision["bf16"], fp16=bool(precision["cuda"] and not precision["bf16"]),
        gradient_checkpointing=True, report_to="none", seed=int(cfg.get("seed", 42)))
    trainer_kwargs = {
        "model": model, "args": train_args, "train_dataset": split["train"],
        "eval_dataset": split["test"], "processing_class": tokenizer
    }
    if peft_config is not None:
        trainer_kwargs["peft_config"] = peft_config
    trainer = DPOTrainer(**trainer_kwargs)
    trainer.train()
    metrics = trainer.evaluate()
    trainer.save_model(cfg["output_dir"])
    tokenizer.save_pretrained(cfg["output_dir"])
    print({"saved_to": cfg["output_dir"], "evaluation": metrics})

if __name__ == "__main__":
    main()
