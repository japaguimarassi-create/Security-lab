from klod.training import inference_dtype_name


def test_inference_dtype_uses_float16_for_t4():
    assert inference_dtype_name(True, False) == "float16"


def test_inference_dtype_uses_bfloat16_when_supported():
    assert inference_dtype_name(True, True) == "bfloat16"


def test_inference_dtype_uses_float32_without_cuda():
    assert inference_dtype_name(False, False) == "float32"
