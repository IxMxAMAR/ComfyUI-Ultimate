# ComfyUI-Ultimate

A batteries-included **ComfyUI** Docker image for **RunPod** — the heavy software stack is baked in, **no model weights**. Built by GitHub Actions, pushed to Docker Hub as [`ixmxamar/comfyui-ultimate`](https://hub.docker.com/r/ixmxamar/comfyui-ultimate).

## Stack
- **Python 3.12 · CUDA 12.8 · PyTorch 2.8.0+cu128** (torchvision 0.23.0 / torchaudio 2.8.0), Triton 3.4.0, numpy 2.2.
- **Blackwell sm_120 capable** (RTX 5090) — also runs on Ampere → Hopper.
- **SageAttention 2.2** (primary accel) + **FlashAttention 2.8.3** (optional) + PyTorch SDPA.
- **29 curated custom-node packs** (see `expected_packs.txt` / `node_pins.txt`).

## Tags
- `:latest` — newest build from `main`.
- `:<git-sha>` — immutable, reproducible.
- `:cu128-torch2.8.0` — moves only on a torch bump.

## Run on RunPod (GPU Pod)
Use an **RTX-class GPU** (RTX VSR / nvidia-vfx node needs a consumer RTX; SageAttention sm_120 targets the 5090). Exposed ports:

| Service | Port |
|---|---|
| ComfyUI | 8188 |
| JupyterLab | 8888 |
| filebrowser | 8080 |
| SSH | 22 |

### Environment variables
| Var | Purpose |
|---|---|
| `CIVITAI_API_KEY` | Civicomfy downloads from Civitai |
| `HF_TOKEN` | HuggingFace gated downloads |
| `JUPYTER_TOKEN` | JupyterLab token — default empty = **no auth**; set it to require a token |
| `PUBLIC_KEY` | SSH public key (RunPod injects this) |
| `COMFY_ARGS` | extra args appended to `python main.py` |
| `WORKSPACE` | persistent volume mount (default `/workspace`) |

`models/ output/ input/ user/` are symlinked onto the `/workspace` network volume, so weights and outputs persist across restarts.

## Getting models
No models are baked and there is **no boot-time provisioning**. Pull models from inside the running ComfyUI UI:
- **Civicomfy** — search + download Civitai/HF models into the right folders (set `CIVITAI_API_KEY`).
- **ComfyUI-RunpodDirect** — paste any URL and stream it straight to the pod (multi-connection).

## Attention
SageAttention is the primary accelerator — prefer the **KJNodes "Patch Sage Attention"** node over the global `--use-sage-attention` flag (the global flag can produce black frames on some Wan/Qwen models). FlashAttention-2 is available as an optional backend.

## Build / dependency model
Every ABI-sensitive package is hard-pinned in `constraints.txt`, applied to all installs via `PIP_CONSTRAINT`. torch is installed first from the cu128 index; opencv/onnxruntime are normalized to a single variant at the end; ComfyUI-Manager's `torch_rollback` is patched out so it can't clobber the cu128 build. CI fails the build unless `smoke_test.py` passes **and** all 29 nodes import. See [`docs/superpowers/specs/`](docs/superpowers/specs/) for the full design.
