"""sitecustomize.py — ComfyUI-Ultimate runtime compatibility layer.

Automatically executed on Python startup when installed in site-packages.
Guarantees compatibility for both legacy (NumPy 1.x) and modern custom nodes.
"""
import sys

# 1. NumPy 1.x backwards compatibility shim for NumPy 2.x
# Hundreds of legacy nodes access deprecated/removed type aliases like np.float_ or np.bool_
try:
    import numpy as np

    _legacy_aliases = {
        'float_': np.float64,
        'int_': np.int64,
        'bool_': np.bool,
        'complex_': np.complex128,
        'object_': np.object_,
        'str_': np.str_,
        'unicode_': np.str_,
        'string_': np.bytes_,
    }
    for _name, _target in _legacy_aliases.items():
        if not hasattr(np, _name):
            setattr(np, _name, _target)
except Exception:
    pass

# 2. OpenCV contrib / headless sanity check
try:
    import cv2
except Exception:
    pass
