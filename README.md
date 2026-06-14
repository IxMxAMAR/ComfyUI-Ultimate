# ComfyUI-Ultimate

A **batteries-included [ComfyUI](https://github.com/comfyanonymous/ComfyUI) Docker image for RunPod** — the entire heavy software stack (CUDA, PyTorch, Triton, SageAttention, FlashAttention, and **29 curated custom-node packs**) is baked in, so a pod boots straight into a fully-loaded ComfyUI. **No model weights are shipped** — you pull those on demand from inside the UI.

Built automatically by GitHub Actions and published to Docker Hub:

> ### `docker.io/ixmxamar/comfyui-ultimate:latest`

[![build](https://github.com/IxMxAMAR/ComfyUI-Ultimate/actions/workflows/build.yml/badge.svg)](https://github.com/IxMxAMAR/ComfyUI-Ultimate/actions/workflows/build.yml)

---

## Table of contents
- [Why this image](#why-this-image)
- [What's inside](#whats-inside)
- [Bundled custom nodes (29)](#bundled-custom-nodes-29)
- [Quick start on RunPod](#quick-start-on-runpod)
- [Services & ports](#services--ports)
- [Environment variables](#environment-variables)
- [Getting models](#getting-models)
- [Persistent storage](#persistent-storage)
- [SSH access](#ssh-access)
- [Attention backends (SageAttention / FlashAttention)](#attention-backends)
- [Troubleshooting](#troubleshooting)
- [How the image is built](#how-the-image-is-built)
- [Build it yourself](#build-it-yourself)
- [Tags](#tags)
- [Roadmap](#roadmap)
- [Credits & license](#credits--license)

---

## Why this image

Most ComfyUI cloud images either ship nothing (you install everything by hand) or bake in tens of gigabytes of models you didn't ask for. This one takes the middle path that actually works on cloud GPUs:

- **Software baked, models not.** Every painful-to-compile dependency (Triton, SageAttention, FlashAttention, the CUDA stack) and 29 popular custom-node packs are pre-installed and version-locked. Models are pulled at runtime into a persistent volume.
- **Blackwell-ready.** Built on CUDA 12.8 / PyTorch cu128, so it runs on the **RTX 5090 (sm_120)** as well as Ampere → Hopper.
- **Dependency-hardened.** A single pinned `constraints.txt` is enforced on every install so no custom node can silently swap your CUDA-enabled torch for a CPU build. The CI **fails the build unless all 29 nodes import cleanly.**

---

## What's inside

| Component | Version / detail |
|---|---|
| Base image | `nvidia/cuda:12.8.0-cudnn-devel-ubuntu22.04` |
| Python | 3.12 |
| PyTorch | `2.8.0+cu128` (`torchvision 0.23.0` / `torchaudio 2.8.0`) |
| Triton | `3.4.0` |
| NumPy | `2.2.6` |
| GPU coverage | sm_80 / 86 / 89 / 90 / **120** (Ampere → Ada → Hopper → **Blackwell / RTX 5090**) |
| Attention | **SageAttention 2.2** + **FlashAttention 2.8.3** + PyTorch SDPA |
| Custom nodes | **29 packs**, pinned to exact commits |
| Web services | ComfyUI · JupyterLab · File Browser · SSH |
| Image size | ~13 GB compressed |

---

## Bundled custom nodes (29)

Every pack is pinned to an exact commit (see [`node_pins.txt`](node_pins.txt)) for reproducibility.

### Core & utility
| Pack | What it adds |
|---|---|
| [ComfyUI-Manager](https://github.com/ltdrdata/ComfyUI-Manager) | Install/manage custom nodes & models from the UI |
| [rgthree-comfy](https://github.com/rgthree/rgthree-comfy) | Power nodes, reroutes, fast group muting, progress bars |
| [ComfyUI-Custom-Scripts](https://github.com/pythongosssss/ComfyUI-Custom-Scripts) | Quality-of-life UI tweaks, autocomplete, image feed |
| [ComfyUI-KJNodes](https://github.com/kijai/ComfyUI-KJNodes) | Huge utility set incl. the **Patch SageAttention** node |
| [ComfyUI_essentials](https://github.com/cubiq/ComfyUI_essentials) | Image/mask/sampling essentials |
| [was-node-suite-comfyui](https://github.com/WASasquatch/was-node-suite-comfyui) | 200+ image/text/logic nodes |
| [ComfyUI-Crystools](https://github.com/crystian/ComfyUI-Crystools) | Live CPU/GPU/VRAM resource monitor |
| [ComfyUI-Easy-Use](https://github.com/yolain/ComfyUI-Easy-Use) | Streamlined all-in-one workflow nodes |
| [cg-use-everywhere](https://github.com/chrisgoringe/cg-use-everywhere) | Broadcast a value to every matching input |

### Detailing & upscaling
| Pack | What it adds |
|---|---|
| [ComfyUI-Impact-Pack](https://github.com/ltdrdata/ComfyUI-Impact-Pack) | Detailers, detectors, SEGS pipeline |
| [ComfyUI-Impact-Subpack](https://github.com/ltdrdata/ComfyUI-Impact-Subpack) | UltralyticsDetector (YOLO) for Impact |
| [ComfyUI_UltimateSDUpscale](https://github.com/ssitu/ComfyUI_UltimateSDUpscale) | Tiled SD upscaling |
| [ComfyUI-Inspire-Pack](https://github.com/ltdrdata/ComfyUI-Inspire-Pack) | Prompt/scheduling/regional tools |
| [efficiency-nodes-comfyui](https://github.com/jags111/efficiency-nodes-comfyui) | Compact efficient samplers, XY plots |

### Control & conditioning
| Pack | What it adds |
|---|---|
| [comfyui_controlnet_aux](https://github.com/Fannovel16/comfyui_controlnet_aux) | ControlNet preprocessors (depth, pose, lineart…) |
| [ComfyUI-Advanced-ControlNet](https://github.com/Kosinkadink/ComfyUI-Advanced-ControlNet) | Advanced/timestep ControlNet scheduling |
| [ComfyUI_IPAdapter_plus](https://github.com/cubiq/ComfyUI_IPAdapter_plus) | IP-Adapter image prompting |

### Video & animation
| Pack | What it adds |
|---|---|
| [ComfyUI-VideoHelperSuite](https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite) | Load/combine video, frame I/O |
| [ComfyUI-Frame-Interpolation](https://github.com/Fannovel16/ComfyUI-Frame-Interpolation) | RIFE/FILM frame interpolation |
| [ComfyUI-AnimateDiff-Evolved](https://github.com/Kosinkadink/ComfyUI-AnimateDiff-Evolved) | AnimateDiff motion modules |
| [ComfyUI-WanVideoWrapper](https://github.com/kijai/ComfyUI-WanVideoWrapper) | WAN 2.x video generation |

### Model formats & vision
| Pack | What it adds |
|---|---|
| [ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF) | Run GGUF-quantized UNet/CLIP |
| [ComfyUI-Florence2](https://github.com/kijai/ComfyUI-Florence2) | Florence-2 captioning / detection |
| [ComfyUI-segment-anything-2](https://github.com/kijai/ComfyUI-segment-anything-2) | SAM 2 segmentation |
| [ComfyUI-RMBG](https://github.com/1038lab/ComfyUI-RMBG) | Background removal (RMBG / BiRefNet / SAM) |
| [ComfyUI-Utility-MegaPack](https://github.com/IxMxAMAR/ComfyUI-Utility-MegaPack) | 156 utility ops across 7 nodes, 11 themes |
| [Nvidia RTX Nodes](https://github.com/Comfy-Org/Nvidia_RTX_Nodes_ComfyUI) | **RTX Video Super Resolution** (RTX GPUs only) |

### Model downloaders (no provisioning scripts needed)
| Pack | What it adds |
|---|---|
| [Civicomfy](https://github.com/MoonGoblinDev/Civicomfy) | Search & download Civitai/HF models from the UI |
| [ComfyUI-RunpodDirect](https://github.com/MadiatorLabs/ComfyUI-RunpodDirect) | Paste any URL → multi-connection download straight to the pod |

---

## Quick start on RunPod

1. **Create a Pod** (or a Template) using the image:
   ```
   ixmxamar/comfyui-ultimate:latest
   ```
2. **Pick an RTX-class GPU** — RTX 4090 / **5090** recommended. (The RTX Video Super Resolution node needs a consumer RTX GPU; SageAttention's Blackwell path targets the 5090.)
3. **Expose ports** — HTTP: `8188`, `8888`, `8080`; TCP: `22` (see [Services & ports](#services--ports)).
4. **Attach a Network Volume** mounted at `/workspace` (so models & outputs persist).
5. **(Optional) Set env vars** — `CIVITAI_API_KEY`, `HF_TOKEN` (see [Environment variables](#environment-variables)).
6. Wait ~60–90s for first boot (ComfyUI loads torch + 29 node packs), then open the **ComfyUI** link.

> ⏱️ **First boot takes ~60–90 seconds** because the image loads PyTorch and all 29 node packs. **Open the ComfyUI link only after** the pod log shows `To see the GUI go to:`. See [Troubleshooting](#troubleshooting) if you get a 403.

---

## Services & ports

| Service | Port | Type | Notes |
|---|---|---|---|
| **ComfyUI** | `8188` | HTTP | The main UI |
| **JupyterLab** | `8888` | HTTP | File manager + terminal + notebooks — **no login by default** |
| **File Browser** | `8080` | HTTP | Lightweight web file manager (no auth) |
| **SSH** | `22` | **TCP** | Add under *TCP ports*; needs an SSH key (see [SSH access](#ssh-access)) |

All web services bind `0.0.0.0` and are reached through RunPod's proxy (`https://<pod-id>-<port>.proxy.runpod.net`).

---

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `CIVITAI_API_KEY` | — | Lets **Civicomfy** download from Civitai (set for unattended/cloud use) |
| `HF_TOKEN` | — | HuggingFace token for gated model downloads |
| `JUPYTER_TOKEN` | *(empty)* | Empty = **JupyterLab open / no login**. Set a value to require a token |
| `PUBLIC_KEY` | — | SSH public key (RunPod injects this automatically from your account) |
| `COMFY_ARGS` | — | Extra args appended to `python main.py` (e.g. `--lowvram`) |
| `WORKSPACE` | `/workspace` | Persistent volume mount point |

---

## Getting models

**No models are baked in and there is no boot-time provisioning script.** Pull what you need from inside the running ComfyUI UI:

- **Civicomfy** — search Civitai (and HuggingFace), one-click download into the correct `models/<type>/` folder. Set `CIVITAI_API_KEY` so it can fetch gated/account models headlessly.
- **ComfyUI-RunpodDirect** — paste any direct URL (Civitai / HuggingFace / generic) and it streams to the pod with fast multi-connection downloads, a queue, and progress.

Everything downloads onto the `/workspace` volume, so it survives pod restarts.

---

## Persistent storage

These directories are symlinked onto the `/workspace` network volume on first boot, so weights, outputs, inputs, and user settings persist:

```
/ComfyUI/models   ->  /workspace/models
/ComfyUI/output   ->  /workspace/output
/ComfyUI/input    ->  /workspace/input
/ComfyUI/user     ->  /workspace/user
```

Always attach a Network Volume at `/workspace` for anything you want to keep.

---

## SSH access

1. In the RunPod template, add port **`22` under *TCP ports*** (not HTTP).
2. Save your **SSH public key** in *RunPod → Settings → SSH Public Keys*. RunPod injects it as `PUBLIC_KEY`, which the image installs into `/root/.ssh/authorized_keys` at boot.
3. Connect using the command shown on the pod's **Connect** tab:
   ```
   ssh root@<host> -p <mapped-port> -i ~/.ssh/your_key
   ```

---

## Attention backends

- **SageAttention 2.2** is the primary accelerator. Prefer the **KJNodes → "Patch Sage Attention"** node over the global `--use-sage-attention` flag — the global flag can produce black frames on some WAN/Qwen models.
- **FlashAttention 2.8.3** is installed as an optional backend (FA2; FA3/FA4 don't support consumer Blackwell).
- **PyTorch SDPA** is always available as a fallback.

> On RTX 5090, SageAttention runs via its sm_89/fp8-compatible kernels (the build that the WanVideoWrapper community uses on 50-series). If you ever hit a kernel error on Blackwell, open an issue — a from-source `sm_120` build path exists.

---

## Troubleshooting

### ComfyUI shows **403 Forbidden** but Jupyter/File Browser work
This is the #1 gotcha and it's **not the image** — ComfyUI is the slowest service to start (it loads torch + 29 node packs, ~60–90s), while Jupyter/File Browser are up in seconds. If you click the ComfyUI link *during* that startup window, RunPod returns a 403 **and your browser caches it** for that subdomain — so it keeps showing 403 even after ComfyUI is ready.

**Fix:**
- Open the ComfyUI link in an **Incognito/Private window** (or hard-refresh with `Ctrl+Shift+R`). It will load.
- Going forward, wait until the pod log shows `To see the GUI go to:` before opening ComfyUI.

You can verify ComfyUI is healthy from a terminal (Jupyter/SSH):
```bash
curl -sI http://localhost:8188/ | head -1   # expect: HTTP/1.1 200 OK
```

### A port stays "Initializing" in RunPod
RunPod's readiness label can lag (e.g. Jupyter returns a redirect, not a 200). If the service answers locally (`curl -sI localhost:<port>`), it's fine — just open the link.

### RTX Video Super Resolution node "failed to import"
That node (`nvidia-vfx`) loads CUDA at import and **only works on a real RTX GPU**. It is intentionally skipped in CI (which has no GPU) and will load on your pod.

### Models disappear after a restart
Attach a Network Volume at `/workspace`. Without it, downloads live in ephemeral container storage.

---

## How the image is built

The hard part of a 29-pack ComfyUI image is dependency conflicts. The strategy:

1. **One pinned `constraints.txt`** ([file](constraints.txt)) hard-pins every ABI-sensitive package (torch, numpy, opencv, onnxruntime, the HuggingFace stack…) and is applied to **every** pip/uv install via `PIP_CONSTRAINT` — so no node can move torch off the cu128 build.
2. **Deterministic install order** — torch (from the cu128 index) first, then attention backends, then a pre-baked ABI set, then ComfyUI core, then the 29 nodes, then a final opencv/onnxruntime normalization to a single variant.
3. **CI quality gates** — `smoke_test.py` runs *inside* the build (asserts single cv2 variant, numpy 2.2, torch cu128, HF coherence), and a **node-import gate** boots ComfyUI headless and **fails the build unless all 29 packs import**. The image is pushed only if both gates pass.

Full design rationale: [`docs/superpowers/specs/`](docs/superpowers/specs/).

---

## Build it yourself

CI ([`.github/workflows/build.yml`](.github/workflows/build.yml)) builds on every push to `main`, plus `workflow_dispatch` and `v*` tags. To build for your own Docker Hub:

1. Fork the repo.
2. Add repo secrets `DOCKERHUB_USER` and `DOCKERHUB_TOKEN` (a Read+Write+Delete access token).
3. Edit the `IMAGE` env in `build.yml` to your namespace.
4. Push to `main` (or run the workflow manually).

Local build (needs ~50 GB free disk + an NVIDIA toolchain to fully exercise it):
```bash
docker build -t comfyui-ultimate .
```

---

## Tags

| Tag | Meaning |
|---|---|
| `latest` | Newest build from `main` |
| `cu128-torch2.8.0` | Pinned to the torch line; moves only on a torch bump |
| `<git-sha>` | Immutable, reproducible build |

---

## Roadmap

- **M2** — slim the image (runtime base / multi-stage), RunPod template doc, optional GPU smoke test.
- **M3** — Serverless mode (`handler.py`) on the same image for autoscaling API endpoints.
- Optional `WITH_FACEID` build flag (insightface on a numpy-1.26 profile) for IP-Adapter FaceID / InstantID.

---

## Credits & license

ComfyUI-Ultimate is a packaging of [ComfyUI](https://github.com/comfyanonymous/ComfyUI) and the 29 community node packs listed above — all credit for the nodes goes to their respective authors. SageAttention wheels courtesy of [Kijai](https://huggingface.co/Kijai/PrecompiledWheels); FlashAttention by [Dao-AILab](https://github.com/Dao-AILab/flash-attention).

This repository's packaging is released under the Apache-2.0 License (see [LICENSE](LICENSE)). Bundled projects retain their own licenses.
