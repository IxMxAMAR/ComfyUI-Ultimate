# ComfyUI Ultimate

**A batteries-included ComfyUI for RunPod.** CUDA 12.8, PyTorch 2.8 (cu128), Triton,
**SageAttention 2.2**, **FlashAttention 2.8.3** and **29 curated custom-node packs** pinned to exact
commits are baked in, so a pod boots straight into a fully-loaded ComfyUI. **No model weights ship**;
you pull those onto a volume that keeps them.

Image: `docker.io/ixmxamar/comfyui-ultimate:latest`

---

## Deploy

1. **Pick an RTX-class GPU** — RTX 4090 or **5090** recommended. One bundled node needs a real consumer
   RTX GPU, and SageAttention's Blackwell path targets the 5090.
2. **Attach a Network Volume mounted at `/workspace`.** Without one, every model and output lives in
   ephemeral container storage and is lost on restart.
3. **Ports** (already set here): HTTP `8188`, `8888`, `8080`, `8090`; TCP `22`.
4. *(Optional)* set `CIVITAI_API_KEY` and `HF_TOKEN` so gated downloads work unattended.
5. **Wait ~60–90 s**, then open ComfyUI — it is ready only once the log shows `To see the GUI go to:`.

## Services

| Service | Port | Type | What it is |
|---|---|---|---|
| **ComfyUI** | `8188` | HTTP | The main UI |
| **PodPanel** | `8090` | HTTP | Outputs gallery, zip downloads, and a model-setup script runner |
| **JupyterLab** | `8888` | HTTP | Terminal, file manager, notebooks — **no login by default** |
| **File Browser** | `8080` | HTTP | Lightweight web file manager — no auth |
| **SSH** | `22` | TCP | Add your key under *RunPod → Settings → SSH Public Keys* |

All bind `0.0.0.0`, reached at `https://<pod-id>-<port>.proxy.runpod.net`.

> **A click on the ComfyUI link can show 403** — ComfyUI's own CSRF middleware rejecting cross-site
> navigations, not a boot race or a browser cache. **This image patches it**, so the link works; on an
> older tag, paste the URL instead of clicking.

## Getting models (nothing is baked in)

No boot-time provisioning script: the image stays small and starts fast, and you choose what to pull.
Everything lands on `/workspace`, so it survives restarts.

**From inside ComfyUI** — no terminal needed:
- **Civicomfy** — search Civitai/HuggingFace, one-click into the right `models/<type>/` folder. Set
  `CIVITAI_API_KEY` for gated models.
- **ComfyUI-RunpodDirect** — paste any direct URL; multi-connection, queued, with progress.

**In bulk, from a preset script** — drop a `setup.sh` into **PodPanel** (`:8090`) and it runs it one
job at a time with a live log, or run it yourself:

```bash
bash setup.sh --dry-run    # show what it would do
bash setup.sh              # download into the right models/<type>/ folders
```

Uploaded scripts and logs live in `/workspace/model-setup/uploads/`, so the job list survives a
restart.

> ⚠️ **PodPanel runs whatever you give it** — as root, with your volume mounted, and no auth by
> default. Set `PODPANEL_TOKEN` to require `?token=…`, or `PODPANEL_ENABLE=0` to switch it off.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `CIVITAI_API_KEY` | — | Civitai downloads (Civicomfy, and PodPanel runs) |
| `HF_TOKEN` | — | HuggingFace token for gated downloads |
| `JUPYTER_TOKEN` | *(empty)* | Empty = **JupyterLab open**. Set a value to require a token |
| `PODPANEL_ENABLE` | `1` | Set to `0` to skip PodPanel |
| `PODPANEL_PORT` | `8090` | PodPanel's port |
| `PODPANEL_TOKEN` | *(empty)* | Empty = **PodPanel open**. Set a value to require `?token=…` |
| `COMFY_ARGS` | — | Extra flags for `python main.py` (e.g. `--lowvram`) |

## What persists

`/ComfyUI/models`, `output`, `input` and `user` are symlinked onto the network volume at `/workspace`
on first boot, so weights, outputs and settings survive a restart.

> A network volume is billed **even while the pod is stopped**. Delete it when you are done.

SageAttention 2.2 is the primary attention backend; prefer **KJNodes → "Patch Sage Attention"** over
the global `--use-sage-attention` flag, which can black-frame some WAN/Qwen models.

## Troubleshooting

**ComfyUI shows 403.** The CSRF middleware, already patched in this image — see above.

**A port stays "Initializing".** RunPod's readiness label lags (JupyterLab returns a redirect, not a
200). If `curl -sI localhost:<port>` answers on the pod, it is fine — just open the link.

**Models disappeared after a restart.** No Network Volume was attached at `/workspace`.

## Links

- **Source and full documentation** — <https://github.com/IxMxAMAR/ComfyUI-Ultimate>
- **Issues and requests** — <https://github.com/IxMxAMAR/ComfyUI-Ultimate/issues>
- **Tags** — `latest`, `cu128-torch2.8.0`, plus a per-commit SHA. CI rebuilds `latest` and **fails
  unless all 29 node packs import cleanly** offline.

MIT licensed. ComfyUI and the bundled custom nodes belong to their respective authors.
