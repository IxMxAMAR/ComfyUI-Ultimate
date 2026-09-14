#!/usr/bin/env bash
# shellcheck source=helpers.sh
. "$(dirname "$0")/helpers.sh"

SCRIPTS_DIR="$(cd "$(dirname "$0")/../scripts" && pwd)"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "-- sanitize_requirements"
new_sandbox
cat > "$SANDBOX/reqs.txt" <<'EOF'
# Sample requirements
torch>=2.0.0
torchvision==0.15.2
torchaudio
opencv-python>=4.8.0
opencv-contrib-python
onnxruntime>=1.16.0
numpy<2.0.0,>=1.24.0
transformers>=4.40.0
qwen-vl-utils
EOF

python "$SCRIPTS_DIR/sanitize_requirements.py" "$SANDBOX/reqs.txt" "$SANDBOX/clean.txt"
assert_file "$SANDBOX/clean.txt" "clean requirements created"

# torch stack should be stripped
out="$(cat "$SANDBOX/clean.txt")"
assert_true "torch stripped" bash -c "! grep -q 'torch>=' '$SANDBOX/clean.txt'"
assert_true "torchvision stripped" bash -c "! grep -q 'torchvision' '$SANDBOX/clean.txt'"
assert_true "torchaudio stripped" bash -c "! grep -q 'torchaudio' '$SANDBOX/clean.txt'"

# opencv remapped to contrib-headless
assert_true "opencv normalized" grep -q "opencv-contrib-python-headless" "$SANDBOX/clean.txt"
assert_true "opencv-python remapped" bash -c "! grep -q 'opencv-python' '$SANDBOX/clean.txt'"

# onnxruntime remapped to gpu
assert_true "onnxruntime remapped to gpu" grep -q "onnxruntime-gpu" "$SANDBOX/clean.txt"

# numpy<2 stripped
assert_true "numpy<2 stripped" bash -c "! grep -q 'numpy<2' '$SANDBOX/clean.txt'"

# clean packages preserved
assert_true "transformers preserved" grep -q "transformers>=4.40.0" "$SANDBOX/clean.txt"
assert_true "qwen-vl-utils preserved" grep -q "qwen-vl-utils" "$SANDBOX/clean.txt"
cleanup_sandbox

echo "-- sitecustomize NumPy 1.x backwards compatibility"
PYSCRIPTS="$SCRIPTS_DIR"
if command -v cygpath >/dev/null 2>&1; then
  PYSCRIPTS="$(cygpath -w "$SCRIPTS_DIR")"
fi
out="$(python -c "
import sys, os, types, importlib.util

try:
    import numpy as np
except ModuleNotFoundError:
    np = types.ModuleType('numpy')
    np.float64 = float
    np.int64 = int
    np.bool = bool
    np.complex128 = complex
    np.object_ = object
    np.str_ = str
    np.bytes_ = bytes
    sys.modules['numpy'] = np

spec = importlib.util.spec_from_file_location('sitecustomize', os.path.join(r'$PYSCRIPTS', 'sitecustomize.py'))
mod = importlib.util.module_from_spec(spec)
sys.modules['sitecustomize'] = mod
spec.loader.exec_module(mod)

assert hasattr(np, 'float_'), 'float_ missing'
assert hasattr(np, 'int_'), 'int_ missing'
assert hasattr(np, 'bool_'), 'bool_ missing'
print('OK')
" 2>&1 | tail -n 1)"
assert_eq "$out" "OK" "NumPy 1.x aliases present via sitecustomize"

echo "-- configure_manager"
new_sandbox
O_SRC="$REPO_DIR/pip_overrides.json"
B_SRC="$REPO_DIR/pip_blacklist.list"
TARGET_MGR="$SANDBOX/mgr"
if command -v cygpath >/dev/null 2>&1; then
  O_SRC="$(cygpath -w "$O_SRC")"
  B_SRC="$(cygpath -w "$B_SRC")"
  TARGET_MGR="$(cygpath -w "$TARGET_MGR")"
fi
export OVERRIDES_SRC="$O_SRC"
export BLACKLIST_SRC="$B_SRC"

python "$SCRIPTS_DIR/configure_manager.py" "$TARGET_MGR"
assert_file "$SANDBOX/mgr/pip_overrides.json" "manager overrides populated"
assert_file "$SANDBOX/mgr/pip_blacklist.list" "manager blacklist populated"
assert_file "$SANDBOX/mgr/config.ini" "manager config.ini populated"

assert_true "config has downgrade_blacklist" grep -q "downgrade_blacklist" "$SANDBOX/mgr/config.ini"
assert_true "torch in downgrade_blacklist" grep -q "torch" "$SANDBOX/mgr/config.ini"
cleanup_sandbox

echo "SUITE_RESULT $TESTS_RUN $TESTS_FAILED $TESTS_SKIPPED"
