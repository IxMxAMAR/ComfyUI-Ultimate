# =============================================================================
# ComfyUI-Ultimate — Linux x86_64 / Python 3.12 / CUDA 12.8 / torch cu128
# Blackwell sm_120 (RTX 5090) capable. Software baked; NO model weights.
# =============================================================================
FROM nvidia/cuda:12.8.0-cudnn-devel-ubuntu22.04

# devel base => nvcc + CUDA 12.8 toolchain for the SageAttention source-build
# fallback. Ubuntu 22.04 glibc 2.35 >= 2.28 (manylinux_2_28 cu128 wheels).

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:/usr/local/bin:/usr/bin:/bin \
    PIP_CONSTRAINT=/opt/constraints.txt \
    UV_CONSTRAINT=/opt/constraints.txt \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MPLBACKEND=Agg \
    HF_HUB_DISABLE_TELEMETRY=1 \
    WAS_BLOCK_AUTO_INSTALL=1

# ---- 1. System deps (python3.12 via deadsnakes) ----
RUN apt-get update && apt-get install -y --no-install-recommends software-properties-common gnupg ca-certificates curl \
 && add-apt-repository -y ppa:deadsnakes/ppa \
 && apt-get update && apt-get install -y --no-install-recommends \
      python3.12 python3.12-venv python3.12-dev \
      git git-lfs aria2 wget \
      ffmpeg libsndfile1 libglib2.0-0 libgomp1 libgl1 \
      build-essential ninja-build \
      openssh-server \
 && git lfs install \
 && ssh-keygen -A \
 && sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config \
 && sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config \
 && rm -rf /var/lib/apt/lists/*

# ---- 2. Python 3.12 venv + tooling ----
# constraints.txt must exist before ANY pip call (PIP_CONSTRAINT is set globally).
COPY constraints.txt /opt/constraints.txt
RUN python3.12 -m venv /opt/venv \
 && python -m pip install --upgrade pip setuptools wheel uv

# ---- 3. torch cu128 FIRST (auto-pulls triton 3.4.0). Assert before building on it. ----
RUN pip install torch==2.8.0+cu128 torchvision==0.23.0+cu128 torchaudio==2.8.0+cu128 \
      --index-url https://download.pytorch.org/whl/cu128 \
 && python -c "import torch; assert torch.version.cuda=='12.8', torch.version.cuda; assert '+cu128' in torch.__version__, torch.__version__; print('torch OK', torch.__version__)"

# ---- 4. Attention backends ----
# FlashAttention-2: prebuilt, cxx11abiTRUE (matches manylinux_2_28 torch 2.8.0+cu128),
# sm_120 SASS baked in. Fallback to a source build if the URL is gone.
RUN pip install --no-cache-dir \
      "https://github.com/Dao-AILab/flash-attention/releases/download/v2.8.3.post1/flash_attn-2.8.3.post1%2Bcu12torch2.8cxx11abiTRUE-cp312-cp312-linux_x86_64.whl" \
   || pip install flash-attn==2.8.3.post1 --no-build-isolation \
   || echo "WARN: flash-attn install failed (optional backend)"

# SageAttention 2.2: hybrid + best-effort. Try the community Blackwell wheel and
# classify the import (sage_check.py tells an ABI mismatch apart from "no GPU at
# build"). On ABI mismatch / missing wheel, compile from source vs torch 2.8.0.
# Never fails the build — if everything fails, the image ships with SDPA fallback.
RUN bash -c '\
  if pip install --no-cache-dir "https://github.com/thekie/sageattention-wheel/releases/download/2.2.0.post1/sageattention-2.2.0-cp312-cp312-linux_x86_64.whl" \
     && python /opt/scripts/sage_check.py; then \
    echo "SageAttention: using prebuilt wheel"; \
  else \
    echo "SageAttention: wheel unusable -> compiling from source"; \
    pip uninstall -y sageattention || true; \
    ( git clone --depth 1 https://github.com/thu-ml/SageAttention.git /tmp/sage \
      && cd /tmp/sage \
      && TORCH_CUDA_ARCH_LIST="8.0;8.6;8.9;12.0" EXT_PARALLEL=2 NVCC_APPEND_FLAGS="--threads 4" MAX_JOBS=4 \
         pip install --no-build-isolation . ) \
      || echo "WARN: SageAttention source build failed; shipping without it (SDPA fallback)"; \
    rm -rf /tmp/sage; \
  fi'

# ---- 5. Pre-bake the ABI-sensitive set (lock it before node requirements run) ----
RUN uv pip install --no-cache \
      numpy numba llvmlite \
      transformers tokenizers huggingface-hub diffusers accelerate peft safetensors \
      protobuf mediapipe pillow scipy scikit-image scikit-learn \
      kornia timm sentencepiece einops matplotlib simpleeval \
      open-clip-torch clip-interrogator gguf ultralytics spandrel \
      jupyterlab

# ---- 6. ComfyUI core (v0.24.0) ----
RUN git clone --depth 1 --branch v0.24.0 https://github.com/comfyanonymous/ComfyUI.git /ComfyUI
WORKDIR /ComfyUI
RUN uv pip install --no-cache -r requirements.txt

# ---- 7. Custom nodes: clone 29 @ pinned commits + install per policy ----
COPY node_pins.txt /opt/node_pins.txt
COPY scripts/ /opt/scripts/
RUN chmod +x /opt/scripts/*.sh && bash /opt/scripts/install_nodes.sh /opt/node_pins.txt

# ---- 8. opencv + onnxruntime FINAL normalization (single winner each) ----
RUN pip uninstall -y opencv-python opencv-python-headless opencv-contrib-python opencv-contrib-python-headless onnxruntime onnxruntime-gpu || true \
 && uv pip install --no-cache opencv-contrib-python-headless==4.11.0.86 onnxruntime-gpu==1.22.0

# ---- 9. Neutralize ComfyUI-Manager torch_rollback + wire pip_overrides ----
COPY pip_overrides.json /opt/pip_overrides.json
RUN python /opt/scripts/patch_manager.py \
 && cp /opt/pip_overrides.json /ComfyUI/custom_nodes/ComfyUI-Manager/pip_overrides.json 2>/dev/null || true

# ---- 10. filebrowser ----
RUN curl -fsSL https://raw.githubusercontent.com/filebrowser/filebrowser/master/get.sh | bash || echo "WARN: filebrowser install failed"

# ---- 11. Integrity checks (smoke_test fails the build; pip check is advisory) ----
COPY expected_packs.txt /opt/expected_packs.txt
RUN pip check || echo "NOTE: pip check reported advisory conflicts (expected: ultralytics/mediapipe want opencv-python; cv2 is provided by opencv-contrib-python-headless)"
RUN python /opt/scripts/smoke_test.py

# ---- 12. Entrypoint ----
RUN cp /opt/scripts/start.sh /opt/start.sh && chmod +x /opt/start.sh
EXPOSE 8188 8888 22 8080
WORKDIR /ComfyUI
ENTRYPOINT ["/opt/start.sh"]
