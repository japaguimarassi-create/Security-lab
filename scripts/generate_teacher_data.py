import argparse
import hashlib
import json
from pathlib import Path

import torch
import yaml
from transformers import AutoModelForCausalLM, AutoTokenizer

from klod.distillation import answer_quality_issue, read_seed_prompts
from klod.specialists import GENERAL_SYSTEM_PROMPT


TEACHER_INSTRUCTIONS = """You are the teacher model preparing high-quality training examples for KLOD,
a general-purpose multilingual assistant. Answer the user's exact request in the language requested.
Be accurate, self-contained and appropriately detailed. Teach the reasoning when it helps the user.
For calculations, verify the result and units. For code, provide complete code only when requested and
respect stated versions. Separate facts, estimates and uncertainty. Never invent citations, sources,
measurements, browsing, experiments or actions. Do not add generic introductions or claim that you
performed work outside this conversation. Do not mention that this is a synthetic training example."""


def load_teacher(cfg: dict):
    quantized = bool(cfg.get("load_in_4bit", False))
    if quantized and not torch.cuda.is_available():
        raise RuntimeError("4-bit teacher loading requires a CUDA GPU and bitsandbytes")
    kwargs = {
        "device_map": cfg.get("device_map", "auto"),
        "trust_remote_code": False,
        "low_cpu_mem_usage": True,
    }
    if quantized:
        from transformers import BitsAndBytesConfig
        compute_dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=compute_dtype,
            bnb_4bit_use_double_quant=True,
        )
    else:
        kwargs["torch_dtype"] = "auto"
    tokenizer = AutoTokenizer.from_pretrained(
        cfg["teacher_model"], trust_remote_code=False)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(cfg["teacher_model"], **kwargs)
    model.eval()
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    return model, tokenizer


def generate_answer(model, tokenizer, system_prompt: str, prompt: str, cfg: dict) -> str:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]
    try:
        rendered = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    except TypeError:
        rendered = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True)
    encoded = tokenizer(
        rendered, return_tensors="pt", truncation=True,
        max_length=int(cfg["max_input_tokens"]))
    input_device = model.get_input_embeddings().weight.device
    encoded = {key: value.to(input_device) if hasattr(value, "to") else value
               for key, value in encoded.items()}
    temperature = float(cfg["temperature"])
    params = {
        "max_new_tokens": int(cfg["max_new_tokens"]),
        "do_sample": temperature > 0,
        "repetition_penalty": float(cfg["repetition_penalty"]),
        "pad_token_id": tokenizer.pad_token_id,
        "eos_token_id": tokenizer.eos_token_id,
    }
    if temperature > 0:
        params.update(temperature=temperature, top_p=float(cfg["top_p"]))
    with torch.inference_mode():
        output = model.generate(**encoded, **params)
    input_length = int(encoded["input_ids"].shape[-1])
    return tokenizer.decode(
        output[0][input_length:], skip_special_tokens=True).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/training/distillation.yaml"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    seed_path = Path(cfg["seed_prompts_path"])
    output_path = Path(cfg["candidate_output_path"])
    if output_path.exists() and not args.overwrite:
        raise SystemExit(f"{output_path} already exists; pass --overwrite to replace it")
    prompts = read_seed_prompts(seed_path)
    limit = args.limit if args.limit is not None else int(cfg.get("max_examples", len(prompts)))
    if limit < 1:
        raise SystemExit("--limit must be positive")
    prompts = prompts[:limit]
    output_path.parent.mkdir(parents=True, exist_ok=True)

    config_digest = hashlib.sha256(
        json.dumps(cfg, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    system_prompt = GENERAL_SYSTEM_PROMPT + "\n\n" + TEACHER_INSTRUCTIONS
    model, tokenizer = load_teacher(cfg)
    torch.manual_seed(int(cfg.get("seed", 42)))
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(int(cfg.get("seed", 42)))

    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    passed = rejected = 0
    with temporary.open("w", encoding="utf-8") as output:
        for index, seed in enumerate(prompts, 1):
            answer = generate_answer(
                model, tokenizer, system_prompt, seed["prompt"], cfg)
            issue = answer_quality_issue(
                seed["prompt"], answer,
                min_chars=int(cfg.get("minimum_answer_chars", 40)),
                max_chars=int(cfg.get("maximum_answer_chars", 16000)),
            )
            quality_passed = issue is None
            passed += int(quality_passed)
            rejected += int(not quality_passed)
            row = {
                "id": seed["id"],
                "domain": seed["domain"],
                "language": seed["language"],
                "teacher_model": cfg["teacher_model"],
                "teacher_config_sha256": config_digest,
                "messages": [
                    {"role": "system", "content": GENERAL_SYSTEM_PROMPT},
                    {"role": "user", "content": seed["prompt"]},
                    {"role": "assistant", "content": answer},
                ],
                "quality_passed": quality_passed,
                "quality_issue": issue,
                "approved": False,
                "review_status": "pending",
                "review_notes": "",
            }
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
            output.flush()
            print(f"[{index}/{len(prompts)}] {seed['id']}: "
                  f"{'candidate' if quality_passed else 'rejected - ' + str(issue)}")
    temporary.replace(output_path)
    print(json.dumps({
        "teacher_model": cfg["teacher_model"],
        "generated": len(prompts),
        "quality_passed": passed,
        "quality_rejected": rejected,
        "candidate_output": str(output_path),
        "config_sha256": config_digest,
        "student_base_model": cfg["student_base_model"],
        "next_step": "Review candidates and set approved=true only for answers verified by a human.",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
