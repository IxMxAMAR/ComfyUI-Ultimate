#!/usr/bin/env python3
"""Neutralize ComfyUI-Manager's PIPFixer.torch_rollback.

Manager's fix_broken() runs on every startup; its hardcoded version map maxes at
torch 2.7.0, so our 2.8.0+cu128 triggers a --force PyPI reinstall that would wipe
the sm_120 build. Rewrite torch_rollback() to a no-op. Idempotent.
"""
import glob
import re

patched = 0
candidates = (
    glob.glob("/ComfyUI/custom_nodes/*/glob/manager_util.py")
    + glob.glob("/ComfyUI/custom_nodes/*/manager_util.py")
)
for f in candidates:
    try:
        src = open(f, encoding="utf-8").read()
    except OSError:
        continue
    if "def torch_rollback" in src and "# PATCHED-NOOP" not in src:
        src = re.sub(
            r"def torch_rollback\([^)]*\):",
            "def torch_rollback(*a, **k):  # PATCHED-NOOP\n        return",
            src,
            count=1,
        )
        open(f, "w", encoding="utf-8").write(src)
        print("patched torch_rollback in", f)
        patched += 1

print(f"patch_manager: {patched} file(s) patched")
