import os


def inference_dtype_name(cuda_available: bool, bf16_supported: bool) -> str:
    if os.environ.get("KLOD_FORCE_CPU") == "1":
        return "float32"
    if cuda_available and bf16_supported:
        return "bfloat16"
    return "float16" if cuda_available else "float32"


def load_training_model(model_id: str, load_in_4bit: bool = True,
                        gradient_checkpointing: bool = True):
    try:
        import torch
        from transformers import AutoModelForCausalLM, BitsAndBytesConfig
        from peft import prepare_model_for_kbit_training
    except ImportError as exc:
        raise RuntimeError("Install the appropriate training extra before starting.") from exc

    force_cpu = os.environ.get("KLOD_FORCE_CPU") == "1"
    use_cuda = torch.cuda.is_available() and not force_cpu
    if force_cpu or not use_cuda:
        threads = max(1, int(os.environ.get("KLOD_CPU_THREADS", "4")))
        torch.set_num_threads(threads)
        if load_in_4bit:
            raise RuntimeError("4-bit QLoRA requires CUDA. Use load_in_4bit=false for CPU LoRA.")
        model = AutoModelForCausalLM.from_pretrained(
            model_id,
            torch_dtype=torch.float32,
            low_cpu_mem_usage=True,
            attn_implementation="eager",
        )
        model.to("cpu")
        bf16 = False
    else:
        bf16 = bool(torch.cuda.is_bf16_supported())
        if load_in_4bit:
            compute_dtype = torch.bfloat16 if bf16 else torch.float16
            quantization = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=compute_dtype,
                bnb_4bit_use_double_quant=True,
            )
            model = AutoModelForCausalLM.from_pretrained(
                model_id,
                quantization_config=quantization,
                device_map="auto",
                trust_remote_code=False,
                low_cpu_mem_usage=True,
            )
            model = prepare_model_for_kbit_training(
                model, use_gradient_checkpointing=gradient_checkpointing
            )
        else:
            dtype = torch.bfloat16 if bf16 else torch.float16
            model = AutoModelForCausalLM.from_pretrained(
                model_id,
                torch_dtype=dtype,
                device_map="auto",
                trust_remote_code=False,
                low_cpu_mem_usage=True,
            )
            if gradient_checkpointing:
                model.gradient_checkpointing_enable()
                if hasattr(model, "enable_input_require_grads"):
                    model.enable_input_require_grads()

    model.config.use_cache = False
    if gradient_checkpointing and not load_in_4bit and not use_cuda:
        model.gradient_checkpointing_enable()
        if hasattr(model, "enable_input_require_grads"):
            model.enable_input_require_grads()
    return model, {
        "cuda": use_cuda,
        "bf16": bf16,
        "device": "cuda" if use_cuda else "cpu",
        "dtype": "4bit" if load_in_4bit else ("bfloat16" if bf16 else ("float16" if use_cuda else "float32")),
    }
