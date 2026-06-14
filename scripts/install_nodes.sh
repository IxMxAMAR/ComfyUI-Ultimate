#!/usr/bin/env bash
# Clone the 29 custom-node packs at pinned commits and install their deps under
# the global PIP_CONSTRAINT. The CI import gate (not this script) is the source of
# truth for success, so a single pack's hiccup logs loudly but does not abort the
# build — except clone/checkout failures, which are reported.
set -uo pipefail

PINS="${1:-/opt/node_pins.txt}"
NODES_DIR=/ComfyUI/custom_nodes
mkdir -p "$NODES_DIR"
PIP="uv pip install --no-cache"
fail=0

install_reqs () {
  local dir="$1"
  if [ -f "$dir/requirements.txt" ]; then
    echo ">> $PIP -r $dir/requirements.txt"
    $PIP -r "$dir/requirements.txt" || { echo "!! requirements failed: $dir"; fail=1; }
  else
    echo ">> (no requirements.txt) $dir"
  fi
}

while read -r name url sha; do
  case "$name" in ''|\#*) continue ;; esac
  dest="$NODES_DIR/$name"
  echo "==================== $name @ $sha ===================="
  if [ ! -d "$dest/.git" ]; then
    git clone --filter=blob:none "$url" "$dest" || { echo "!! clone failed: $name"; fail=1; continue; }
  fi
  git -C "$dest" checkout -q "$sha" || { echo "!! checkout failed: $name ($sha)"; fail=1; }

  case "$name" in
    ComfyUI-Frame-Interpolation)
      # Never run install.py (it pip-installs torch per-line, clobbering cu128).
      if [ -f "$dest/requirements-no-cupy.txt" ]; then
        $PIP -r "$dest/requirements-no-cupy.txt" || { echo "!! reqs failed: $name"; fail=1; }
      else
        install_reqs "$dest"
      fi
      $PIP cupy-cuda12x || echo "WARN: cupy-cuda12x failed (frame-interp falls back to CPU)"
      ;;
    ComfyUI-Impact-Pack)
      export SAM2_BUILD_CUDA=0      # don't compile a CUDA ext at build time
      install_reqs "$dest"
      ;;
    *)
      install_reqs "$dest"
      ;;
  esac
done < "$PINS"

if [ "$fail" -ne 0 ]; then
  echo "WARNING: a node clone/checkout/requirements step reported a problem. The CI import gate will decide pass/fail."
fi
exit 0
