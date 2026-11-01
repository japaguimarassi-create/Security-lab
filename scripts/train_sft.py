import argparse
import json
from pathlib import Path
import yaml
import torch
from datasets import Dataset
from peft import LoraConfig
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import SFTConfig, SFTTrainer

def read_rows(path: Path):
    rows = []
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            row = json.loads(line)
            if not isinstance(row.get("messages"), list) or len(row["messages"]) < 2:
                raise ValueError(f"{path}:{line_number}: expected a messages array")
            rows.append(row)
    if len(rows) < 20:
        raise ValueError("SFT requires at least 20 reviewed conversations")
    return rows

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/training/sft.yaml"))
    args = parser.parse_args()
    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    source = Path(cfg["dataset_path"])
    if not source.is_file():
        raise SystemExit(f"Dataset not found: {source}")
    tokenizer = AutoTokenizer.from_pretrained(cfg["base_model"])
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    rows = read_rows(source)
    def format_row(row):
        return tokenizer.apply_chat_template(row["messages"], tokenize=False, add_generation_prompt=False)
    dataset = Dataset.from_dict({"text": [format_row(row) for row in rows]})
    split = dataset.train_test_split(test_size=float(cfg.get("validation_ratio", 0.05)), seed=int(cfg.get("seed", 42)))
    model = AutoModelForCausalLM.from_pretrained(cfg["base_model"], torch_dtype="auto")
    model.config.use_cache = False
    lora = cfg["lora"]
    peft = LoraConfig(r=int(lora["rank"]), lora_alpha=int(lora["alpha"]),
        lora_dropout=float(lora["dropout"]), target_modules=lora["target_modules"],
        task_type="CAUSAL_LM")
    use_cuda = torch.cuda.is_available()
    bf16 = bool(cfg.get("bf16", True) and use_cuda and torch.cuda.is_bf16_supported())
    train_args = SFTConfig(
        output_dir=cfg["output_dir"], dataset_text_field="text",
        max_length=int(cfg["max_sequence_length"]), packing=bool(cfg.get("packing", False)),
        max_steps=int(cfg["max_steps"]), learning_rate=float(cfg["learning_rate"]),
        warmup_ratio=float(cfg.get("warmup_ratio", 0.03)),
        per_device_train_batch_size=int(cfg["per_device_train_batch_size"]),
        per_device_eval_batch_size=int(cfg.get("per_device_eval_batch_size", 1)),
        gradient_accumulation_steps=int(cfg["gradient_accumulation_steps"]),
        eval_strategy="steps", eval_steps=int(cfg.get("eval_steps", 200)),
        save_strategy="steps", save_steps=int(cfg["save_steps"]),
        save_total_limit=int(cfg["save_total_limit"]), bf16=bf16,
        fp16=bool(cfg.get("fp16", False) and use_cuda and not bf16),
        gradient_checkpointing=True, report_to="none", seed=int(cfg.get("seed", 42))
    )
    trainer = SFTTrainer(
        model=model, args=train_args, train_dataset=split["train"],
        eval_dataset=split["test"], processing_class=tokenizer, peft_config=peft
    )
    trainer.train()
    trainer.evaluate()
    trainer.save_model(cfg["output_dir"])
    tokenizer.save_pretrained(cfg["output_dir"])
    print(f"SFT adapter saved to {cfg['output_dir']}")

if __name__ == "__main__":
    main()
