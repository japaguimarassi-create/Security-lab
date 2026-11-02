from klod.engine import InferenceEngine

def test_engine_starts_unloaded():
    engine = InferenceEngine("model-id")
    assert engine.loaded is False
    assert engine.status["model_id"] == "model-id"
