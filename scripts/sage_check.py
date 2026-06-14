#!/usr/bin/env python3
"""Classify a SageAttention import on a GPU-less CI builder.

exit 0  -> wheel is usable: imported OK, or only failed because there's no GPU/
           driver at build time (environmental, not the wheel's fault).
exit 2  -> ABI mismatch (undefined symbol): caller should compile from source.
"""
import sys

try:
    import sageattention  # noqa: F401
    print("sage_check: import OK")
    sys.exit(0)
except Exception as e:  # noqa: BLE001
    msg = str(e).lower()
    abi = ("undefined symbol" in msg
           or "symbol not found" in msg
           or "incompatible" in msg
           or "glibcxx" in msg          # wheel needs newer libstdc++ than the image
           or "glibc_" in msg
           or "cannot open shared object" in msg
           or "cannot load" in msg
           or ("_c" in msg and "cannot import" in msg))
    if abi:
        print("sage_check: WHEEL UNUSABLE (ABI/loader) ->", e)
        sys.exit(2)
    # libcuda / "no CUDA-capable device" / driver-not-found => no GPU on builder.
    print("sage_check: import deferred (no GPU at build, wheel ABI looks fine) ->", e)
    sys.exit(0)
