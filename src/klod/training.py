from pathlib import Path

def load_training_model(model_id: str, load_in_4bit: bool = True,
                        gradient_checkpointing: bool = True):
    try:
        import torch
        from transformers import AutoModelForCausalLM, BitsAndBytesConfig
        from peft import prepare_model_for_kbit_training
    except ImportError as exc:
        raise RuntimeError("Install the training extra: pip install -e '.[training]'") from exc

    use_cuda = torch.cuda.is_available()
    if load_in_4bit and not use_cuda:
        raise RuntimeError("4-bit QLoRA requires a CUDA GPU; run training_preflight.py first")
    bf16 = bool(use_cuda and torch.cuda.is_bf16_supported())
    kwargs = {"trust_remote_code": False, "low_cpu_mem_usage": True}

    if load_in_4bit:
        compute_dtype = torch.bfloat16 if bf16 else torch.float16
        quantization = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=compute_dtype,
            bnb_4bit_use_double_quant=True
        )
        kwargs.update(quantization_config=quantization, device_map="auto")
        model = AutoModelForCausalLM.from_pretrained(model_id, **kwargs)
        model = prepare_model_for_kbit_training(
            model, use_gradient_checkpointing=gradient_checkpointing)
    else:
        model = AutoModelForCausalLM.from_pretrained(model_id, torch_dtype="auto", **kwargs)
        if gradient_checkpointing:
            model.gradient_checkpointing_enable()
            if hasattr(model, "enable_input_require_grads"):
                model.enable_input_require_grads()

    model.config.use_cache = False
    return model, {"cuda": use_cuda, "bf16": bf16}
