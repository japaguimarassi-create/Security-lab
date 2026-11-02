import threading
from pathlib import Path
from typing import Any

class InferenceEngine:
    def __init__(self, model_id: str, device_map: str = "auto", adapter_path: str | None = None,
                 max_input_tokens: int = 8192):
        self.model_id = model_id
        self.device_map = device_map
        self.adapter_path = adapter_path
        self.max_input_tokens = max_input_tokens
        self.model: Any = None
        self.tokenizer: Any = None
        self._lock = threading.RLock()
        self._loading = False
        self._load_error: str | None = None

    @property
    def loaded(self) -> bool:
        return self.model is not None and self.tokenizer is not None

    @property
    def status(self) -> dict:
        return {
            "loaded": self.loaded,
            "loading": self._loading,
            "model_id": self.model_id,
            "adapter_loaded": bool(self.adapter_path and self.loaded),
            "adapter_path": self.adapter_path,
            "error": self._load_error
        }

    def load(self) -> None:
        if self.loaded:
            return
        with self._lock:
            if self.loaded:
                return
            self._loading = True
            self._load_error = None
            try:
                import torch
                from transformers import AutoModelForCausalLM, AutoTokenizer
                tokenizer = AutoTokenizer.from_pretrained(self.model_id, trust_remote_code=False)
                model = AutoModelForCausalLM.from_pretrained(
                    self.model_id,
                    torch_dtype="auto",
                    device_map=self.device_map,
                    low_cpu_mem_usage=True,
                    trust_remote_code=False
                )
                if self.adapter_path:
                    adapter = Path(self.adapter_path)
                    if not adapter.is_dir():
                        raise FileNotFoundError(f"KLOD_ADAPTER_PATH does not exist: {adapter}")
                    from peft import PeftModel
                    model = PeftModel.from_pretrained(model, str(adapter), is_trainable=False)
                model.eval()
                self.tokenizer = tokenizer
                self.model = model
            except Exception as exc:
                self.model = None
                self.tokenizer = None
                self._load_error = f"{type(exc).__name__}: {exc}"
                raise
            finally:
                self._loading = False

    def generate(self, messages: list[dict], max_tokens: int = 256,
                 temperature: float = 0.7, top_p: float = 0.9) -> tuple[str, int, int]:
        if not self.loaded:
            raise RuntimeError("Model is not loaded")
        if not messages:
            raise ValueError("At least one message is required")
        if max_tokens < 1:
            raise ValueError("max_tokens must be positive")
        if not 0 <= temperature <= 2 or not 0 < top_p <= 1:
            raise ValueError("Invalid sampling parameters")

        import torch
        with self._lock:
            try:
                encoded = self.tokenizer.apply_chat_template(
                    messages, tokenize=True, add_generation_prompt=True,
                    return_tensors="pt", return_dict=True, enable_thinking=False
                )
            except TypeError:
                encoded = self.tokenizer.apply_chat_template(
                    messages, tokenize=True, add_generation_prompt=True,
                    return_tensors="pt", return_dict=True
                )
            input_count = int(encoded["input_ids"].shape[-1])
            if input_count > self.max_input_tokens:
                raise ValueError(f"Input has {input_count} tokens; limit is {self.max_input_tokens}")
            if self.model.config.max_position_embeddings:
                context_limit = int(self.model.config.max_position_embeddings)
                if input_count + max_tokens > context_limit:
                    max_tokens = max(1, context_limit - input_count)
            input_device = self.model.get_input_embeddings().weight.device
            encoded = {key: value.to(input_device) if hasattr(value, "to") else value
                       for key, value in encoded.items()}
            params = {
                "max_new_tokens": max_tokens,
                "do_sample": temperature > 0,
                "pad_token_id": self.tokenizer.eos_token_id,
                "eos_token_id": self.tokenizer.eos_token_id
            }
            if temperature > 0:
                params.update(temperature=temperature, top_p=top_p)
            with torch.inference_mode():
                output = self.model.generate(**encoded, **params)
            new_tokens = output[0][input_count:]
            answer = self.tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
            return answer, input_count, int(new_tokens.numel())
