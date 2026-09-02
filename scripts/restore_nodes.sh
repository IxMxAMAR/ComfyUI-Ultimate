#!/usr/bin/env bash
# Restore the custom nodes listed in /workspace/comfy_nodes.txt onto LOCAL disk,
# then reinstall their Python requirements.
#
# Deliberately NOT `set -e`: a node whose repo has moved, been deleted or gone
# private must never stop the pod from booting. Every failure is logged and
# skipped, and ComfyUI still comes up with everything that did work.

. /opt/scripts/node_manifest.sh

WORKSPACE="${WORKSPACE:-/workspace}"
MANIFEST="$(cn_manifest_path)"
LOG="$(cn_log_path)"

# Wheel cache on the volume, so the second boot is far faster than the first.
export PIP_CACHE_DIR="${PIP_CACHE_DIR:-$WORKSPACE/pip-cache}"
mkdir -p "$PIP_CACHE_DIR"

log() { echo "[nodes] $*" | tee -a "$LOG"; }

if [ ! -f "$MANIFEST" ]; then
  cat > "$MANIFEST" <<'EOF'
# comfy_nodes.txt — custom nodes restored onto this pod at every boot.
#
# The 29 node packs bundled in the image are NOT listed here and must not be;
# they are already installed and load faster than anything restored at runtime.
# This file is only for nodes you add yourself.
#
# Format:  <dirname> <git_url> <commit_sha>
#   - the sha may be omitted to track the default branch
#   - a bare git URL works too; the directory name is inferred
#
# You rarely need to edit this by hand. Install nodes through ComfyUI-Manager as
# usual, then run:   comfy-nodes freeze
# which records everything you have added, at the exact commit you are running.
EOF
  log "created $MANIFEST (no custom nodes pinned yet)"
  exit 0
fi

count=0; ok=0; failed=0
while read -r name url sha; do
  [ -n "$name" ] || continue
  count=$((count + 1))
  dest="$COMFY_NODES_DIR/$name"

  if cn_is_baked "$name"; then
    log "SKIP $name — already baked into the image (remove it from the manifest)"
    continue
  fi

  if [ -d "$dest/.git" ]; then
    cur="$(git -C "$dest" rev-parse HEAD 2>/dev/null)"
    if [ "$sha" != "HEAD" ] && [ "$cur" = "$sha" ]; then
      log "ok   $name already at $sha"
      ok=$((ok + 1))
      continue
    fi
    rm -rf "$dest"
  fi

  if [ "$sha" = "HEAD" ]; then
    git clone --depth 1 "$url" "$dest" >>"$LOG" 2>&1
  else
    git init -q "$dest" >>"$LOG" 2>&1 \
      && git -C "$dest" remote add origin "$url" >>"$LOG" 2>&1 \
      && git -C "$dest" fetch -q --depth 1 origin "$sha" >>"$LOG" 2>&1 \
      && git -C "$dest" checkout -q FETCH_HEAD >>"$LOG" 2>&1
  fi
  if [ $? -ne 0 ] || [ ! -d "$dest" ]; then
    log "FAIL $name — could not fetch $url ($sha); skipping"
    rm -rf "$dest"
    failed=$((failed + 1))
    continue
  fi

  if [ -f "$dest/requirements.txt" ]; then
    # PIP_CONSTRAINT is set image-wide, so a node requirement still cannot
    # downgrade torch out from under CUDA.
    if pip install --no-cache-dir=false -r "$dest/requirements.txt" >>"$LOG" 2>&1; then
      log "ok   $name installed with requirements"
    else
      log "WARN $name installed but its requirements failed — see $LOG"
    fi
  else
    log "ok   $name installed"
  fi
  ok=$((ok + 1))
done <<EOF
$(cn_parse "$MANIFEST")
EOF

log "restored $ok/$count pinned node(s), $failed failed"
exit 0
