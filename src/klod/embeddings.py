import threading
from typing import Sequence

class EmbeddingEngine:
    def __init__(self, model_id: str, device: str = "cpu"):
        self.model_id = model_id
        self.device = device
        self._model = None
        self._lock = threading.RLock()
        self._error = None

    @property
    def loaded(self) -> bool:
        return self._model is not None

    @property
    def status(self) -> dict:
        return {"enabled": True, "loaded": self.loaded, "model_id": self.model_id,
                "device": self.device, "error": self._error}

    def load(self):
        if self.loaded:
            return
        with self._lock:
            if self.loaded:
                return
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(
                    self.model_id, device=self.device, trust_remote_code=False)
                self._model.max_seq_length = 512
                self._error = None
            except Exception as exc:
                self._error = f"{type(exc).__name__}: {exc}"
                raise RuntimeError("Could not load the local multilingual embedding model") from exc

    def _encode(self, texts: Sequence[str], prefix: str) -> list[list[float]]:
        if not texts:
            return []
        self.load()
        prepared = [prefix + str(text)[:5000] for text in texts]
        with self._lock:
            result = self._model.encode(
                prepared, batch_size=min(16, len(prepared)),
                normalize_embeddings=True, convert_to_numpy=True,
                show_progress_bar=False
            )
        if getattr(result, "ndim", 2) == 1:
            result = result.reshape(1, -1)
        return [[float(value) for value in vector] for vector in result.tolist()]

    def encode_query(self, text: str) -> list[float]:
        return self._encode([text], "query: ")[0]

    def encode_passages(self, texts: Sequence[str]) -> list[list[float]]:
        return self._encode(texts, "passage: ")
