#!/usr/bin/env bash
# RunPod Pod entrypoint: wire the network volume, start SSH + JupyterLab +
# filebrowser, then run ComfyUI in the foreground.
set -u
export PATH="/opt/venv/bin:$PATH"

WORKSPACE="${WORKSPACE:-/workspace}"
echo "[start] wiring persistent dirs onto $WORKSPACE"
for d in models output input user; do
  mkdir -p "$WORKSPACE/$d"
  if [ -d "/ComfyUI/$d" ] && [ ! -L "/ComfyUI/$d" ]; then
    cp -an "/ComfyUI/$d/." "$WORKSPACE/$d/" 2>/dev/null || true
    rm -rf "/ComfyUI/$d"
  fi
  ln -sfn "$WORKSPACE/$d" "/ComfyUI/$d"
done

# --- SSH (RunPod injects PUBLIC_KEY) ---
if [ -n "${PUBLIC_KEY:-}" ]; then
  mkdir -p /root/.ssh && chmod 700 /root/.ssh
  echo "$PUBLIC_KEY" >> /root/.ssh/authorized_keys && chmod 600 /root/.ssh/authorized_keys
fi
mkdir -p /run/sshd && /usr/sbin/sshd && echo "[start] sshd up on :22" || echo "[start] WARN sshd failed"

# --- JupyterLab (open/no-auth by default; set JUPYTER_TOKEN to require one) ---
JUPYTER_TOKEN="${JUPYTER_TOKEN:-}"
nohup jupyter lab --allow-root --ip=0.0.0.0 --port=8888 --no-browser \
  --ServerApp.token="$JUPYTER_TOKEN" --ServerApp.password='' \
  --ServerApp.root_dir="$WORKSPACE" \
  --ServerApp.allow_origin='*' --ServerApp.allow_remote_access=True \
  --ServerApp.trust_xheaders=True --ServerApp.disable_check_xsrf=True \
  > /var/log/jupyter.log 2>&1 &
if [ -n "$JUPYTER_TOKEN" ]; then
  echo "[start] JupyterLab up on :8888 (token: $JUPYTER_TOKEN)"
else
  echo "[start] JupyterLab up on :8888 (no auth)"
fi

# --- filebrowser (noauth, writable db in /tmp) ---
if command -v filebrowser >/dev/null 2>&1; then
  nohup filebrowser -r "$WORKSPACE" -a 0.0.0.0 -p 8080 --noauth -d /tmp/filebrowser.db \
    > /var/log/filebrowser.log 2>&1 &
  echo "[start] filebrowser up on :8080"
else
  echo "[start] filebrowser not installed, skipping :8080"
fi

# --- Runtime Compatibility & ComfyUI-Manager Protection ---
# 1. Ensure sitecustomize.py is loaded in venv (NumPy 1.x backwards compatibility shim for older nodes)
if [ -f /opt/scripts/sitecustomize.py ]; then
  cp -f /opt/scripts/sitecustomize.py /opt/venv/lib/python3.12/site-packages/sitecustomize.py 2>/dev/null || true
fi

# 2. Seed ComfyUI-Manager config & overrides (remaps opencv/onnxruntime, prevents torch/numpy downgrade)
python /opt/scripts/configure_manager.py "$WORKSPACE/user/__manager" "$WORKSPACE/user/default/ComfyUI-Manager" \
  || echo "[start] WARN manager configuration reported an error; continuing"

# --- Restore user-pinned custom nodes onto LOCAL disk (see comfy_nodes.txt) ---
# Nodes installed at runtime via ComfyUI-Manager live on the pod's local disk and
# die with the pod. They are restored here from a manifest on the volume rather
# than by symlinking custom_nodes onto it, so node code still imports at local
# NVMe speed. Never fatal: a dead node repo must not stop the pod booting.
bash /opt/scripts/restore_nodes.sh || echo "[start] WARN node restore reported an error; continuing"

# 3. Quick OpenCV normalization check (in case a restored node brought in GUI opencv-python)
if [ "$(python -c 'import importlib.metadata as md; print(len([d for d in ("opencv-python", "opencv-python-headless", "opencv-contrib-python") if md.distribution(d)]))' 2>/dev/null || echo 0)" -gt 0 ]; then
  echo "[start] Normalizing OpenCV variants..."
  pip uninstall -y opencv-python opencv-python-headless opencv-contrib-python >/dev/null 2>&1 || true
  pip install --no-deps opencv-contrib-python-headless==4.11.0.86 >/dev/null 2>&1 || true
fi

# --- ComfyUI (foreground). Attention: prefer the KJNodes 'Patch Sage Attention'
#     node over the global --use-sage-attention flag. Override via COMFY_ARGS. ---
cd /ComfyUI
COMFY_ARGS="${COMFY_ARGS:---enable-triton-backend}"
echo "[start] launching ComfyUI on :8188 ($COMFY_ARGS)"
exec python main.py --listen 0.0.0.0 --port 8188 ${COMFY_ARGS}
