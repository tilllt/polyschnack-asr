# ==============================================================
# CrispASR runtime — downloads pre-compiled release binary
# HYBRID (Weg 1): Das CUDA-Binary enthält den CPU-Backend
# (ggml_backend_init_best = CUDA > Metal > Vulkan > CPU). GPU-Zugriff
# NUR via compose.gpu.yml (runtime: nvidia); ohne Overlay läuft der
# Container automatisch auf CPU (kein Dockerfile.cpu mehr).
# ==============================================================
FROM nvidia/cuda:12.8.0-runtime-ubuntu24.04

ARG CRISPASR_VERSION=v0.8.24

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg ca-certificates wget \
    && rm -rf /var/lib/apt/lists/*

# Download CrispASR pre-compiled Linux CUDA binary from GitHub release
RUN wget -q "https://github.com/CrispStrobe/CrispASR/releases/download/${CRISPASR_VERSION}/crispasr-linux-x86_64-cuda.tar.gz" \
    -O /tmp/crispasr.tar.gz && \
    tar xzf /tmp/crispasr.tar.gz -C /tmp && \
    cp /tmp/crispasr-linux-x86_64-cuda/crispasr /usr/local/bin/crispasr && \
    cp /tmp/crispasr-linux-x86_64-cuda/libc2pa_c.so /usr/local/lib/libc2pa_c.so && \
    ldconfig && \
    chmod +x /usr/local/bin/crispasr && \
    rm -rf /tmp/crispasr.tar.gz /tmp/crispasr-linux-x86_64-cuda

# Verify
RUN crispasr --help 2>&1 | head -5

# Model volume — mount GGUF files here
RUN mkdir -p /models

# HTTP-Server-Modus (OpenAI-kompatibel): Modell wird einmal geladen und
# bleibt zwischen Requests im Speicher. Modell via ARK_ASR_MODEL-Env
# (Default wie compose.backends.yml: /models/ark-asr-3b-q8_0.gguf).
EXPOSE 5095

ENV ARK_ASR_MODEL=/models/ark-asr-3b-q8_0.gguf

CMD ["sh", "-c", "exec crispasr --server -m \"$ARK_ASR_MODEL\" --host 0.0.0.0 --port 5095"]

