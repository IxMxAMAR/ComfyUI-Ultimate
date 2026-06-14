#!/usr/bin/env bash
# Boot ComfyUI headless and fail if any custom node fails to import or any
# expected pack is missing from the import log. Run inside the built image.
set -uo pipefail
cd /ComfyUI
LOG=/tmp/comfy_boot.log

echo "Booting ComfyUI (--cpu --quick-test-for-ci)..."
python main.py --cpu --quick-test-for-ci > "$LOG" 2>&1 || true
echo "----- import log tail -----"
tail -n 60 "$LOG"
echo "---------------------------"

rc=0
if grep -E "IMPORT FAILED" "$LOG"; then
  echo "::error::a custom node failed to import (see lines above)"
  rc=1
fi

while read -r pack; do
  case "$pack" in ''|\#*) continue ;; esac
  if ! grep -q -- "$pack" "$LOG"; then
    echo "::error::expected pack not seen in import log: $pack"
    rc=1
  fi
done < /opt/expected_packs.txt

if [ "$rc" -eq 0 ]; then
  echo "ALL 29 CUSTOM NODES IMPORTED OK"
fi
exit "$rc"
