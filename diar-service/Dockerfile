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

# CrispASR-Version: v0.8.28 (2026-08-16) — Longfile-Diarize-Fix.
# v0.8.25 hatte den parakeet-Longform-Bug (#350: unified dispatch routet
# chunked long-form in einen Single-Full-Length-Decode → ganze Spans
# still verloren; Fix #352 "long-form drops whole spans on 30-300 s
# non-JA audio", gemergt nach v0.8.25). Live-Befund 2026-08-16 mit
# v0.8.25: 51-min-Datei bricht bei 636 s ab, 295-s-Clips bei 54-184 s.
ARG CRISPASR_VERSION=v0.8.28

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg ca-certificates wget curl libopenblas0 \
    && rm -rf /var/lib/apt/lists/*

# CrispASR pre-compiled Linux CUDA binary (wie ark-asr)
# CrispASR pre-compiled binaries — CUDA UND CPU im selben Image (Hybrid):
# Die CUDA-Binary ist hart an libcuda.so.1 gelinkt (DT_NEEDED) und startet
# ohne NVIDIA-Container-Toolkit NICHT (exit 127, "error while loading shared
# libraries: libcuda.so.1"). /usr/local/bin/crispasr ist deshalb ein Wrapper,
# der beim Start wählt: libcuda vorhanden (GPU-Overlay) -> CUDA-Binary,
# sonst CPU-Fallback (ggml CPU-Backend).
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

# Verify
RUN crispasr --help 2>&1 | head -5

# Model volume — parakeet GGUF hier mounten (q8_0, ~640 MB). Fehlt die
# Datei, lädt der Entrypoint sie automatisch von HuggingFace nach
# (Volume muss dafür beschreibbar sein, also KEIN ':ro').
ENV DIAR_MODEL=/models/parakeet-tdt-0.6b-v3-q8_0.gguf

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 5098

# Entrypoint prüft/lädt das Modell, startet dann den CrispASR-Server.
CMD ["/entrypoint.sh"]
