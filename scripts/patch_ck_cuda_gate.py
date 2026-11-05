#!/usr/bin/env python3
"""Make comfy-kitchen's CUDA feature probes respect ComfyUI's cu130 gate.

The failure this fixes
----------------------
MiniMax H3 (and any quantized/convrot VAE) decode crashes with::

    RuntimeError: detect_k_anchor kernel launch failed:
    CUDA driver version is insufficient for CUDA runtime version

    comfy/ldm/minimax/vae.py:315  out = comfy.quant_ops.ck.int8_attention(query, key, value)
    -> comfy_kitchen/sage_attention.py -> _int8_attention_cuda -> _C.sage_sdpa
    -> detect_k_anchor  (the first kernel launch on that path)

Two independent facts have to line up for that to happen, and both do on this image:

1. The VAE decoder's weights are quantized, so ``isinstance(self.to_qkv.weight,
   comfy.ops.QuantizedTensor)`` is True and ComfyUI takes its INT8-attention branch.
2. ``int8_attention`` is the one comfy-kitchen entry point that **bypasses
   comfy-kitchen's backend registry**. Its probe is only::

       return capability >= _NATIVE_MINIMUM_CAPABILITY and _cuda_backend._EXT_AVAILABLE

   Every other comfy-kitchen op is dispatched through ``registry.get_capable_backend()``,
   so ComfyUI's own gate in ``comfy/quant_ops.py`` takes effect for them::

       if cuda_version < (13,):
           ck.registry.disable("cuda")
           logging.warning("WARNING: You need pytorch with cu130 or higher ...")

   This image is torch 2.8.0+cu128, so the registry's cuda backend *is* disabled —
   but ``int8_attention`` never looks, ComfyUI computes
   ``COMFY_KITCHEN_INT8_ATTENTION_IS_AVAILABLE = comfy_kitchen.int8_attention_is_available()``
   as True, and calls it. comfy-kitchen has shipped **CUDA 13.0 wheels since its first
   release** (0.1.0), and those need NVIDIA driver r580+; the pod's driver is older, so
   the CUDA-13 cubin cannot be loaded and the launch fails with cudaErrorInsufficientDriver.

   The same defect exists for ``flash_attention_decode`` (ComfyUI issue #16449,
   "…although the CUDA backend is disabled on torch < cu130"), closed upstream with
   "We do not support using cuda 12 on newer GPUs."

What this does
--------------
Appends a gate to the installed ``comfy_kitchen/__init__.py`` that wraps every public
``*_is_available`` helper. When comfy-kitchen's CUDA kernels cannot run on this host —
torch's CUDA runtime is < 13, the registry's cuda backend is disabled, or the NVIDIA
driver is older than r580 — the probes return False, exactly as they would if the
extension were missing. ComfyUI then takes its normal attention paths instead of
launching a kernel that cannot load. ``comfy_kitchen.int8_decode.is_available`` has the
same registry bypass and is imported directly by ComfyUI's Qwen3.5 text encoder (v0.44.0+),
so it is gated too.

ROCm builds are passed through untouched (the HIP path has its own kernels), and a host
that really can run the CUDA kernels (cu130 torch + driver r580+) is unaffected.

The edit is idempotent and is re-applied on every boot by ``start.sh``, because updating
ComfyUI inside a pod reinstalls comfy-kitchen and would otherwise undo it.

Usage
-----
    python patch_ck_cuda_gate.py                  # patch (autodetect site-packages)
    python patch_ck_cuda_gate.py --report         # patch + print the verdict line
    python patch_ck_cuda_gate.py --check          # verify only; exit 1 if missing
    python patch_ck_cuda_gate.py --require        # fail if comfy-kitchen is absent

Exit codes: 0 ok, 1 --check found the patch missing, 2 comfy-kitchen absent under
--require, 3 comfy-kitchen is present but its shape changed (the gate cannot be applied
safely — the build must fail rather than ship an unguarded image).
"""

import argparse
import glob
import importlib.util
import site
import sys
from pathlib import Path

MARKER = "# --- ComfyUI-Ultimate: comfy-kitchen CUDA-availability gate ---"
END_MARKER = "# --- end ComfyUI-Ultimate patch ---"

# The public helper ComfyUI reads for the crashing call site. Its presence proves we are
# looking at a comfy-kitchen new enough to have the registry-bypassing int8 path.
ANCHORS = ("int8_attention_is_available",)

#: Driver branch comfy-kitchen's prebuilt CUDA wheels require (CUDA 13.0 GA floor).
MIN_DRIVER_MAJOR = 580

PATCH_BLOCK = (
    "\n\n"
    + MARKER
    + '''
# Every public *_is_available helper in this package is wrapped so that a CUDA backend
# which cannot actually run on this host reports itself unavailable, instead of letting
# ComfyUI launch a kernel that fails at load time. See
# scripts/patch_ck_cuda_gate.py for the full story (MiniMax H3 / convrot VAE decode:
# "detect_k_anchor kernel launch failed: CUDA driver version is insufficient ...").
import functools as _ck_ultimate_functools

_CK_ULTIMATE_DRIVER_CUDA = []


def _ck_ultimate_fmt_cuda(cuda_api):
    return "%d.%d" % (cuda_api // 1000, (cuda_api % 1000) // 10)


def _ck_ultimate_driver_cuda():
    """CUDA version the installed driver supports (13000 = 13.0), or None if unknown."""
    if _CK_ULTIMATE_DRIVER_CUDA:
        return _CK_ULTIMATE_DRIVER_CUDA[0]
    cuda_api = None
    # Preferred: cudart answers exactly, with no subprocess and no parsing.
    try:
        cuda_api = int(torch.cuda.cudart().cudaDriverGetVersion())
    except Exception:
        cuda_api = None
    if not cuda_api:
        # Fallback: the driver version string (r570 -> CUDA 12.8, r580 -> CUDA 13.0).
        try:
            import subprocess

            proc = subprocess.run(
                ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                major = int(proc.stdout.strip().splitlines()[0].strip().split(".")[0])
                cuda_api = (
                    13000
                    if major >= 580
                    else 12900
                    if major >= 575
                    else 12800
                    if major >= 570
                    else 0
                )
        except Exception:
            cuda_api = None
    _CK_ULTIMATE_DRIVER_CUDA.append(cuda_api)
    return cuda_api


def _ck_ultimate_cuda_gate():
    """(usable, reason) for comfy-kitchen's CUDA kernels on this host."""
    if getattr(torch.version, "hip", None) is not None:
        return True, "ROCm build (HIP kernels)"
    cuda_runtime = getattr(torch.version, "cuda", None)
    if cuda_runtime is None:
        return False, "torch has no CUDA runtime"
    try:
        if tuple(int(part) for part in str(cuda_runtime).split(".")) < (13,):
            return False, (
                "torch is cu%s but comfy-kitchen ships CUDA-13 kernels" % cuda_runtime
            )
    except Exception:
        pass
    try:
        if not registry.is_available("cuda"):
            return False, "comfy-kitchen cuda backend is disabled"
    except Exception:
        pass
    driver_cuda = _ck_ultimate_driver_cuda()
    if driver_cuda is not None and driver_cuda < 13000:
        return False, (
            "driver supports CUDA %s but comfy-kitchen ships CUDA-13 kernels"
            % _ck_ultimate_fmt_cuda(driver_cuda)
        )
    return True, "CUDA kernels usable"


def _ck_ultimate_cuda_gate_reason():
    return _ck_ultimate_cuda_gate()[1]


_CK_ULTIMATE_GATED = []


def _ck_ultimate_gate(name, func):
    @_ck_ultimate_functools.wraps(func)
    def wrapper(*args, **kwargs):
        if not _ck_ultimate_cuda_gate()[0]:
            return False
        return func(*args, **kwargs)

    wrapper.__ck_ultimate_gate__ = True
    wrapper.__wrapped_name__ = name
    return wrapper


for _ck_ultimate_name in sorted(n for n in dir() if n.endswith("_is_available")):
    _ck_ultimate_fn = globals()[_ck_ultimate_name]
    if callable(_ck_ultimate_fn) and not getattr(_ck_ultimate_fn, "__ck_ultimate_gate__", False):
        globals()[_ck_ultimate_name] = _ck_ultimate_gate(_ck_ultimate_name, _ck_ultimate_fn)
        _CK_ULTIMATE_GATED.append(_ck_ultimate_name)

try:  # keep the module namespace tidy; never fail an import over this
    del _ck_ultimate_name, _ck_ultimate_fn
except NameError:
    pass

# ComfyUI imports one probe straight from its submodule, out of reach of the loop above:
#   comfy/text_encoders/qwen35.py: from comfy_kitchen.int8_decode import is_available
# This package __init__ finishes before that import binds the name, so rebinding the
# submodule attribute here is what ComfyUI gets.
try:
    from . import int8_decode as _ck_ultimate_int8_decode

    if not getattr(_ck_ultimate_int8_decode.is_available, "__ck_ultimate_gate__", False):
        _ck_ultimate_int8_decode.is_available = _ck_ultimate_gate(
            "int8_decode.is_available", _ck_ultimate_int8_decode.is_available
        )
        _CK_ULTIMATE_GATED.append("int8_decode.is_available")
except (ImportError, AttributeError):
    pass
'''
    + END_MARKER
    + "\n"
)


def _site_dir_candidates():
    dirs = []
    try:
        dirs.extend(Path(p) for p in site.getsitepackages())
    except Exception:
        pass
    try:
        dirs.append(Path(site.getusersitepackages()))
    except Exception:
        pass
    dirs.append(Path(sys.prefix) / "lib")
    dirs.append(Path("/opt/venv/lib"))
    return dirs


def find_ck_init(site_packages=None):
    """Locate the installed comfy_kitchen/__init__.py, or None."""
    if site_packages:
        candidate = Path(site_packages) / "comfy_kitchen" / "__init__.py"
        return candidate if candidate.is_file() else None

    try:
        spec = importlib.util.find_spec("comfy_kitchen")
    except Exception:
        spec = None
    if spec is not None and spec.submodule_search_locations:
        for location in spec.submodule_search_locations:
            candidate = Path(location) / "__init__.py"
            if candidate.is_file():
                return candidate

    patterns = ["/opt/venv/lib/python3*/site-packages/comfy_kitchen/__init__.py"]
    for base in _site_dir_candidates():
        patterns.append(str(base / "python3*" / "site-packages" / "comfy_kitchen" / "__init__.py"))
        patterns.append(str(base / "site-packages" / "comfy_kitchen" / "__init__.py"))
    for pattern in patterns:
        for hit in sorted(glob.glob(pattern)):
            candidate = Path(hit)
            if candidate.is_file():
                return candidate
    return None


def report(target):
    """Print the CUDA-gate verdict by importing the patched package."""
    site_dir = str(target.parent.parent)
    if site_dir not in sys.path:
        sys.path.insert(0, site_dir)
    try:
        import comfy_kitchen

        usable = bool(comfy_kitchen.int8_attention_is_available())
        reason = comfy_kitchen._ck_ultimate_cuda_gate_reason()
        gated = ", ".join(getattr(comfy_kitchen, "_CK_ULTIMATE_GATED", [])) or "none"
    except Exception as exc:  # torch missing, no GPU, broken install: never fatal
        print("[ck-gate] could not evaluate comfy-kitchen CUDA availability: %r" % (exc,))
        return
    print(
        "[ck-gate] comfy-kitchen CUDA kernels: %s (gate: %s) -> int8 attention %s"
        % (
            "usable" if usable else "UNAVAILABLE",
            reason,
            "available" if usable else "DISABLED, ComfyUI uses its normal attention path",
        )
    )
    print("[ck-gate] gated probes: %s" % gated)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Make comfy-kitchen's CUDA probes respect ComfyUI's cu130 gate.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--site-packages",
        default=None,
        help="site-packages directory containing comfy_kitchen/ (default: autodetect)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the patch is present without modifying anything (exit 1 if missing)",
    )
    parser.add_argument(
        "--require",
        action="store_true",
        help="fail when comfy-kitchen is not installed (used by the image build)",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="after patching, print the CUDA-gate verdict",
    )
    parser.add_argument("--quiet", action="store_true", help="print problems only")
    args = parser.parse_args(argv)

    def say(message):
        if not args.quiet:
            print(message, flush=True)

    target = find_ck_init(args.site_packages)
    if target is None:
        if args.require:
            print(
                "ERROR: comfy-kitchen is not installed; cannot apply the CUDA gate",
                file=sys.stderr,
            )
            return 2
        say("[ck-gate] comfy-kitchen not found; nothing to patch")
        return 0

    source = target.read_text(encoding="utf-8")

    if MARKER in source:
        say("[ck-gate] already patched: %s" % target)
        if args.report:
            report(target)
        return 0

    if args.check:
        print("ERROR: %s is not patched" % target, file=sys.stderr)
        return 1

    missing = [anchor for anchor in ANCHORS if anchor not in source]
    if missing:
        print(
            "ERROR: %s no longer contains %s — comfy-kitchen changed shape, so the CUDA "
            "gate cannot be applied. Re-check scripts/patch_ck_cuda_gate.py against the "
            "installed version." % (target, ", ".join(repr(m) for m in missing)),
            file=sys.stderr,
        )
        return 3

    if not source.endswith("\n"):
        source += "\n"
    target.write_text(source + PATCH_BLOCK, encoding="utf-8")
    say("[ck-gate] patched %s" % target)
    if args.report:
        report(target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
