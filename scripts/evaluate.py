import argparse
import json
import math
from pathlib import Path
import torch
from datasets import load_dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments, DataCollatorForLanguageModeling

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("evaluation/results.json"))
    parser.add_argument("--max-length", type=int, default=2048)
    args = parser.parse_args()
    if not args.dataset.is_file():
        raise SystemExit(f"Evaluation dataset not found: {args.dataset}")
    data = load_dataset("json", data_files=str(args.dataset), split="train")
    if len(data) < 5:
        raise SystemExit("Evaluation requires at least five held-out examples")
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForCausalLM.from_pretrained(args.model, torch_dtype="auto")
    def tokenize(batch):
        return tokenizer(batch["text"], truncation=True, max_length=args.max_length)
    tokenized = data.map(tokenize, batched=True, remove_columns=data.column_names)
    training_args = TrainingArguments(output_dir="outputs/eval-temp",
        per_device_eval_batch_size=1, report_to="none", do_train=False,
        do_eval=True, fp16=torch.cuda.is_available())
    trainer = Trainer(model=model, args=training_args, eval_dataset=tokenized,
        data_collator=DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False),
        processing_class=tokenizer)
    metrics = trainer.evaluate()
    loss = float(metrics["eval_loss"])
    result = {"model": args.model, "examples": len(data), "eval_loss": loss,
              "perplexity": math.exp(min(loss, 20)), "metrics": metrics}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
