import sys
from types import ModuleType

from klod.embeddings import EmbeddingEngine

class FakeArray(list):
    ndim = 2
    def tolist(self):
        return list(self)

class FakeSentenceTransformer:
    def __init__(self, model_id, device, trust_remote_code):
        self.model_id = model_id
        self.device = device
        self.calls = []
        self.max_seq_length = 512
    def encode(self, texts, **kwargs):
        self.calls.append((texts, kwargs))
        return FakeArray([[1.0, 0.0] for _ in texts])

def test_embedding_engine_applies_e5_query_and_passage_prefixes(monkeypatch):
    module = ModuleType("sentence_transformers")
    models = []
    def create_model(*args, **kwargs):
        instance = FakeSentenceTransformer(*args, **kwargs)
        models.append(instance)
        return instance
    module.SentenceTransformer = create_model
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    engine = EmbeddingEngine("test/e5", "cpu")
    query = engine.encode_query("como registrar entidade")
    passages = engine.encode_passages(["guia de entidades", "guia de blocos"])
    assert query == [1.0, 0.0]
    assert len(passages) == 2
    assert models[0].calls[0][0] == ["query: como registrar entidade"]
    assert models[0].calls[1][0] == ["passage: guia de entidades", "passage: guia de blocos"]
    assert models[0].calls[0][1]["normalize_embeddings"] is True
