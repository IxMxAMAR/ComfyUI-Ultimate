#!/usr/bin/env python3
"""Configures ComfyUI-Manager to protect core environment and ensure smooth node installs:
1. Populates pip_overrides.json (remaps onnxruntime -> onnxruntime-gpu, opencv-python -> opencv-contrib-python-headless).
2. Populates pip_blacklist.list (protects torch/torchvision/torchaudio/triton from accidental install/downgrade).
3. Updates config.ini with downgrade_blacklist and sets use_uv=False for better package tolerance.
"""
import configparser
import os
import shutil
import sys

OVERRIDES_SRC = os.environ.get("OVERRIDES_SRC", "/opt/pip_overrides.json")
BLACKLIST_SRC = os.environ.get("BLACKLIST_SRC", "/opt/pip_blacklist.list")


def setup_manager_dir(mgr_dir: str):
    os.makedirs(mgr_dir, exist_ok=True)

    # 1. pip_overrides.json
    dst_overrides = os.path.join(mgr_dir, "pip_overrides.json")
    if os.path.exists(OVERRIDES_SRC):
        shutil.copyfile(OVERRIDES_SRC, dst_overrides)

    # 2. pip_blacklist.list
    dst_blacklist = os.path.join(mgr_dir, "pip_blacklist.list")
    if os.path.exists(BLACKLIST_SRC):
        shutil.copyfile(BLACKLIST_SRC, dst_blacklist)

    # 3. config.ini
    cfg_path = os.path.join(mgr_dir, "config.ini")
    cfg = configparser.ConfigParser()
    if os.path.exists(cfg_path):
        try:
            cfg.read(cfg_path)
        except Exception:
            pass

    if not cfg.has_section("default"):
        cfg.add_section("default")

    current_bl = cfg.get("default", "downgrade_blacklist", fallback="")
    bl_items = set(x.strip() for x in current_bl.split(",") if x.strip())
    bl_items.update(["torch", "torchvision", "torchaudio", "triton", "numpy"])
    cfg.set("default", "downgrade_blacklist", ",".join(sorted(bl_items)))
    cfg.set("default", "use_uv", "False")

    with open(cfg_path, "w", encoding="utf-8") as f:
        cfg.write(f)


if __name__ == "__main__":
    target_dirs = sys.argv[1:] if len(sys.argv) > 1 else [
        "/ComfyUI/user/__manager",
        "/ComfyUI/user/default/ComfyUI-Manager",
    ]
    for d in target_dirs:
        try:
            setup_manager_dir(d)
        except Exception as e:
            print(f"WARN: could not configure manager directory {d}: {e}", file=sys.stderr)
