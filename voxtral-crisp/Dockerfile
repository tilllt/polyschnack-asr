# ==============================================================
# CrispASR runtime — Voxtral-Mini-4B-Realtime (Backend voxtral4b)
# HYBRID (Weg 1): CUDA-Binary mit CPU-Fallback
# (ggml_backend_init_best = CUDA > Metal > Vulkan > CPU).
# Change 029: CrispASR-basierte Voxtral-Option für PolySchnack —
# ersetzt das vLLM-Voxtral-Backend (deterministischer Hang,
# vllm-project/vllm #52926: "empty multimodal embeddings").
# ==============================================================
FROM nvidia/cuda:12.8.0-runtime-ubuntu24.04

ARG CRISPASR_VERSION=v0.8.29

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg ca-certificates wget libopenblas0 curl \
    && rm -rf /var/lib/apt/lists/*

# Download CrispASR pre-compiled Linux CUDA + CPU binaries (Hybrid):
# Die CUDA-Binary ist hart an libcuda.so.1 gelinkt (DT_NEEDED) und startet
# ohne NVIDIA-Container-Toolkit NICHT. /usr/local/bin/crispasr ist ein
# Wrapper, der beim Start wählt: libcuda vorhanden -> CUDA, sonst CPU.
RUN wget -q "https://github.com/CrispStrobe/CrispASR/releases/download/${CRISPASR_VERSION}/crispasr-linux-x86_64-cuda.tar.gz" \
    -O /tmp/crispasr-cuda.tar.gz && \
    tar xzf /tmp/crispasr-cuda.tar.gz -C /tmp && \
    cp /tmp/crispasr-linux-x86_64-cuda/crispasr /usr/local/bin/crispasr-cuda && \
    cp /tmp/crispasr-linux-x86_64-cuda/libc2pa_c.so /usr/local/lib/libc2pa_c.so && \
    rm -rf /tmp/crispasr-cuda.tar.gz /tmp/crispasr-linux-x86_64-cuda && \
    wget -q "https://github.com/CrispStrobe/CrispASR/releases/download/${CRISPASR_VERSION}/crispasr-linux-x86_64.tar.gz" \
    -O /tmp/crispasr-cpu.tar.gz && \
    tar xzf /tmp/crispasr-cpu.tar.gz -C /tmp && \
    cp /tmp/crispasr-linux-x86_64/crispasr /usr/local/bin/crispasr-cpu && \
    rm -rf /tmp/crispasr-cpu.tar.gz /tmp/crispasr-linux-x86_64 && \
    printf '%s\n' \
      '#!/bin/sh' \
      'if ldconfig -p 2>/dev/null | grep -q "libcuda.so.1" || [ -e /usr/lib/x86_64-linux-gnu/libcuda.so.1 ]; then' \
      '  exec /usr/local/bin/crispasr-cuda "$@"' \
      'fi' \
      'echo "[crispasr-hybrid] Keine libcuda.so.1 gefunden - CPU-Backend" >&2' \
      'exec /usr/local/bin/crispasr-cpu "$@"' \
      > /usr/local/bin/crispasr && \
    chmod +x /usr/local/bin/crispasr && \
    ldconfig

# Verify: Backend voxtral4b muss in der Binary kompiliert sein.
RUN crispasr --help 2>&1 | grep -q voxtral4b

# Model volume — GGUF hier mounten (./DATA/models:/models:ro)
RUN mkdir -p /models

# OpenAI-kompatibler Server-Modus (Backend voxtral4b).
EXPOSE 5100

ENV VOXTRAL_ASR_MODEL=/models/voxtral-mini-4b-realtime-q8_0.gguf

CMD ["sh", "-c", "exec crispasr --server --backend voxtral4b -m \"$VOXTRAL_ASR_MODEL\" --host 0.0.0.0 --port 5100"]
