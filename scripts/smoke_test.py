#!/usr/bin/env python3
"""Build-time ABI smoke test. Runs inside `docker build` (no GPU) — GPU-only
asserts are gated on torch.cuda.is_available(). A failure here fails the build."""
import importlib.metadata as md


def present(name: str) -> bool:
    try:
        md.distribution(name)
        return True
    except md.PackageNotFoundError:
        return False


# --- single opencv variant: contrib-headless only ---
variants = [
    d for d in (
        "opencv-python",
        "opencv-python-headless",
        "opencv-contrib-python",
        "opencv-contrib-python-headless",
    ) if present(d)
]
assert variants == ["opencv-contrib-python-headless"], f"cv2 variants present: {variants}"
import cv2  # noqa: E402
assert hasattr(cv2, "ximgproc"), "cv2.ximgproc missing (need the contrib build)"

# --- single onnxruntime: gpu only ---
assert present("onnxruntime-gpu"), "onnxruntime-gpu not installed"
assert not present("onnxruntime"), "plain onnxruntime present (must be gpu-only)"

# --- numpy / protobuf ---
import numpy  # noqa: E402
assert numpy.__version__.startswith("2.2"), numpy.__version__
import google.protobuf  # noqa: E402
assert google.protobuf.__version__.startswith("4.25"), google.protobuf.__version__

# --- torch cu128 ---
import torch  # noqa: E402
assert "+cu128" in torch.__version__, torch.__version__
assert torch.version.cuda == "12.8", torch.version.cuda

# --- HuggingFace set coherence (the split_torch_state_dict canary) ---
from huggingface_hub import split_torch_state_dict_into_shards  # noqa: F401,E402
import transformers  # noqa: F401,E402
import diffusers  # noqa: F401,E402

# --- attention backends (best-effort; not build-blockers) ---
if present("sageattention"):
    try:
        import sageattention  # noqa: F401
        print("sageattention import OK")
    except Exception as e:  # import may need CUDA at load on a GPU-less builder
        print(f"WARN: sageattention present but import deferred (no GPU at build?): {e}")
else:
    print("WARN: sageattention not installed (SDPA fallback)")
print("flash_attn present" if present("flash_attn") else "WARN: flash_attn not installed (optional)")

# --- GPU-only checks (skipped on CPU CI builder) ---
if torch.cuda.is_available():
    import onnxruntime as ort
    provs = ort.get_available_providers()
    assert "CUDAExecutionProvider" in provs, provs
    print("GPU capability:", torch.cuda.get_device_capability())

print("SMOKE OK | numpy", numpy.__version__, "| torch", torch.__version__)
