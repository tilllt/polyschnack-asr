# ==============================================================
# PolySchnack Forced-Aligner-Service
# ==============================================================
# Schlanker Container nach dem diar-service-Muster: qwen3-asr.cpp
# (qwen3-asr-cli) + qwen3-forced-aligner-0.6b-f16 GGUF + kleiner
# Python-stdlib-HTTP-Wrapper (aligner_server.py).
#
# Der Aligner ist ein einzelner, nicht-autoregressiver Forward-Pass:
# Audio + Referenztext -> präzise Word-Level-Timestamps (80-ms-Bins,
# max. 400 s Audio pro Pass). Die Webapp alignet ihre 120-s-ASR-Chunks.
#
# HYBRID (Weg 1): Der CUDA-Build enthält den CPU-Backend
# (ggml_backend_init_best = CUDA > Metal > Vulkan > CPU). GPU-Zugriff
# NUR via compose.gpu.yml (runtime: nvidia); ohne Overlay läuft der
# Container automatisch auf CPU.
# ==============================================================

# ---- Builder stage — qwen3-asr.cpp mit CUDA (CPU-Fallback via ggml) ----
FROM nvidia/cuda:12.8.0-devel-ubuntu24.04 AS builder

ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    git cmake build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN git clone --recursive https://github.com/predict-woo/qwen3-asr.cpp.git .
RUN cmake -B build -DCMAKE_BUILD_TYPE=Release && \
    cmake --build build -j$(nproc)

# ---- Runtime stage — schlank, nur CLI + Python-stdlib-Wrapper ----
FROM nvidia/cuda:12.8.0-runtime-ubuntu24.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg ca-certificates wget curl python3 \
    && rm -rf /var/lib/apt/lists/*

# Nur der CLI wird gebraucht (Alignment ist CLI-Modus: --align / -o)
COPY --from=builder /src/build/qwen3-asr-cli /usr/local/bin/

# Shared library: Upstream linkt die CLI dynamisch gegen libqwen3-asr.so;
# ohne sie scheitert jeder Aufruf ("error while loading shared libraries").
# WICHTIG: direkt aus der Builder-Stage kopieren — die Runtime-Stage hat
# KEIN /src/build (dort war der frühere find-Befehl wirkungslos: find auf
# nicht-existentem Pfad + ldconfig-Exit 0 = Build "erfolgreich" ohne Lib,
# Regression 2026-08-14, gleicher Fix wie im qwen3-Backend-Image).
COPY --from=builder /src/build/libqwen3-asr.so* /usr/local/lib/
RUN ldconfig

# Forced-Aligner-Modell (GGUF, ~1,8 GB) — fehlt die Datei, lädt der
# Entrypoint sie automatisch von HuggingFace nach (Volume ':rw' nötig).
ENV ALIGNER_MODEL=/models/qwen3-forced-aligner-0.6b-f16.gguf

COPY aligner_server.py /aligner_server.py
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 5099

# Entrypoint prüft/lädt das Modell, startet dann den Wrapper-Server.
CMD ["/entrypoint.sh"]
