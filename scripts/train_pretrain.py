import argparse
from pathlib import Path
import yaml
from datasets import load_dataset
from peft import LoraConfig, get_peft_model
from transformers import AutoTokenizer, Trainer, TrainingArguments, DataCollatorForLanguageModeling
from klod.training import load_training_model

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/training/continued_pretraining.yaml"))
    args = parser.parse_args()
    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    data_path = Path(cfg["dataset_path"])
    if not data_path.is_file():
        raise SystemExit(f"Dataset not found: {data_path}")
    raw = load_dataset("json", data_files=str(data_path), split="train")
    if len(raw) < 20:
        raise SystemExit("At least 20 approved documents are required for training")
    split = raw.train_test_split(test_size=float(cfg.get("validation_ratio", 0.02)),
                                 seed=int(cfg.get("seed", 42)))
    tokenizer = AutoTokenizer.from_pretrained(cfg["base_model"])
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model, precision = load_training_model(
        cfg["base_model"], bool(cfg.get("load_in_4bit", True)),
        bool(cfg.get("gradient_checkpointing", True)))
    if cfg.get("use_lora", True):
        lora = cfg["lora"]
        model = get_peft_model(model, LoraConfig(
            r=int(lora["rank"]), lora_alpha=int(lora["alpha"]),
            lora_dropout=float(lora["dropout"]),
            target_modules=lora["target_modules"], task_type="CAUSAL_LM"))
        model.print_trainable_parameters()

    max_length = int(cfg["max_sequence_length"])
    def tokenize(batch):
        return tokenizer(batch["text"], truncation=False, add_special_tokens=False)
    tokenized = split.map(tokenize, batched=True, remove_columns=split["train"].column_names)

    def pack(batch):
        joined = {key: sum(batch[key], []) for key in batch.keys()}
        total = (len(joined["input_ids"]) // max_length) * max_length
        return {key: [values[i:i + max_length] for i in range(0, total, max_length)]
                for key, values in joined.items()}

    packed = tokenized.map(pack, batched=True, batch_size=1000)
    if len(packed["train"]) == 0 or len(packed["test"]) == 0:
        raise SystemExit("Not enough tokens to create packed training and validation sequences")
    train_args = TrainingArguments(
        output_dir=cfg["output_dir"], max_steps=int(cfg["max_steps"]),
        learning_rate=float(cfg["learning_rate"]),
        warmup_ratio=float(cfg.get("warmup_ratio", 0.03)),
        weight_decay=float(cfg.get("weight_decay", 0.1)),
        per_device_train_batch_size=int(cfg["per_device_train_batch_size"]),
        per_device_eval_batch_size=int(cfg.get("per_device_eval_batch_size", 1)),
        gradient_accumulation_steps=int(cfg["gradient_accumulation_steps"]),
        logging_steps=int(cfg.get("logging_steps", 10)),
        eval_strategy="steps", eval_steps=int(cfg.get("eval_steps", 200)),
        save_strategy="steps", save_steps=int(cfg["save_steps"]),
        save_total_limit=int(cfg["save_total_limit"]),
        bf16=precision["bf16"], fp16=bool(precision["cuda"] and not precision["bf16"]),
        gradient_checkpointing=bool(cfg.get("gradient_checkpointing", True)),
        report_to="none", seed=int(cfg.get("seed", 42)))
    trainer = Trainer(model=model, args=train_args,
        train_dataset=packed["train"], eval_dataset=packed["test"],
        data_collator=DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False),
        processing_class=tokenizer)
    trainer.train()
    metrics = trainer.evaluate()
    trainer.save_model(cfg["output_dir"])
    tokenizer.save_pretrained(cfg["output_dir"])
    print({"saved_to": cfg["output_dir"], "evaluation": metrics})

if __name__ == "__main__":
    main()
