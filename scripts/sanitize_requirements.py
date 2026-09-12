#!/usr/bin/env python3
"""Sanitize custom node requirements.txt to guarantee installation success:
1. Strips torch/torchvision/torchaudio/triton so nodes never clobber or conflict with cu128.
2. Normalizes any opencv-python variant to opencv-contrib-python-headless.
3. Remaps onnxruntime to onnxruntime-gpu.
4. Strips restrictive numpy<2 / numpy==1.* pins (our sitecustomize.py provides NumPy 1.x shims).
"""
import os
import re
import sys


def sanitize_line(line: str) -> str | None:
    line = line.strip()
    if not line or line.startswith('#'):
        return None

    # Preserve pip flags and URLs
    if line.startswith(('-', '@')):
        return line

    # Split package name from version and environment markers
    marker_split = line.split(';', 1)
    req_part = marker_split[0].strip()
    marker_part = ('; ' + marker_split[1].strip()) if len(marker_split) > 1 else ''

    # Match package name
    m = re.match(r'^([a-zA-Z0-9_\-\.]+)\s*(.*)$', req_part)
    if not m:
        return line

    pkg_raw = m.group(1)
    pkg = pkg_raw.lower().replace('_', '-')
    spec = m.group(2).strip()

    # Protect PyTorch cu128 stack from downgrade or conflict
    if pkg in ('torch', 'torchvision', 'torchaudio', 'triton'):
        return None

    # Enforce single headless contrib opencv
    if pkg in ('opencv-python', 'opencv-contrib-python', 'opencv-python-headless', 'opencv-contrib-python-headless'):
        return 'opencv-contrib-python-headless' + marker_part

    # Enforce GPU onnxruntime
    if pkg == 'onnxruntime':
        return 'onnxruntime-gpu' + (f' {spec}' if spec else '') + marker_part

    # Protect numpy 2.x: skip restrictive downgrade pins (sitecustomize.py provides backward compatibility)
    if pkg == 'numpy' and any(op in spec for op in ('<', '==1.')):
        return None

    return line


def sanitize_file(input_path: str, output_path: str | None = None) -> list[str]:
    if not os.path.isfile(input_path):
        return []

    with open(input_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()

    cleaned: list[str] = []
    seen = set()
    for raw_line in lines:
        clean = sanitize_line(raw_line)
        if clean and clean not in seen:
            seen.add(clean)
            cleaned.append(clean)

    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            for l in cleaned:
                f.write(l + '\n')

    return cleaned


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('usage: sanitize_requirements.py <input_requirements.txt> [output_path]', file=sys.stderr)
        sys.exit(1)

    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else None
    results = sanitize_file(src, dst)
    if not dst:
        for r in results:
            print(r)
