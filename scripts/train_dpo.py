import argparse
from pathlib import Path
import yaml
import torch
from datasets import load_dataset
from peft import LoraConfig
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import DPOConfig, DPOTrainer

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/training/dpo.yaml"))
    args = parser.parse_args()
    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    path = Path(cfg["dataset_path"])
    if not path.is_file():
        raise SystemExit(f"Dataset not found: {path}")
    dataset = load_dataset("json", data_files=str(path), split="train")
    required = {"prompt", "chosen", "rejected"}
    if not required.issubset(dataset.column_names):
        raise SystemExit("DPO JSONL rows must contain prompt, chosen and rejected")
    if len(dataset) < 100:
        raise SystemExit("DPO requires at least 100 reviewed preference pairs")
    split = dataset.train_test_split(test_size=float(cfg.get("validation_ratio", 0.05)), seed=int(cfg.get("seed", 42)))
    tokenizer = AutoTokenizer.from_pretrained(cfg["base_model"])
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "left"
    model = AutoModelForCausalLM.from_pretrained(cfg["base_model"], torch_dtype="auto")
    lora = cfg["lora"]
    peft = LoraConfig(r=int(lora["rank"]), lora_alpha=int(lora["alpha"]),
        lora_dropout=float(lora["dropout"]), target_modules=lora["target_modules"],
        task_type="CAUSAL_LM")
    use_cuda = torch.cuda.is_available()
    bf16 = bool(cfg.get("bf16", True) and use_cuda and torch.cuda.is_bf16_supported())
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
        save_total_limit=int(cfg["save_total_limit"]), bf16=bf16,
        fp16=bool(cfg.get("fp16", False) and use_cuda and not bf16),
        gradient_checkpointing=True, report_to="none", seed=int(cfg.get("seed", 42))
    )
    trainer = DPOTrainer(
        model=model, args=train_args, train_dataset=split["train"],
        eval_dataset=split["test"], processing_class=tokenizer, peft_config=peft
    )
    trainer.train()
    trainer.evaluate()
    trainer.save_model(cfg["output_dir"])
    tokenizer.save_pretrained(cfg["output_dir"])
    print(f"DPO adapter saved to {cfg['output_dir']}")

if __name__ == "__main__":
    main()
