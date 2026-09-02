#!/usr/bin/env bash
# CI gate for the custom-node manifest: prove the restore path works inside the
# real image, and — more importantly — that it cannot damage the baked packs or
# stop the pod booting.
set -uo pipefail

export WORKSPACE=/tmp/ci-nodes-ws
rm -rf "$WORKSPACE"; mkdir -p "$WORKSPACE"

fail() { echo "FAIL: $*"; exit 1; }

command -v comfy-nodes >/dev/null || fail "comfy-nodes is not on PATH"

# 1. First boot with no manifest must create one and exit clean.
bash /opt/scripts/restore_nodes.sh || fail "restore exited non-zero on a fresh volume"
[ -f "$WORKSPACE/comfy_nodes.txt" ] || fail "restore did not create the manifest"
echo "ok: fresh volume creates a manifest"

# 2. Nothing pinned yet, so nothing is claimed as installed.
comfy-nodes list | grep -q "Nothing pinned" || fail "empty manifest should report nothing pinned"
echo "ok: empty manifest reports cleanly"

# 3. A baked pack listed in the manifest must be refused, not reinstalled over.
baked="$(head -1 /opt/expected_packs.txt)"
before="$(git -C "/ComfyUI/custom_nodes/$baked" rev-parse HEAD 2>/dev/null || echo none)"
echo "$baked https://github.com/example/$baked.git deadbeef" >> "$WORKSPACE/comfy_nodes.txt"
bash /opt/scripts/restore_nodes.sh | grep -q "already baked" || fail "baked pack was not skipped"
after="$(git -C "/ComfyUI/custom_nodes/$baked" rev-parse HEAD 2>/dev/null || echo none)"
[ "$before" = "$after" ] || fail "a baked pack was modified by the restore ($before -> $after)"
echo "ok: baked pack '$baked' protected from the manifest"

# 4. An unreachable repo must be survivable — this is the pod-boot guarantee.
echo "zz-broken https://github.com/this-org-does-not-exist-9z/zz-broken.git HEAD" >> "$WORKSPACE/comfy_nodes.txt"
if ! bash /opt/scripts/restore_nodes.sh >/dev/null 2>&1; then
  fail "restore exited non-zero on an unreachable repo — this would break pod boot"
fi
[ ! -d "/ComfyUI/custom_nodes/zz-broken" ] || fail "a failed clone left a broken directory behind"
echo "ok: unreachable repo is skipped without failing the boot"

# 5. The manifest never lists the image's own packs after a freeze.
comfy-nodes freeze >/dev/null 2>&1
while read -r name _rest; do
  case "$name" in ''|'#'*) continue ;; esac
  grep -qxF "$name" /opt/expected_packs.txt && fail "freeze recorded baked pack $name"
done < "$WORKSPACE/comfy_nodes.txt"
echo "ok: freeze excludes the baked packs"

echo "nodes gate PASS"
