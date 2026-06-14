# ComfyUI-Ultimate — RunPod Template — Design Spec

**Date:** 2026-06-14
**Repo:** `IxMxAMAR/ComfyUI-Ultimate` → image `docker.io/ixmxamar/comfyui-ultimate`
**Status:** Approved design — ready for implementation planning.

---

## 1. Goal & Scope

A "batteries-included" ComfyUI Docker image where the **heavy software stack is baked in** (CUDA libs, PyTorch cu128, Triton, SageAttention, FlashAttention, 27 curated custom-node packs) and **no model weights** are baked in. Built by **GitHub Actions** and pushed to **Docker Hub**, deployable on **RunPod**.

- **Primary target:** RunPod **GPU Pod** (interactive — ComfyUI web UI, JupyterLab, SSH, filebrowser).
- **Secondary target:** RunPod **Serverless** endpoint (same image, alternate entrypoint with a `handler.py`) — layered on later, not part of the first milestone.

**Non-goals:** baking model weights into the image; a custom ComfyUI fork; FaceID/insightface in the default image (gated behind a build flag).

---

## 2. Target Hardware / Stack (verified 2026-06-14)

| Component | Choice | Notes |
|---|---|---|
| Base image | `nvidia/cuda:12.8.0-cudnn-devel-ubuntu22.04` | `devel` → `nvcc` + toolchain for the SageAttention source-build fallback. Ubuntu 22.04 = glibc 2.35 ≥ 2.28 required by `manylinux_2_28` cu128 wheels. |
| Python | 3.12 | matches all wheels (torch cu128, nvidia-vfx cp312, flash-attn cp312). |
| PyTorch | `torch==2.8.0+cu128` / `torchvision==0.23.0+cu128` / `torchaudio==2.8.0+cu128` | torchvision 0.23.0 metadata hard-pins torch==2.8.0 → triple is mechanically locked. Longest ComfyUI track record on Blackwell. From `download.pytorch.org/whl/cu128`. |
| Triton | `triton==3.4.0` | **auto-pulled by torch**; never `pip install triton` separately. Pinned as a guard. |
| numpy | `numpy==2.2.6` | achievable because no default pack hard-pins numpy<2 (insightface excluded). |
| GPU coverage | sm_80 / 86 / 89 / 90 / 120 | Ampere → Ada → Hopper → Blackwell. Covers RTX 5090 (sm_120). |
| Attention | SageAttention 2.2.0 (primary) + FlashAttention 2.8.3.post1 (optional) + PyTorch SDPA | see §6. |

---

## 3. Custom Node Set (27 packs)

Cloned at **pinned commits** (`node_pins.txt`). Models referenced by these nodes download at runtime onto the volume — never baked.

**Core/Utility:** ComfyUI-Manager, rgthree-comfy, ComfyUI-Custom-Scripts, ComfyUI-KJNodes, ComfyUI_essentials, was-node-suite-comfyui, ComfyUI-Crystools, ComfyUI-Easy-Use, cg-use-everywhere

**Detailing/Upscale:** ComfyUI-Impact-Pack, ComfyUI-Impact-Subpack, ComfyUI_UltimateSDUpscale, ComfyUI-Inspire-Pack, efficiency-nodes-comfyui

**Control/Conditioning:** comfyui_controlnet_aux, ComfyUI-Advanced-ControlNet, ComfyUI_IPAdapter_plus

**Video/Animation:** ComfyUI-VideoHelperSuite, ComfyUI-Frame-Interpolation, ComfyUI-AnimateDiff-Evolved, ComfyUI-WanVideoWrapper

**Model formats/Vision:** ComfyUI-GGUF, ComfyUI-Florence2, ComfyUI-segment-anything-2

**Added:** ComfyUI-RMBG (`1038lab/ComfyUI-RMBG`), ComfyUI-Utility-MegaPack (`IxMxAMAR/ComfyUI-Utility-MegaPack`), Nvidia RTX Nodes (`Comfy-Org/Nvidia_RTX_Nodes_ComfyUI`)

**Excluded by decision:** ReActor, the user's API node packs (NanoBanana2/Kling/ElevenLabs/etc.), insightface-dependent FaceID paths (behind a flag — §7).

---

## 4. Dependency Management Strategy (the core risk)

**Thesis:** Every torch/numpy/opencv/onnx/HF conflict here is **mechanical, not version-arithmetic.** No pack declares a genuinely unsatisfiable version — they declare **bare/unpinned names** (or run `install.py` / pull transitive deps like `ultralytics`, `clip-interrogator`, `rembg`) that let a naive `pip install` fetch a default-PyPI/CPU wheel that **clobbers** the curated cu128 build and strips sm_120. Defense = 5 layers.

### 4.1 Layer 1 — One authoritative `constraints.txt` (`/opt/constraints.txt`)

Single source of truth; hard-`==`-pins every ABI-sensitive package. Bounds versions only — never installs anything itself.

```text
# /opt/constraints.txt — ComfyUI Ultimate (cu128 / py3.12 / sm_120 Blackwell)
# Applied to EVERY pip/uv install via PIP_CONSTRAINT/UV_CONSTRAINT.
# Generated baseline 2026-06-14 (re-verify against live cu128 index on bump).

# --- PyTorch triple (cu128). torchvision 0.23.0 hard-pins torch==2.8.0. ---
torch==2.8.0+cu128
torchvision==0.23.0+cu128
torchaudio==2.8.0+cu128
triton==3.4.0

# --- numpy 2.x + its compiled gatekeepers ---
numpy==2.2.6
numba==0.61.2
llvmlite==0.44.0

# --- single opencv variant: contrib-headless (no libGL/X11) ---
opencv-contrib-python-headless==4.11.0.86

# --- single onnxruntime: gpu, CUDA-12.x family (cuDNN 9) ---
onnxruntime-gpu==1.22.0

# --- HuggingFace set: move as one coherent group ---
transformers==4.53.2
tokenizers==0.21.2
huggingface-hub==0.34.3
diffusers==0.34.0
accelerate==1.8.1
peft==0.16.0
safetensors==0.5.3

# --- protobuf under RMBG <6 cap, above mediapipe floor ---
protobuf==4.25.8
mediapipe==0.10.21
pillow==11.3.0
simpleeval==1.0.3

# --- ComfyUI core == pins (tied to ComfyUI v0.24.0) ---
comfyui-frontend-package==1.45.15
comfyui-workflow-templates==0.9.98
comfyui-embedded-docs==0.5.3
comfy-kitchen==0.2.10
comfy-aimdo==0.4.9

# --- other cross-cutting pins ---
scipy==1.15.3
scikit-image==0.25.2
scikit-learn==1.6.1
kornia==0.8.1
timm==1.0.16
sentencepiece==0.2.0
einops==0.8.1
matplotlib==3.10.3
clip-interrogator==0.6.0
open-clip-torch==2.32.0
gguf==0.17.1
ultralytics==8.3.162
spandrel==0.4.1

# --- HARD BANS: impossible version → pip fails loudly if a node tries these ---
opencv-python==0.0.0
opencv-python-headless==0.0.0
opencv-contrib-python==0.0.0
onnxruntime==0.0.0
xformers==0.0.0
```

A second file `constraints-final.txt` is identical **minus** the opencv/onnx `==0.0.0` ban lines; used only for the final normalization installs of `opencv-contrib-python-headless` and `onnxruntime-gpu`.

### 4.2 Layer 2 — `PIP_CONSTRAINT` everywhere

```dockerfile
ENV PIP_CONSTRAINT=/opt/constraints.txt \
    UV_CONSTRAINT=/opt/constraints.txt \
    MPLBACKEND=Agg \
    HF_HUB_DISABLE_TELEMETRY=1 \
    WAS_BLOCK_AUTO_INSTALL=1
```

Set **before any install** and **persists at runtime** so ComfyUI-Manager's startup self-healing is also constrained. Honored by both `pip` and `uv`. A node's bare `torch` becomes a no-op; a floor `torch>=2.0` resolves to the pinned `2.8.0+cu128`; a transitive `ultralytics→torchvision` resolves to `0.23.0+cu128`.

### 4.3 Layer 3 — Deterministic install order

```
1. apt deps (python3.12, git/git-lfs, ffmpeg, libsndfile1, libglib2.0-0, libgomp1,
   build-essential, ninja-build)            # NO libgl1 (headless cv2)
2. python3.12 venv + pip/uv
3. torch cu128 FIRST  (--index-url download.pytorch.org/whl/cu128) → auto triton 3.4.0
   3a. ASSERT torch.version.cuda=='12.8' and '+cu128' in torch.__version__
4. FlashAttention 2 (prebuilt wheel) + SageAttention 2.2 (hybrid)   # §6
5. pre-bake the ABI-sensitive SET (numpy/numba/HF group/protobuf/mediapipe/pillow/…)
6. ComfyUI core (git clone v0.24.0; uv pip install -r requirements.txt)
7. custom nodes: clone all 27 @ pinned commit; install per §4.5
8. opencv + onnxruntime FINAL normalization (uninstall all variants, install the one
   winner each via constraints-final.txt)    # MUST be last
9. pip check + smoke_test.py
10. patch_manager.py (neutralize ComfyUI-Manager torch_rollback)
```

### 4.4 Layer 4 — `--no-deps` on the movers
Packs whose deps would relocate torch/numpy/cv2/onnx are installed `--no-deps`, with their real deps installed explicitly under the constraint. Frame-Interpolation's `install.py` is **never run** (it `pip install torch` per line).

### 4.5 Layer 5 — Neutralize the two runtime self-healers
- **ComfyUI-Manager** `PIPFixer.torch_rollback`: its hardcoded map maxes at torch 2.7.0, so our 2.8.0+cu128 triggers a `--force` PyPI reinstall that wipes sm_120 on every boot. `patch_manager.py` rewrites `torch_rollback` to a no-op (idempotent). The persistent `PIP_CONSTRAINT` is the second line of defense.
- **was-node-suite** import-time `install_package`: disabled via `WAS_BLOCK_AUTO_INSTALL=1` + pre-installed cv2 so its `import cv2` never triggers the uninstall/reinstall branch.

### 4.6 Per-pack handling (risky packs)

| Pack | Policy | Runtime model DL |
|---|---|---|
| ComfyUI core | `uv pip install -r requirements.txt` after torch | frontend assets only |
| ComfyUI-Manager | install reqs; run `patch_manager.py`; pre-bake transformers/hub | catalog JSON |
| was-node-suite | `-r requirements.txt --no-deps` + explicit deps; `WAS_BLOCK_AUTO_INSTALL=1` | SAM/MiDaS/BLIP/rembg |
| Impact-Pack | reqs with `sam2` via `--no-deps` (`SAM2_BUILD_CUDA=0`); no SAM auto-DL at build | SAM @ runtime |
| Impact-Subpack | `ultralytics==8.3.162 --no-deps` then `-r requirements.txt --no-deps` | YOLO @ runtime |
| comfyui_controlnet_aux | `--no-deps` + explicit deps (biggest direct torch mover) | Annotators/DWPose ONNX |
| Frame-Interpolation | **don't run install.py**; `-r requirements-no-cupy.txt --no-deps` + `cupy-cuda12x` | RIFE/FILM via torch.hub |
| segment-anything-2 | `uv pip install .` (vendored sam2) | sam2 safetensors |
| Florence2 | `-r requirements.txt` after HF set frozen | Florence-2 VLMs |
| WanVideoWrapper | `-r requirements.txt` (constraint overrides cv2→headless) | user-supplied |
| RMBG | `--no-deps` + explicit deps; lists BOTH onnxruntime variants; `groundingdino-py` needs nvcc | RMBG/BiRefNet/SAM3/LaMa |
| essentials | `--no-deps` (rembg pulls CPU onnxruntime) + explicit deps | CLIPSeg/rembg |
| Easy-Use | `-r requirements.txt`; mediapipe pre-baked (runtime install becomes no-op) | IC-Light/IPAdapter |
| IPAdapter_plus | `uv pip install .` (insightface optional — flag) | buffalo_l (FaceID only) |
| efficiency-nodes | `clip-interrogator==0.6.0 --no-deps` (pulls CPU torchvision otherwise) | BLIP/CLIP |
| Inspire-Pack | install from requirements.txt; pre-bake sibling packs (runtime git-clone) | — |
| VideoHelperSuite | `-r requirements.txt` (cv2→headless) | — |
| RTX Nodes | `pip install nvidia-vfx --extra-index-url https://pypi.nvidia.com/` (cp312-abi3 manylinux_2_28, ~600MB) | none |
| rgthree, Custom-Scripts, KJNodes, cg-use-everywhere, Advanced-ControlNet, AnimateDiff-Evolved, GGUF, UltimateSDUpscale, Crystools, Utility-MegaPack | default `uv pip install -r requirements.txt` | low/none |

### 4.7 opencv / onnxruntime normalization (final layer)
All four cv2 distros vend the same `cv2` module and shadow each other → keep exactly **one**: `opencv-contrib-python-headless==4.11.0.86` (contrib preserves Frame-Interpolation's `ximgproc`/SIFT; headless avoids libGL/X11). `onnxruntime` (CPU) and `onnxruntime-gpu` both write `site-packages/onnxruntime/`; keep only `onnxruntime-gpu==1.22.0`. ComfyUI-Manager `pip_overrides.json`: `{"onnxruntime": "onnxruntime-gpu"}` for runtime node installs. Final step uninstalls all variants then reinstalls the winners via `constraints-final.txt`.

---

## 5. RTX Nodes (nvidia-vfx) note
`Comfy-Org/Nvidia_RTX_Nodes_ComfyUI` (RTX Video Super Resolution) installs from `https://pypi.nvidia.com/` (Linux cp312-abi3 manylinux_2_28 wheel exists). The VSR engine is an **RTX-consumer GPU feature** — works on RTX 4090/5090, may not initialize on datacenter cards (A100/H100). Needs NVIDIA driver 570.190+/580.82+/590.44+ at runtime (host-provided by RunPod). No `Requires-Dist` → won't move torch/numpy.

---

## 6. Attention Backends

### FlashAttention 2 — prebuilt wheel (no compile)
```dockerfile
# cxx11abiTRUE matches torch 2.8.0+cu128 (manylinux_2_28 = _GLIBCXX_USE_CXX11_ABI=1).
# sm_120 SASS baked in (built w/ CUDA 12.9.1, arch list 80;90;100;120). Dated 2026-06-11.
RUN pip install --no-cache-dir \
  "https://github.com/Dao-AILab/flash-attention/releases/download/v2.8.3.post1/flash_attn-2.8.3.post1%2Bcu12torch2.8cxx11abiTRUE-cp312-cp312-linux_x86_64.whl"
# Fallback if URL 404s: pip install flash-attn==2.8.3.post1 --no-build-isolation
```
FA3/FA4 do **not** support consumer Blackwell — FA2 only. No pack hard-requires flash_attn (all wrap in try/except), so it's an optional accelerator path.

### SageAttention 2.2.0 — hybrid (community wheel → fallback to source compile)
```dockerfile
# Try the community prebuilt (thekie 2.2.0.post1: cp312/linux/cu128/sm_120, dated 2026-06-03,
# built vs torch 2.10 ABI). Import-test it; if it fails, compile from source vs our torch 2.8.0.
RUN ( pip install --no-cache-dir \
        "https://github.com/thekie/sageattention-wheel/releases/download/2.2.0.post1/sageattention-2.2.0-cp312-cp312-linux_x86_64.whl" \
      && python -c "import sageattention; print('sage wheel OK')" ) \
   || ( echo "sage wheel failed import -> building from source" \
        && git clone --depth 1 https://github.com/thu-ml/SageAttention.git /tmp/sage \
        && cd /tmp/sage \
        && TORCH_CUDA_ARCH_LIST="8.0;8.6;8.9;12.0" EXT_PARALLEL=4 NVCC_APPEND_FLAGS="--threads 8" MAX_JOBS=8 \
           pip install --no-build-isolation . \
        && rm -rf /tmp/sage )
```
Build is deterministic in practice (the wheel either imports against torch 2.8.0 or it doesn't, consistently). The chosen path is recorded in the build metadata / lockfile. Never `pip install sageattention` bare (pulls 1.0.6 → black output on Blackwell).

**xformers: skipped/banned** — SageAttention + SDPA cover all attention; bare xformers pulls torch 2.10.

**Runtime usage:** prefer the KJNodes "Patch Sage Attention KJ" node over the global `--use-sage-attention` flag (global flag yields black frames on some Wan/Qwen models).

---

## 7. FaceID / insightface (flag, off by default)
insightface forces `numpy<2` image-wide (numpy-1.x ABI Cython ext) — the single thing that breaks the clean numpy-2.2 image. **Default: not installed.** Build-arg `WITH_FACEID=1` switches to a **numpy==1.26.4 fallback profile** (drop numba/mediapipe to numpy-1.x lines, add `insightface==0.7.3 --no-deps` + onnxruntime-gpu) for IPAdapter FaceID / InstantID.

---

## 8. Image Layout & Persistence
- App baked at `/ComfyUI`. Python venv at `/opt/venv`.
- On the RunPod **network volume** (`/workspace`): `models/`, `output/`, `input/`, `user/` — symlinked into `/ComfyUI` so weights/outputs/configs persist across pod restarts and the image stays app-only.
- Node model-cache env vars (e.g. `HF_HOME`, `AUX_ANNOTATOR_CKPTS_PATH`, Frame-Interp `ckpts_path`) pointed at the volume.

---

## 9. Runtime Services & Access
| Service | Port | Auth |
|---|---|---|
| ComfyUI web UI | 8188 | none (RunPod proxy URL obscurity) |
| JupyterLab | 8888 | token |
| SSH | 22 | RunPod-injected public key |
| filebrowser | 8080 | default login |

Entrypoint (`start.sh`) launches all four, wires the volume symlinks, runs the provisioning script if set, then starts ComfyUI.

---

## 10. Model Provisioning (runtime, env-driven)
ai-dock style: `PROVISIONING_SCRIPT` env = URL to a bash script run on first boot that downloads checkpoints/LoRAs/VAEs into `/workspace/models/...`. Supports `HF_TOKEN` and `CIVITAI_TOKEN`. Models are **never** in the image. Ships with a couple of example provisioning scripts (e.g. SDXL set, Flux set, WAN set) the operator can point to or fork.

---

## 11. Reproducibility & Tags
Three committed artifacts pin everything:
1. `constraints.txt` — ABI intent (human-edited).
2. `node_pins.txt` — 27 packs + VCS deps at exact commits.
3. `requirements.lock` — full `pip freeze --all` from the last green build.

**Tags:** `:latest`, `:<git-sha>` (immutable/reproducible), `:cu128-torch2.8.0` (moves only on torch bump). Same Dockerfile + same 3 artifacts → byte-stable env regardless of build date.

---

## 12. CI/CD (GitHub Actions → Docker Hub)
- **Triggers:** push to `main`, manual `workflow_dispatch`, version tags.
- **Disk:** free-disk-space step (image is ~18–25 GB; free-runner root is ~14 GB) → buildx with GHA layer cache.
- **Secrets:** `DOCKERHUB_USER` / `DOCKERHUB_TOKEN` (PAT `ixmxamar`).
- **Gates (push only if both pass):**
  1. `smoke_test.py` runs **inside** the build: single cv2 variant, numpy 2.2, torch cu128, HF-set coherence (`split_torch_state_dict_into_shards` import canary), and (GPU job) `CUDAExecutionProvider` + sm_120. A regression fails `docker build` itself.
  2. **Node-import gate:** `python main.py --cpu --quick-test-for-ci` → fail on any `IMPORT FAILED`/`Cannot import`, and assert all 27 expected pack dirs appear in success lines (`/opt/expected_packs.txt`).
- **Optional** self-hosted Blackwell GPU job asserts the CUDA provider + sm_120 at runtime.

---

## 13. Update Discipline
Bump only `constraints.txt`, one coherent group at a time; let the gates prove it.
- **torch line** (highest blast radius): confirm triple is live on cu128 index + torchvision metadata pin; bump triton to the paired value; **rebuild SageAttention** (re-runs the hybrid); run gates; regenerate lockfile. cu128 ceiling = torch 2.11.
- **HF quartet**: move transformers+tokenizers+hub+diffusers+accelerate+peft+safetensors together; canary = the `split_torch_state_dict_into_shards` import.
- **numpy**: verify inside numba ∩ mediapipe ∩ opencv ranges; re-run full smoke test (compiled-ext `_ARRAY_API not found` risk). If unreachable, use the numpy 1.26.4 fallback profile.
- **single node**: edit `node_pins.txt` commit; the constraint still governs its deps — a node bump cannot move ABI packages.

---

## 14. Repository Structure (to build)
```
ComfyUI-Ultimate/
├─ Dockerfile
├─ constraints.txt
├─ constraints-final.txt
├─ node_pins.txt
├─ requirements.lock              # generated after first green build
├─ scripts/
│  ├─ install_nodes.sh
│  ├─ patch_manager.py
│  ├─ smoke_test.py
│  ├─ ci_node_import_gate.sh
│  ├─ start.sh                    # entrypoint: services + volume + provisioning
│  └─ provisioning/               # example model-download scripts
├─ pip_overrides.json             # {"onnxruntime":"onnxruntime-gpu"}
├─ expected_packs.txt             # 27 pack dir names for the CI gate
├─ .github/workflows/build.yml
└─ docs/superpowers/specs/2026-06-14-comfyui-ultimate-runpod-template-design.md
```

---

## 15. Milestones
1. **M1 — Pod image:** Dockerfile + dependency strategy + attention backends + CI build/push + both gates green. Deployable interactive Pod (ComfyUI/Jupyter/SSH/filebrowser) with runtime provisioning.
2. **M2 — Polish:** example provisioning scripts, README + RunPod template config, `requirements.lock` committed, optional GPU smoke job.
3. **M3 — Serverless:** `handler.py` + serverless entrypoint mode (same image), RunPod Serverless template.

---

## 16. Open Risks
- SageAttention community wheel (thekie) is a single-maintainer repo — the hybrid's source-compile fallback covers a 404 or ABI mismatch, but adds build time when it fires.
- Multi-arch SASS makes the source-compile fallback heavy (~30–90 min) — `MAX_JOBS=8` to avoid runner OOM; drop `9.0` from the arch list if Hopper isn't needed.
- Image size (~18–25 GB) is near GitHub free-runner disk limits → free-disk-space step is mandatory; self-hosted/larger runner is the escape hatch.
- nvidia-vfx (RTX VSR) won't initialize on datacenter GPUs — documented as RTX-only.
