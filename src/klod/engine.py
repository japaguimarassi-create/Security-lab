import threading
from typing import Any

class InferenceEngine:
    def __init__(self, model_id: str, device_map: str = "auto"):
        self.model_id = model_id
        self.device_map = device_map
        self.model: Any = None
        self.tokenizer: Any = None
        self._lock = threading.Lock()

    @property
    def loaded(self) -> bool:
        return self.model is not None and self.tokenizer is not None

    def load(self) -> None:
        if self.loaded:
            return
        with self._lock:
            if self.loaded:
                return
            try:
                import torch
                from transformers import AutoModelForCausalLM, AutoTokenizer
            except ImportError as exc:
                raise RuntimeError("Install model dependencies: pip install -e '.[model]'") from exc
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_id)
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_id, torch_dtype="auto", device_map=self.device_map,
                low_cpu_mem_usage=True
            )
            self.model.eval()

    def generate(self, messages: list[dict], max_tokens: int = 256,
                 temperature: float = 0.7, top_p: float = 0.9) -> tuple[str, int, int]:
        if not self.loaded:
            raise RuntimeError("Model is not loaded")
        import torch
        inputs = self.tokenizer.apply_chat_template(
            messages, tokenize=True, add_generation_prompt=True,
            return_tensors="pt", return_dict=True
        )
        input_count = int(inputs["input_ids"].shape[-1])
        if input_count > 8192:
            raise ValueError("Input exceeds the 8192-token API limit")
        device = getattr(self.model, "device", None)
        if device is not None:
            inputs = inputs.to(device)
        params = {"max_new_tokens": max_tokens, "do_sample": temperature > 0,
                  "pad_token_id": self.tokenizer.eos_token_id,
                  "eos_token_id": self.tokenizer.eos_token_id}
        if temperature > 0:
            params.update(temperature=temperature, top_p=top_p)
        with torch.inference_mode():
            output = self.model.generate(**inputs, **params)
        tokens = output[0][input_count:]
        return self.tokenizer.decode(tokens, skip_special_tokens=True).strip(), input_count, int(tokens.numel())
