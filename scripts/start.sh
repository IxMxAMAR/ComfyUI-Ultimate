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

# --- ComfyUI (foreground). Attention: prefer the KJNodes 'Patch Sage Attention'
#     node over the global --use-sage-attention flag. Override via COMFY_ARGS. ---
cd /ComfyUI
echo "[start] launching ComfyUI on :8188"
exec python main.py --listen 0.0.0.0 --port 8188 ${COMFY_ARGS:-}
