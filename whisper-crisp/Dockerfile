# ==============================================================
# CrispASR runtime — OpenAI Whisper (Backend whisper)
# HYBRID (Weg 1): CUDA-Binary mit CPU-Fallback
# (ggml_backend_init_best = CUDA > Metal > Vulkan > CPU).
# Change 029: CrispASR-basierte Whisper-Option für PolySchnack
# (zusätzlich zu faster-whisper build-whisper; nutzt Whisper-GGUF
# im whisper.cpp-Format, z. B. ggml-large-v3-turbo-q5_0.bin).
# 2026-08-30: auf v0.8.30 angehoben (wie diar/aligner) — v0.8.29-Tarball
# ist monolithisch (keine libggml-*-Trennung), die Hybrid-Verify-
# Invarianten (ldd + exe-dir-Backend-Libs + diagnostics) gelten nur für
# die v0.8.30-Lib-Struktur.
# ==============================================================
FROM nvidia/cuda:12.8.0-runtime-ubuntu24.04

ARG GIT_SHA=dev
ENV GIT_SHA=${GIT_SHA}
LABEL org.opencontainers.image.revision=${GIT_SHA}
ARG CRISPASR_VERSION=v0.8.30

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
    cp /tmp/crispasr-linux-x86_64-cuda/*.so* /usr/local/lib/ && \
    cp /tmp/crispasr-linux-x86_64-cuda/libggml-cpu.so /usr/local/bin/libggml-cpu.so && \
    cp /tmp/crispasr-linux-x86_64-cuda/libggml-cuda.so /usr/local/bin/libggml-cuda.so && \
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

# Verify: Backend whisper muss in der Binary kompiliert sein.
# 2026-08-30: CUDA-Binary zusaetzlich auf fehlende Shared Libs pruefen
# (Wrapper-Verify deckt in CI nur den CPU-Pfad ab — libcrispasr.so.1/
# libggml fehlten im Image → Crash 127 mit GPU-Overlay). Invariante:
# NUR libcuda.so.1 darf "not found" sein (kommt vom NVIDIA-Runtime).
# 2026-08-30 (2): ggml laedt Backend-Plugins aus dem EXE-Verzeichnis
# (/usr/local/bin) — ohne libggml-cpu/cuda.so dort: 0 Backends →
# GGML_ASSERT(backend) + SIGSEGV beim Modell-Init (Box, GPU-Overlay).
RUN missing=$(ldd /usr/local/bin/crispasr-cuda | grep "not found" | grep -v "libcuda.so.1" || true); \
    if [ -n "$missing" ]; then echo "FEHLENDE LIBS: $missing"; exit 1; fi; \
    test -f /usr/local/bin/libggml-cpu.so && test -f /usr/local/bin/libggml-cuda.so || { echo "FEHLT: ggml-Backend-Libs im exe-dir"; exit 1; }; \
    n=$(crispasr-cuda --diagnostics 2>&1 | grep -o "registered backends: [0-9]*" | head -1 | grep -o "[0-9]*"); \
    if [ "${n:-0}" = "0" ]; then echo "ggml registriert keine Backends"; exit 1; fi; \
    echo "ggml backends OK (n=$n)"; \
    crispasr --help 2>&1 | grep -q whisper

# Model volume — GGUF/.bin hier mounten (./DATA/models:/models:ro)
RUN mkdir -p /models

# OpenAI-kompatibler Server-Modus (Backend whisper).
EXPOSE 5101

ENV WHISPER_ASR_MODEL=/models/ggml-large-v3-turbo-q5_0.bin

CMD ["sh", "-c", "exec crispasr --server --backend whisper -m \"$WHISPER_ASR_MODEL\" --host 0.0.0.0 --port 5101"]