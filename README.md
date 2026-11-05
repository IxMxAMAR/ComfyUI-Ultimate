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
- [The RunPod template page](#the-runpod-template-page)
- [Services & ports](#services--ports)
- [Environment variables](#environment-variables)
- [Getting models](#getting-models)
- [PodPanel](#podpanel)
- [Keeping custom nodes across rebuilds](#keeping-custom-nodes-across-rebuilds)
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
- **Dependency-hardened & runtime-resilient.** A pinned `constraints.txt` enforces consistent build-time dependencies without locking down runtime installs. Core CUDA PyTorch packages are shielded by ComfyUI-Manager downgrade blacklists, requirement sanitization, and a NumPy 1.x backwards-compatibility shim so both bleeding-edge and legacy nodes install cleanly. The CI **fails the build unless all 29 nodes import cleanly.**

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
| ComfyUI | `v0.39.2` (with the cross-site navigation fix — see Troubleshooting) |
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
3. **Expose ports** — HTTP: `8188`, `8888`, `8080`, `8090`; TCP: `22` (see [Services & ports](#services--ports)).
4. **Attach a Network Volume** mounted at `/workspace` (so models & outputs persist).
5. **(Optional) Set env vars** — `CIVITAI_API_KEY`, `HF_TOKEN` (see [Environment variables](#environment-variables)).
6. Wait ~60–90s for first boot (ComfyUI loads torch + 29 node packs), then open the **ComfyUI** link.

> ⏱️ **First boot takes ~60–90 seconds** because the image loads PyTorch and all 29 node packs. **Open the ComfyUI link only after** the pod log shows `To see the GUI go to:`. See [Troubleshooting](#troubleshooting) if you get a 403.

---

## The RunPod template page

The published template — [console.runpod.io/hub/template/lbw5xj63wp](https://console.runpod.io/hub/template/lbw5xj63wp) —
carries its own README. That text is **not** part of the image and not part of this repo as far as
RunPod is concerned: it lives on the template record and is served only by RunPod's GraphQL API.
(REST v2 cannot set it — its `UpdateTemplateRequest` rejects unknown properties and has no `readme`
field at all.)

The source of truth is [`docs/template-readme.md`](docs/template-readme.md). Edit that file, then:

```bash
python tools/set_template_readme.py --dry-run    # show what would change
python tools/set_template_readme.py              # push it
python tools/set_template_readme.py --show       # print the live readme
python tools/set_template_readme.py --create     # create the template from scratch
```

The key is read from `--key`, then `$RUNPOD_API_KEY`, then `~/.runpod/config.toml`. It must belong
to the account that **owns** the template: a key for any other account can read a public template
but every write comes back as `Template not found`. The script preserves the rest of the template
definition (image, disk, volume, env, flags), and adds the PodPanel port `8090` if the template is
missing it — templates created before PodPanel existed usually are.

> ⚠️ `saveTemplate` is an upsert, so the script echoes the live definition back rather than sending
> only the fields it means to change. `--dry-run` first is never a bad idea.

---

## Services & ports

| Service | Port | Type | Notes |
|---|---|---|---|
| **ComfyUI** | `8188` | HTTP | The main UI |
| **JupyterLab** | `8888` | HTTP | File manager + terminal + notebooks — **no login by default** |
| **File Browser** | `8080` | HTTP | Lightweight web file manager (no auth) |
| **PodPanel** | `8090` | HTTP | Outputs gallery, zip downloads, and a drop-in runner for [PodPreset](https://github.com/IxMxAMAR/ComfyUI-Ultimate) `setup.sh` files (see [PodPanel](#podpanel)) |
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
| `PODPANEL_ENABLE` | `1` | Set to `0` to skip PodPanel entirely |
| `PODPANEL_PORT` | `8090` | PodPanel's port |
| `PODPANEL_TOKEN` | *(empty)* | Empty = **PodPanel open / no login**, matching JupyterLab. Set a value to require `?token=…` |
| `WORKSPACE` | `/workspace` | Persistent volume mount point |

---

## Getting models

**No models are baked in and there is no boot-time provisioning script.** Pull what you need from inside the running ComfyUI UI:

- **Civicomfy** — search Civitai (and HuggingFace), one-click download into the correct `models/<type>/` folder. Set `CIVITAI_API_KEY` so it can fetch gated/account models headlessly.
- **ComfyUI-RunpodDirect** — paste any direct URL (Civitai / HuggingFace / generic) and it streams to the pod with fast multi-connection downloads, a queue, and progress.

Everything downloads onto the `/workspace` volume, so it survives pod restarts.

---

## PodPanel

A small web panel on port `8090` covering the other half of the loop: seeing what came out, getting it off the pod, and loading a model preset onto a fresh pod without a terminal.

Open `https://<pod-id>-8090.proxy.runpod.net` (add `8090` under **Expose HTTP Ports**). Three things:

**Outputs** — every image, video and audio file under `/workspace/output`, newest first, with kind/folder/name filters and a lightbox (arrow keys to move, `Esc` to close). Thumbnails come from Pillow, video posters from ffmpeg; both are already in the image.

**Downloads** — the lightbox downloads a single file; tick any number of cards and **Download selected** streams them as one zip. Media is served with HTTP range support, so videos and audio scrub instead of downloading whole.

**Run a preset** — drop in a `setup.sh` from PodPreset (or paste one) and it runs with `bash` from `/workspace`, one job at a time, streaming the log live. Optional CivitAI/HuggingFace keys are passed to that run as environment variables only — never written into the script or to disk. Uploaded scripts, logs and exit codes live in `/workspace/model-setup/uploads/`, so they survive a restart and the job list is rebuilt from there.

> ⚠️ **It runs whatever you drop in it.** There is no authentication by default — the same posture as JupyterLab and File Browser on this image — and a submitted script runs as root with your volume mounted. Treat the port as sensitive: set `PODPANEL_TOKEN` to require `?token=…`, or `PODPANEL_ENABLE=0` to switch it off.

`scripts/start.sh` starts it (log: `/var/log/podpanel.log`). It is a single stdlib-only file, so you can also drop `podpanel.py` onto an already-running pod and start it by hand:

```bash
python /workspace/podpanel.py --port 8090 --output /workspace/output &
```

---

## Keeping custom nodes across rebuilds

ComfyUI, its Python environment and the 29 bundled node packs live **inside the
image, on the pod's local NVMe** — not on the network volume. That is why this
image starts far faster than templates which install ComfyUI onto `/workspace`
and then import tens of thousands of small files over network storage on every
boot.

The trade-off: anything you install through ComfyUI-Manager also lands on local
disk, and local disk is wiped when the pod is destroyed.

The fix is a pin list, not a symlink — so your nodes still load from fast local
disk, and the list works on any pod, any volume, any account.

**The one command you need.** Install nodes through the Manager UI exactly as
normal, then:

```bash
comfy-nodes freeze
```

That records every node you added — at the exact commit you are running — into
`/workspace/comfy_nodes.txt`. On every future boot they are cloned back and
their requirements reinstalled, before ComfyUI starts. Run it from a JupyterLab
terminal (port 8888 → File → New → Terminal) or over SSH.

| Command | Does |
|---------|------|
| `comfy-nodes status` | Shows which installed nodes are **not** yet recorded — i.e. what you would lose on a rebuild |
| `comfy-nodes freeze` | Records everything you have installed |
| `comfy-nodes add <git-url> [sha]` | Installs a node and records it, in one step |
| `comfy-nodes list` | Shows what is pinned |
| `comfy-nodes restore` | Re-runs the restore now |

You can also edit `/workspace/comfy_nodes.txt` by hand — it uses the same
`<dirname> <git_url> <commit_sha>` format as this repo's own `node_pins.txt`.
The sha is optional (omit it to track the default branch), and a bare git URL
works too.

**What it costs.** Restoring a handful of nodes adds roughly 10–25 seconds to a
cold boot, mostly pip; the wheel cache lives on the volume, so later boots are
faster. Progress is logged to `/workspace/comfy_nodes.log`.

**When to bake a node in instead.** The pin list is for nodes you are trying out
or that change often. Once you have settled on one permanently, add it to
`node_pins.txt` and rebuild — a baked node costs **nothing** at boot, because it
and its dependencies are already installed. If boot is getting slow, that is the
signal to promote what has accumulated in the pin list.

**Packs installed from the Comfy Registry.** ComfyUI-Manager increasingly
installs node packs as versioned archives rather than git clones, so those
directories contain no `.git`. `freeze` handles them: it falls back to the
`Repository` url the Registry requires in `pyproject.toml` and records them as
tracking `HEAD` (an archive carries no commit id, so there is nothing exact to
pin to). If you want one pinned to a specific commit, reinstall it with
`comfy-nodes add <git-url> <sha>`.

If a pack has neither a git remote nor a Repository url, it genuinely cannot be
restored — `freeze` and `status` both say so explicitly rather than skipping it
quietly, because a silent omission would only surface as a missing node after
your next rebuild.

Three guarantees, all enforced in CI: the manifest can never modify or overwrite
one of the 29 bundled packs; a node whose repo has moved, been deleted or gone
private is logged and skipped, so it can never stop the pod from booting; and a
pack that cannot be recorded is always reported, never dropped in silence.

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
- **comfy-kitchen (CK) INT8 attention** is deliberately **unavailable on this image**. CK's prebuilt CUDA kernels are CUDA-13 builds needing NVIDIA driver r580+, while this image is torch cu128, so the kernels cannot load. ComfyUI already disables CK's cuda backend for cu12x, but some CK entry points (INT8 attention, flash-attention decode, INT8 decode) bypass that gate — see [Quantized VAE decode crashes with `detect_k_anchor`](#quantized-vae-decode-crashes-with-detect_k_anchor-kernel-launch-failed). A boot-time gate (`scripts/patch_ck_cuda_gate.py`) now makes those probes report unavailable so ComfyUI falls back cleanly. The only cost is the INT8-attention speedup on quantized VAEs.

> On RTX 5090, SageAttention runs via its sm_89/fp8-compatible kernels (the build that the WanVideoWrapper community uses on 50-series). If you ever hit a kernel error on Blackwell, open an issue — a from-source `sm_120` build path exists.

---

## Troubleshooting

### ComfyUI shows **403 Forbidden** when you *click* the link, but works if you paste it
This is ComfyUI's own doing — not RunPod's, not a startup-timing problem, and not a browser cache.

ComfyUI ships a CSRF middleware (`create_origin_only_middleware()` in `server.py`) that returns a bare, body-less **403** for *any* request whose `Sec-Fetch-Site` header is `cross-site`. That is exactly the header a browser sends when you **click a link** from another site — and the RunPod console lives on `console.runpod.io` while the ComfyUI link is `*.proxy.runpod.net`, so a click is cross-site. Pasting the URL into the address bar sends `Sec-Fetch-Site: none` and works. Chrome and Firefox both behave this way.

Because that 403 carries `Content-Length: 0`, the browser discards it and draws its own error page — Firefox shows `about:neterror` ("Problem loading page"), Chrome shows a generic `HTTP ERROR 403`. On Firefox's error page there is no origin, so `sessionStorage` throws `NS_ERROR_NOT_AVAILABLE` and ComfyUI's frontend could never have booted there anyway.

**Fix (this image):** the build runs `scripts/patch_server.py`, which relaxes the middleware to allow safe top-level navigations (`GET`/`HEAD` + `Sec-Fetch-Mode: navigate`) while still blocking every other cross-site request — so the protection that matters (a random site POSTing to queue workflows) stays intact.

**Workaround on an unpatched build:** bookmark the ComfyUI URL, or paste it. A bookmark click is a user-initiated navigation, not one from a document, so it sends `none` and loads. Don't click the console link.

Upstream: [Comfy-Org/ComfyUI#16203](https://github.com/Comfy-Org/ComfyUI/issues/16203) — still open as of v0.39.2.

You can confirm both behaviours from any terminal (Jupyter/SSH), and check that ComfyUI itself is healthy:
```bash
POD=https://<POD_ID>-8188.proxy.runpod.net
curl -sI http://localhost:8188/ | head -1   # expect: HTTP/1.1 200 OK
# the click path — patched: 200 | unpatched: 403
curl -o /dev/null -w '%{http_code}\n' -H 'Sec-Fetch-Site: cross-site' -H 'Sec-Fetch-Mode: navigate' $POD/
# cross-site POST — always 403, protection intact
curl -o /dev/null -w '%{http_code}\n' -X POST -H 'Sec-Fetch-Site: cross-site' -H 'Content-Type: application/json' -d '{}' $POD/prompt
```

Full write-up with the evidence, and why it isn't a RunPod or startup problem: [docs/reverse-proxy-403.md](docs/reverse-proxy-403.md).

### A port stays "Initializing" in RunPod
RunPod's readiness label can lag (e.g. Jupyter returns a redirect, not a 200). If the service answers locally (`curl -sI localhost:<port>`), it's fine — just open the link.

### RTX Video Super Resolution node "failed to import"
That node (`nvidia-vfx`) loads CUDA at import and **only works on a real RTX GPU**. It is intentionally skipped in CI (which has no GPU) and will load on your pod.

### Quantized VAE decode crashes with `detect_k_anchor kernel launch failed`
```
RuntimeError: detect_k_anchor kernel launch failed: CUDA driver version is
insufficient for CUDA runtime version
```
Sampling completes (4–8 steps) and then **VAEDecode** dies. It happens on any workflow whose VAE decoder weights are quantized — MiniMax H3 int8/convrot VAEs, for example; the loader picks the layout from the file's own headers, so a name like `minimax_h3_video_vae_fp16` is not a reliable signal that the weights are fp16. It is not your driver, your VAE or your workflow.

**What actually happens.** Quantized VAE weights send ComfyUI down its INT8-attention path (`comfy/ldm/minimax/vae.py` → `comfy.quant_ops.ck.int8_attention`). `int8_attention` is the one comfy-kitchen entry point that **bypasses comfy-kitchen's own backend registry**, so the gate ComfyUI already applies on a cu12x torch — `ck.registry.disable("cuda")`, logging *"You need pytorch with cu130 or higher to use optimized CUDA operations"* — does not cover it. Every comfy-kitchen wheel ever published (0.1.0 onward) is a **CUDA-13 build requiring NVIDIA driver r580+**, so the first kernel on that path cannot be loaded and the launch fails with `cudaErrorInsufficientDriver` (35). CUDA loads kernels lazily, which is why the failure lands at decode rather than at startup. Upstream closed the same defect for `flash_attention_decode` with *"We do not support using cuda 12 on newer GPUs"* ([ComfyUI #16449](https://github.com/Comfy-Org/ComfyUI/issues/16449)).

**What this image does about it.** `scripts/patch_ck_cuda_gate.py` appends a gate to the installed `comfy_kitchen/__init__.py` that wraps every public `*_is_available` probe, plus `comfy_kitchen.int8_decode.is_available` (imported directly by ComfyUI's Qwen3.5 text encoder): when CK's CUDA kernels cannot run (torch cu12x, registry backend disabled, or a driver below r580), the probes report unavailable and ComfyUI takes its normal attention path. It is applied at build time and **re-applied on every boot**, because updating ComfyUI inside a pod reinstalls comfy-kitchen and would otherwise undo it. Verify or re-apply after a manual CK upgrade:
```bash
python /opt/scripts/patch_ck_cuda_gate.py --report     # verdict + which probes are gated
```
The gate leaves a cu130 image on an r580+ host completely untouched, so this is safe to keep after a future CUDA-13 upgrade.

### `ValueError: too many values to unpack (expected 3)` from `audio_vae.py`
The MiniMax-H3 reference/keyframe nodes take **two** VAE inputs and they are easy to cross:

| Input | Must receive |
|---|---|
| `vae` | the **video** VAE — `minimax_h3_video_vae_*.safetensors` |
| `audio_vae` | the **audio** VAE — `minimax_h3_audio_vae_fp32.safetensors` |

(`MiniMaxH3ReferenceToVideo`, `MiniMaxH3ImageToVideo` and `MiniMaxH3AddGuide` all have this pair.) If an audio VAE reaches `vae`, the node hands it an image and `MiniMaxH3AudioVAE.encode()` unpacks `waveform.shape` as `(batch, channels, length)` — an image has 4–5 dims, hence the error. The giveaway is the log line just before the traceback: `Model MiniMaxH3AudioVAE prepared for dynamic VRAM loading` while the node is encoding a reference **image**. Nothing is wrong with the image, the model or the VAE file; only the wiring. The same nodes also feed the video VAE from `MiniMaxH3ImageToVideo`'s keyframes, so a crossed pair breaks every reference workflow.

> Note the file names: a MiniMax H3 VAE named `..._fp16` can still carry **int8/convrot quantization metadata** (the loader logs `Found quantization metadata version 1` right after loading it), which is what puts VAE decode on comfy-kitchen's INT8-attention path — see [Quantized VAE decode crashes with `detect_k_anchor`](#quantized-vae-decode-crashes-with-detect_k_anchor-kernel-launch-failed). Check the log, not the filename.

### Models disappear after a restart
Attach a Network Volume at `/workspace`. Without it, downloads live in ephemeral container storage.

---

## How the image is built

The hard part of a 29-pack ComfyUI image is dependency conflicts. The strategy:

1. **Build-time `constraints.txt` + runtime protection** — hard-pins every ABI-sensitive package during base build, while protecting torch cu128 at runtime via ComfyUI-Manager downgrade blacklists and requirements sanitization so user-installed nodes (new or old) never fail from rigid constraint conflicts.
2. **Deterministic install order** — torch (from the cu128 index) first, then attention backends, then a pre-baked ABI set, then ComfyUI core, then the 29 nodes, then a final opencv/onnxruntime normalization to a single variant.
3. **CI quality gates** — `smoke_test.py` runs *inside* the build (asserts single cv2 variant, numpy 2.2, torch cu128, HF coherence); a **node-import gate** boots ComfyUI headless and **fails the build unless all 29 packs import**; and a **comfy-kitchen CUDA-gate check** runs against the *finished* image, so a later pip step or a node pack cannot silently reinstall CK and undo the gate described in [Troubleshooting](#quantized-vae-decode-crashes-with-detect_k_anchor-kernel-launch-failed). The image is pushed only if all gates pass.

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
- **cu130 image line** — rebuild torch, SageAttention and FlashAttention on CUDA 13 so comfy-kitchen's INT8 attention and flash-attention-decode actually run (needs a host with NVIDIA driver r580+; the pod's driver belongs to the RunPod host and cannot be changed from inside the container). Until then the CK CUDA gate keeps the cu128 line correct rather than merely fast.
- Optional `WITH_FACEID` build flag (insightface on a numpy-1.26 profile) for IP-Adapter FaceID / InstantID.

---

## Credits & license

ComfyUI-Ultimate is a packaging of [ComfyUI](https://github.com/comfyanonymous/ComfyUI) and the 29 community node packs listed above — all credit for the nodes goes to their respective authors. SageAttention wheels courtesy of [Kijai](https://huggingface.co/Kijai/PrecompiledWheels); FlashAttention by [Dao-AILab](https://github.com/Dao-AILab/flash-attention).

This repository's packaging is released under the Apache-2.0 License (see [LICENSE](LICENSE)). Bundled projects retain their own licenses.
