# ComfyUI Ultimate

**A batteries-included ComfyUI for RunPod.** The whole heavy stack is baked in — CUDA 12.8,
PyTorch 2.8 (cu128), Triton, **SageAttention 2.2**, **FlashAttention 2.8.3**, and **29 curated
custom-node packs** pinned to exact commits — so a pod boots straight into a fully-loaded
ComfyUI. **No model weights are shipped**; you pull those on demand, onto a volume that keeps them.

| | |
|---|---|
| **Image** | `docker.io/ixmxamar/comfyui-ultimate:latest` |
| **GPU** | RTX 4090 / **5090** recommended — a consumer RTX card is required by one node |
| **Volume** | attach a Network Volume at `/workspace` |
| **First boot** | ~60–90 s while PyTorch and the 29 node packs load |

---

## Deploy

1. **Pick an RTX-class GPU** — RTX 4090 or **5090** recommended. The RTX Video Super Resolution
   node needs a real consumer RTX GPU, and SageAttention's Blackwell path targets the 5090.
2. **Attach a Network Volume mounted at `/workspace`.** Without one, every model and output lives
   in ephemeral container storage and is lost on restart.
3. **Ports** (already set on this template): HTTP `8188`, `8888`, `8080`, `8090`; TCP `22`.
4. *(Optional)* set `CIVITAI_API_KEY` and `HF_TOKEN` so gated downloads work unattended.
5. **Wait ~60–90 seconds**, then open ComfyUI — it is ready only once the pod log shows
   `To see the GUI go to:`.

---

## Services

| Service | Port | Type | What it is |
|---|---|---|---|
| **ComfyUI** | `8188` | HTTP | The main UI |
| **PodPanel** | `8090` | HTTP | Outputs gallery, zip downloads, and a drop-in runner for model-setup scripts |
| **JupyterLab** | `8888` | HTTP | Terminal, file manager, notebooks — **no login by default** |
| **File Browser** | `8080` | HTTP | Lightweight web file manager — no auth |
| **SSH** | `22` | TCP | Add your key under *RunPod → Settings → SSH Public Keys* |

All web services bind `0.0.0.0` and are reached through RunPod's proxy at
`https://<pod-id>-<port>.proxy.runpod.net`.

> **A click on the ComfyUI link can show 403.** That is ComfyUI's own CSRF middleware rejecting
> cross-site navigations — not a startup-timing problem and not a browser cache, so incognito and
> hard-refresh do not help. **This image patches it**, so the link works; on an older tag, paste
> the URL into the address bar or bookmark it instead of clicking. The evidence, and why it is
> neither RunPod's fault nor a boot race, is in
> [docs/reverse-proxy-403.md](https://github.com/IxMxAMAR/ComfyUI-Ultimate/blob/main/docs/reverse-proxy-403.md).

---

## Getting models (nothing is baked in)

There is **no boot-time provisioning script** — the image stays small and starts fast, and you
decide what to pull. Everything lands on the `/workspace` volume, so it survives restarts.

**1. From inside ComfyUI** — works for everyone, no terminal needed:

- **Civicomfy** — search Civitai and HuggingFace and download into the correct `models/<type>/`
  folder. Set `CIVITAI_API_KEY` so it can fetch gated and account-only models headlessly.
- **ComfyUI-RunpodDirect** — paste any direct URL (Civitai / HuggingFace / generic); it streams to
  the pod with multi-connection downloads, a queue, and progress.

**2. In bulk, with a preset script and PodPanel** — for a fresh pod, a team, or a repeatable setup:

```bash
bash setup.sh --dry-run     # show exactly what it would do
bash setup.sh               # download everything into the right models/<type>/ folders
```

Drop that `setup.sh` into **PodPanel** (`:8090`) and it runs it for you, one job at a time,
streaming the log live. Uploaded scripts, logs and exit codes stay in
`/workspace/model-setup/uploads/`, so the job list is rebuilt after a restart.

> ⚠️ **PodPanel runs whatever you give it** — as root, with your volume mounted, and with no
> authentication by default (the same posture as JupyterLab and File Browser on this image). Set
> `PODPANEL_TOKEN` to require `?token=…`, or `PODPANEL_ENABLE=0` to switch it off entirely.

---

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
| `WORKSPACE` | `/workspace` | Persistent volume mount point |
| `PUBLIC_KEY` | — | SSH public key; RunPod injects it from your account |

---

## What persists

On first boot these are symlinked onto the network volume, so weights, outputs, inputs and
settings all survive a restart:

```
/ComfyUI/models  ->  /workspace/models
/ComfyUI/output  ->  /workspace/output
/ComfyUI/input   ->  /workspace/input
/ComfyUI/user    ->  /workspace/user
```

> A network volume is billed **even while the pod is stopped**. Delete it when you are finished
> with it.

---

## Attention backends

- **SageAttention 2.2** is the primary accelerator. Prefer **KJNodes → "Patch Sage Attention"**
  over the global `--use-sage-attention` flag — the global flag can produce black frames on some
  WAN/Qwen models.
- **FlashAttention 2.8.3** is installed as an optional backend (FA3/FA4 do not support consumer
  Blackwell).
- **PyTorch SDPA** is always available as a fallback.

---

## Troubleshooting

**A port stays "Initializing" in RunPod.** RunPod's readiness label lags — JupyterLab returns a
redirect rather than a 200. If `curl -sI localhost:<port>` answers on the pod, the service is fine;
just open the link.

**ComfyUI shows 403 Forbidden.** See the note under [Services](#services) — it is the CSRF
middleware, this image patches it, and incognito or a hard refresh will not change it.

**The RTX Video Super Resolution node "failed to import".** That node loads CUDA at import and
needs a real RTX GPU. It is skipped in CI (which has no GPU) and loads normally on your pod.

**Models disappeared after a restart.** No Network Volume was attached at `/workspace`.

**A custom node will not install.** ComfyUI-Manager is set up to protect the pinned CUDA/PyTorch
stack — a downgrade blacklist, requirement sanitisation, and a NumPy 1.x compatibility shim. If a
node still fights it, open an issue with the pack name.

---

## Links

- **Source, full documentation and the list of all 29 node packs** —
  <https://github.com/IxMxAMAR/ComfyUI-Ultimate>
- **Issues and feature requests** — <https://github.com/IxMxAMAR/ComfyUI-Ultimate/issues>
- **Tags** — `latest`, `cu128-torch2.8.0`, and a per-commit SHA tag. `latest` is rebuilt by CI,
  which **fails the build unless all 29 node packs import cleanly** with no network access.

MIT licensed. ComfyUI and the bundled custom nodes belong to their respective authors.
