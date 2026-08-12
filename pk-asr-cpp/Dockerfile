# ==============================================================
# PolySchnack parakeet.cpp — CrispASR-Server mit parakeet-Backend
# ==============================================================
# Weg-1-Umbau: ersetzt das externe mudler/parakeet.cpp-server-Image
# durch ein eigenes hybrides CrispASR-Image (gleiches GGUF-Modell
# cstr/parakeet-tdt-0.6b-v3-GGUF q8_0 wie im diar-Service).
#
# CrispASR erkennt das parakeet-Backend automatisch aus den GGUF-
# Metadaten; Word-Timestamps nativ via -ml 1. OpenAI-kompatibler
# Server (POST /v1/audio/transcriptions).
#
# HYBRID (Weg 1): Das CUDA-Binary enthält den CPU-Backend
# (ggml_backend_init_best = CUDA > Metal > Vulkan > CPU). GPU-Zugriff
# NUR via compose.gpu.yml (runtime: nvidia); ohne Overlay läuft der
# Container automatisch auf CPU. Kein Dockerfile.cpu mehr.
# ==============================================================
FROM nvidia/cuda:12.8.0-runtime-ubuntu24.04

ARG CRISPASR_VERSION=v0.8.25

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg ca-certificates wget curl libopenblas0 \
    && rm -rf /var/lib/apt/lists/*

# CrispASR pre-compiled Linux CUDA binary (wie ark-asr/diar)
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
ENV CPP_ASR_MODEL=/models/parakeet-tdt-0.6b-v3-q8_0.gguf

# Residenter Post-Prozessor: Interpunktion (fullstop = EN/DE/FR/IT) +
# deutsches Truecasing (lstm, 97,9% F1) — parakeet emittiert selbst
# keine Satzzeichen, das übernimmt der Server. Modelle auto-download
# nach ~/.cache/crispasr. Per Env überschreibbar (compose.backends.yml).
ENV CRISPASR_EXTRA_ARGS="--punc-model fullstop --truecase-model lstm"

EXPOSE 5093

CMD ["sh", "-c", "exec crispasr --server -m \"$CPP_ASR_MODEL\" -ml 1 --host 0.0.0.0 --port 5093 $CRISPASR_EXTRA_ARGS"]
