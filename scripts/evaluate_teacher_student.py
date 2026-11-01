import argparse
import gc
import json
import random
from pathlib import Path

import yaml

from klod.specialists import GENERAL_SYSTEM_PROMPT
from klod.training import inference_dtype_name


def read_eval_prompts(path: Path, limit: int | None = None) -> list[dict]:
    rows = []
    seen = set()
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: expected an object")
            prompt = row.get("prompt")
            if not isinstance(prompt, str) or not prompt.strip():
                raise ValueError(f"{path}:{line_number}: prompt must be non-empty")
            key = prompt.casefold().strip()
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "id": str(row.get("id") or f"eval-{line_number:05d}"),
                "domain": str(row.get("domain") or "general"),
                "language": str(row.get("language") or "pt"),
                "prompt": prompt.strip(),
            })
            if limit is not None and len(rows) >= limit:
                break
    if len(rows) < 5:
        raise ValueError("At least five unique held-out prompts are required")
    return rows


def _generate(model, tokenizer, prompts: list[dict], cfg: dict) -> list[str]:
    import torch

    answers = []
    for index, row in enumerate(prompts, 1):
        messages = [
            {"role": "system", "content": GENERAL_SYSTEM_PROMPT},
            {"role": "user", "content": row["prompt"]},
        ]
        try:
            rendered = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True,
                enable_thinking=False)
        except TypeError:
            rendered = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(
            rendered, return_tensors="pt", truncation=True,
            max_length=int(cfg["max_input_tokens"]))
        device = model.get_input_embeddings().weight.device
        inputs = {key: value.to(device) if hasattr(value, "to") else value
                  for key, value in inputs.items()}
        generation = {
            "max_new_tokens": int(cfg["max_new_tokens"]),
            "do_sample": False,
            "repetition_penalty": float(cfg.get("repetition_penalty", 1.05)),
            "pad_token_id": tokenizer.pad_token_id,
            "eos_token_id": tokenizer.eos_token_id,
        }
        with torch.inference_mode():
            output = model.generate(**inputs, **generation)
        input_length = int(inputs["input_ids"].shape[-1])
        answer = tokenizer.decode(
            output[0][input_length:], skip_special_tokens=True).strip()
        answers.append(answer)
        print(f"Generated {index}/{len(prompts)}")
    return answers


def run_checkpoint(model_id: str, adapter: str | None,
                   prompts: list[dict], cfg: dict) -> list[str]:
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=False)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    cuda_available = torch.cuda.is_available()
    bf16_supported = cuda_available and torch.cuda.is_bf16_supported()
    dtype_name = inference_dtype_name(cuda_available, bf16_supported)
    model = AutoModelForCausalLM.from_pretrained(
        model_id, torch_dtype=getattr(torch, dtype_name),
        device_map=cfg.get("device_map", "auto"),
        low_cpu_mem_usage=True, trust_remote_code=False)
    if adapter:
        adapter_path = Path(adapter)
        if not adapter_path.is_dir():
            raise FileNotFoundError(f"Student adapter does not exist: {adapter_path}")
        model = PeftModel.from_pretrained(model, str(adapter_path), is_trainable=False)
    model.eval()
    answers = _generate(model, tokenizer, prompts, cfg)
    del model, tokenizer
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return answers


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/training/distillation_eval.yaml"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    prompt_path = Path(cfg["heldout_prompts_path"])
    output_path = Path(cfg["blind_output_path"])
    key_path = Path(cfg["answer_key_path"])
    if not prompt_path.is_file():
        raise SystemExit(f"Held-out prompts not found: {prompt_path}")
    for target in (output_path, key_path):
        if target.exists() and not args.overwrite:
            raise SystemExit(f"{target} already exists; pass --overwrite to replace it")
    if not cfg.get("student_adapter") or not Path(cfg["student_adapter"]).is_dir():
        raise SystemExit("Train the student adapter before running teacher/student evaluation.")

    prompts = read_eval_prompts(prompt_path, args.limit)
    seed = int(cfg.get("seed", 42))
    import torch
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

    print("Loading frozen teacher:", cfg["teacher_model"])
    teacher_answers = run_checkpoint(
        cfg["teacher_model"], None, prompts, cfg)
    print("Loading trained student:", cfg["student_base_model"])
    student_answers = run_checkpoint(
        cfg["student_base_model"], cfg["student_adapter"], prompts, cfg)

    rng = random.Random(seed)
    comparisons = []
    answer_key = []
    for row, teacher_answer, student_answer in zip(
            prompts, teacher_answers, student_answers):
        if rng.random() < 0.5:
            answer_a, answer_b = teacher_answer, student_answer
            mapping = {"answer_a": "teacher", "answer_b": "student"}
        else:
            answer_a, answer_b = student_answer, teacher_answer
            mapping = {"answer_a": "student", "answer_b": "teacher"}
        comparisons.append({
            "id": row["id"], "domain": row["domain"],
            "language": row["language"], "prompt": row["prompt"],
            "answer_a": answer_a, "answer_b": answer_b,
            "preferred": None, "review_notes": "",
        })
        answer_key.append({"id": row["id"], **mapping})

    output_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.parent.mkdir(parents=True, exist_ok=True)
    output_tmp = output_path.with_suffix(output_path.suffix + ".tmp")
    key_tmp = key_path.with_suffix(key_path.suffix + ".tmp")
    output_tmp.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in comparisons),
        encoding="utf-8")
    key_tmp.write_text(json.dumps({
        "teacher_model": cfg["teacher_model"],
        "student_base_model": cfg["student_base_model"],
        "student_adapter": cfg["student_adapter"],
        "seed": seed, "mapping": answer_key,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    output_tmp.replace(output_path)
    key_tmp.replace(key_path)
    print(json.dumps({
        "blind_comparisons": len(comparisons),
        "blind_output": str(output_path),
        "answer_key": str(key_path),
        "instruction": "Review answer_a and answer_b without opening the answer key.",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
