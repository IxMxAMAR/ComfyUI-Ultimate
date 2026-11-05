#!/usr/bin/env bash
# Tests for scripts/patch_ck_cuda_gate.py — the comfy-kitchen CUDA-availability gate.
#
# The gate logic is exercised without torch or a GPU: a fake site-packages provides
# comfy_kitchen, torch and nvidia-smi, driven by environment variables, so the
# cu128 / driver-r570 / disabled-registry / ROCm branches are all assertable on any
# runner (dev box, CI, no GPU) — the same reason the real crash can't be caught by a
# CPU import gate.
cd "$(dirname "$0")" || exit 1
. ./helpers.sh

SCRIPT="../scripts/patch_ck_cuda_gate.py"
PY="${PYTHON:-python}"
MARKER='ComfyUI-Ultimate: comfy-kitchen CUDA-availability gate'

assert_exit() { # assert_exit <label> <expected-code> <cmd...>
  local label="$1" expected="$2" actual
  shift 2
  "$@" >/dev/null 2>&1
  actual=$?
  assert_eq "$actual" "$expected" "$label"
}

new_gate_sandbox() {
  SANDBOX="$(mktemp -d)"
  SITE="$SANDBOX/site"
  BIN="$SANDBOX/bin"
  mkdir -p "$SITE/comfy_kitchen" "$SITE/torch" "$BIN"

  # fake torch: CUDA runtime / ROCm flavour / driver capability are env-driven
  cat > "$SITE/torch/__init__.py" <<'EOF'
import os


class _Version:
    cuda = os.environ.get("FAKE_TORCH_CUDA") or None
    hip = os.environ.get("FAKE_TORCH_HIP") or None


version = _Version()


class _Cudart:
    def cudaDriverGetVersion(self):
        return int(os.environ.get("FAKE_DRIVER_CUDA", "0"))


class _Cuda:
    _EXT_AVAILABLE = True

    def is_available(self):
        return True

    def get_device_capability(self, device=None):
        return (8, 9)

    def cudart(self):
        return _Cudart()


cuda = _Cuda()
EOF

  # fake registry: stands in for ComfyUI's ck.registry.disable("cuda") on cu12x
  cat > "$SITE/comfy_kitchen/registry.py" <<'EOF'
import os


class _Registry:
    def is_available(self, name):
        if name == "cuda" and os.environ.get("FAKE_CK_CUDA_DISABLED") == "1":
            return False
        return True


registry = _Registry()
EOF

  # fake submodules shaped like the real probes
  cat > "$SITE/comfy_kitchen/sage_attention.py" <<'EOF'
import torch

_NATIVE_MINIMUM_CAPABILITY = (7, 5)


def is_available(device=None):
    if device is not None and device.type != "cuda":
        return False
    if not torch.cuda.is_available():
        return False
    capability = torch.cuda.get_device_capability(device)
    return capability >= _NATIVE_MINIMUM_CAPABILITY and torch.cuda._EXT_AVAILABLE
EOF

  cat > "$SITE/comfy_kitchen/flash_attention.py" <<'EOF'
import torch


def is_available(device=None):
    return bool(torch.cuda._EXT_AVAILABLE)
EOF

  # not imported by the package __init__; ComfyUI imports it directly (qwen35.py)
  cat > "$SITE/comfy_kitchen/int8_decode.py" <<'EOF'
import torch


def is_available(device=None):
    return bool(torch.cuda._EXT_AVAILABLE)
EOF

  # fake package __init__: the same public aliases the real package exports
  cat > "$SITE/comfy_kitchen/__init__.py" <<'EOF'
import torch

from .flash_attention import is_available as flash_attention_decode_is_available
from .registry import registry
from .sage_attention import is_available as int8_attention_is_available
EOF

  # fake nvidia-smi
  cat > "$BIN/nvidia-smi" <<'EOF'
#!/usr/bin/env bash
echo "${FAKE_DRIVER:-570.195.03}"
EOF
  chmod +x "$BIN/nvidia-smi"

  unset FAKE_TORCH_CUDA FAKE_TORCH_HIP FAKE_CK_CUDA_DISABLED FAKE_DRIVER FAKE_DRIVER_CUDA
}

run_gate() { # run_gate <probe-name> -> "<value> | <reason>"
  (cd "$SANDBOX" && PYTHONPATH="$SITE" PATH="$BIN:$PATH" "$PY" -c "
import comfy_kitchen as ck
print(ck.$1(), '|', ck._ck_ultimate_cuda_gate_reason())
" 2>&1)
}

int8_decode_value() { # the import ComfyUI's qwen35.py does, not the package attribute
  (cd "$SANDBOX" && PYTHONPATH="$SITE" PATH="$BIN:$PATH" "$PY" -c "
from comfy_kitchen.int8_decode import is_available
print(is_available())
" 2>&1)
}

gate_value() { run_gate "$1" | cut -d'|' -f1 | tr -d ' '; }

patch() { "$PY" "$SCRIPT" --site-packages "$SITE" "$@"; }

# ---------------------------------------------------------------------------
# 1. Negative cases on a pristine sandbox
# ---------------------------------------------------------------------------
new_gate_sandbox
assert_exit "--check fails before the patch" 1 patch --check
assert_exit "--require fails when comfy-kitchen is absent" 2 \
  "$PY" "$SCRIPT" --site-packages "$SANDBOX/nope" --require
assert_exit "missing comfy-kitchen is a no-op without --require" 0 \
  "$PY" "$SCRIPT" --site-packages "$SANDBOX/nope"

# An upstream reshape must fail loudly (exit 3), never patch blindly.
cat > "$SITE/comfy_kitchen/__init__.py" <<'EOF'
# comfy-kitchen with the public alias renamed
from .sage_attention import is_available as some_other_name
EOF
assert_exit "renamed anchor fails loudly instead of patching" 3 patch

# An older comfy-kitchen without int8_decode still patches and still imports.
new_gate_sandbox
rm "$SITE/comfy_kitchen/int8_decode.py"
assert_exit "comfy-kitchen without int8_decode patches cleanly" 0 patch
export FAKE_TORCH_CUDA=12.8 FAKE_DRIVER=570.195.03
assert_eq "$(gate_value int8_attention_is_available)" "False" "no int8_decode: package still imports and gates"
unset FAKE_TORCH_CUDA FAKE_DRIVER

# ---------------------------------------------------------------------------
# 2. Apply the gate
# ---------------------------------------------------------------------------
new_gate_sandbox
assert_exit "patcher applies cleanly" 0 patch
assert_eq "$(grep -c "$MARKER" "$SITE/comfy_kitchen/__init__.py")" "1" "marker appended once"
assert_true "patched __init__.py compiles" "$PY" -m py_compile "$SITE/comfy_kitchen/__init__.py"

before="$(cksum "$SITE/comfy_kitchen/__init__.py")"
assert_exit "second run is a no-op" 0 patch
assert_eq "$(cksum "$SITE/comfy_kitchen/__init__.py")" "$before" "idempotent: file unchanged"
assert_exit "--check passes after patching" 0 patch --check
assert_true "--report prints a verdict" bash -c "'$PY' '$SCRIPT' --site-packages '$SITE' --report | grep -q 'comfy-kitchen CUDA kernels'"

# ---------------------------------------------------------------------------
# 3. The gate itself: this image's stack must report UNAVAILABLE
# ---------------------------------------------------------------------------
export FAKE_TORCH_CUDA=12.8 FAKE_DRIVER=570.195.03
assert_eq "$(gate_value int8_attention_is_available)" "False" "cu128 + r570: int8 attention unavailable"
assert_eq "$(gate_value flash_attention_decode_is_available)" "False" "cu128 + r570: flash-attention decode unavailable"
assert_eq "$(int8_decode_value)" "False" "cu128 + r570: int8 decode (direct submodule import) unavailable"

# A host that can really run the CUDA-13 kernels is left alone.
export FAKE_TORCH_CUDA=13.0 FAKE_DRIVER_CUDA=13000
assert_eq "$(gate_value int8_attention_is_available)" "True" "cu130 + driver with CUDA 13.0: int8 attention available"
assert_eq "$(gate_value flash_attention_decode_is_available)" "True" "cu130 + driver with CUDA 13.0: flash-attention decode available"
assert_eq "$(int8_decode_value)" "True" "cu130 + driver with CUDA 13.0: int8 decode available"

# A driver capped below CUDA 13.0 cannot load the CUDA-13 kernels.
export FAKE_DRIVER_CUDA=12080
assert_eq "$(gate_value int8_attention_is_available)" "False" "cu130 + driver capped at CUDA 12.8: int8 attention unavailable"

# ComfyUI disabled the registry backend: the probe must agree.
export FAKE_DRIVER_CUDA=13000 FAKE_CK_CUDA_DISABLED=1
assert_eq "$(gate_value int8_attention_is_available)" "False" "registry cuda disabled: int8 attention unavailable"
unset FAKE_CK_CUDA_DISABLED

# The nvidia-smi fallback (used when cudart is unavailable) needs a real exec.
unset FAKE_DRIVER_CUDA
if [ "$(uname -s)" = "Linux" ]; then
  export FAKE_DRIVER=570.195.03
  assert_eq "$(gate_value int8_attention_is_available)" "False" "nvidia-smi fallback: r570 unavailable"
  unset FAKE_DRIVER
else
  skip "nvidia-smi fallback path (Windows cannot exec a shebang script via subprocess; enforced on Linux CI)"
fi

# ROCm: the HIP kernels are a different build and must pass through untouched.
unset FAKE_TORCH_CUDA
export FAKE_TORCH_HIP=1
assert_eq "$(gate_value int8_attention_is_available)" "True" "ROCm build: probe untouched"

# A usable stack still answers the original probe.
unset FAKE_TORCH_HIP
export FAKE_TORCH_CUDA=13.0 FAKE_DRIVER_CUDA=13000
assert_eq "$(gate_value int8_attention_is_available)" "True" "usable stack: probe answers True"
unset FAKE_TORCH_CUDA FAKE_DRIVER_CUDA

echo "SUITE_RESULT $TESTS_RUN $TESTS_FAILED $TESTS_SKIPPED"
