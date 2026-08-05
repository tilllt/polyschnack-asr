# ==============================================================
# PolySchnack Diarization Service — CrispASR-Server (Option B)
# ==============================================================
# Statt pyannote/CUDA-torch in der Webapp: eigener schlanker Container
# mit dem CrispASR-Binary und einem kleinen parakeet-Modell. Die Webapp
# ruft POST /v1/audio/transcriptions mit diarize=true auf.
# HYBRID (Weg 1): Das CUDA-Binary enthält den CPU-Backend (ggml_backend_init_best
# = CUDA > Metal > Vulkan > CPU). GPU-Zugriff NUR via compose.gpu.yml
# (runtime: nvidia); ohne Overlay läuft der Container automatisch auf CPU.
# ==============================================================
FROM nvidia/cuda:12.8.0-runtime-ubuntu24.04

ARG CRISPASR_VERSION=v0.8.25

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg ca-certificates wget curl \
    && rm -rf /var/lib/apt/lists/*

# CrispASR pre-compiled Linux CUDA binary (wie ark-asr)
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

# Model volume — parakeet GGUF hier mounten (q8_0, ~470 MB)
ENV DIAR_MODEL=/models/parakeet-tdt-0.6b-v3-q8_0.gguf

EXPOSE 5098

CMD ["sh", "-c", "exec crispasr --server -m \"$DIAR_MODEL\" --host 0.0.0.0 --port 5098"]
