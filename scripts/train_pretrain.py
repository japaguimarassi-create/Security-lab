import argparse
from pathlib import Path
import yaml
import torch
from datasets import load_dataset
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments, DataCollatorForLanguageModeling

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/training/continued_pretraining.yaml"))
    args = parser.parse_args()
    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    data_path = Path(cfg["dataset_path"])
    if not data_path.exists():
        raise SystemExit(f"Dataset not found: {data_path}")
    tokenizer = AutoTokenizer.from_pretrained(cfg["base_model"])
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(cfg["base_model"], torch_dtype="auto")
    model.gradient_checkpointing_enable()
    model.config.use_cache = False
    lora = cfg["lora"]
    model = get_peft_model(model, LoraConfig(
        r=lora["rank"], lora_alpha=lora["alpha"], lora_dropout=lora["dropout"],
        target_modules=lora["target_modules"], task_type="CAUSAL_LM"))
    dataset = load_dataset("json", data_files=str(data_path), split="train")
    length = int(cfg["max_sequence_length"])
    def tokenize(batch):
        return tokenizer(batch["text"], truncation=True, max_length=length)
    tokenized = dataset.map(tokenize, batched=True, remove_columns=dataset.column_names)
    cuda = torch.cuda.is_available()
    bf16 = bool(cfg["bf16"] and cuda and torch.cuda.is_bf16_supported())
    training_args = TrainingArguments(
        output_dir=cfg["output_dir"], max_steps=cfg["max_steps"],
        learning_rate=cfg["learning_rate"], warmup_ratio=cfg["warmup_ratio"],
        weight_decay=cfg["weight_decay"],
        per_device_train_batch_size=cfg["per_device_train_batch_size"],
        gradient_accumulation_steps=cfg["gradient_accumulation_steps"],
        logging_steps=cfg["logging_steps"], save_steps=cfg["save_steps"],
        save_total_limit=cfg["save_total_limit"], bf16=bf16,
        fp16=bool(cfg["fp16"] and cuda and not bf16),
        gradient_checkpointing=True, report_to=["tensorboard"])
    trainer = Trainer(model=model, args=training_args, train_dataset=tokenized,
        data_collator=DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False),
        processing_class=tokenizer)
    trainer.train()
    model.save_pretrained(cfg["output_dir"], safe_serialization=True)
    tokenizer.save_pretrained(cfg["output_dir"])

if __name__ == "__main__":
    main()
