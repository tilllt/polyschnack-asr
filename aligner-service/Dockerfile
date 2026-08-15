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
# CUDA-Backend explizit aktivieren (Review/Fix 2026-08-15): ohne
# -DGGML_CUDA=ON linkt ggml auf Linux NUR den CPU-Backend — der Aligner
# lief trotz runtime: nvidia auf CPU (f16-Modell, 60-min-Datei = Stunden).
# -DCMAKE_CUDA_ARCHITECTURES=86 deckt die RTX-3090 (sm_86) ab; weitere
# Architekturen (z.B. 89/90) bei Bedarf ergänzen.
RUN cmake -B build -DCMAKE_BUILD_TYPE=Release \
    -DGGML_CUDA=ON \
    -DGGML_CUDA_F16=ON \
    -DCMAKE_CUDA_ARCHITECTURES=86 && \
    cmake --build build -j$(nproc)
# Shared libraries EINSAMMELN (im Builder!): Upstream linkt CLI dynamisch
# gegen libqwen3-asr.so UND die ggml-Familie (libggml.so.0,
# libggml-base.so.0, libggml-cpu.so.0 …) — sie liegen verstreut im
# Build-Output (ggml-Submodule). Die Runtime-Stage hat KEIN /src/build;
# deshalb hier bündeln und per COPY übernehmen (Regression 2026-08-14:
# find lief in der Runtime-Stage ins Leere → „erfolgreicher" Build ohne Lib).
RUN mkdir -p /src/libs && find /src/build -name '*.so*' -exec cp -a {} /src/libs/ \;

# ---- Runtime stage — schlank, nur CLI + Python-stdlib-Wrapper ----
FROM nvidia/cuda:12.8.0-runtime-ubuntu24.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg ca-certificates wget curl python3 \
    && rm -rf /var/lib/apt/lists/*

# Nur der CLI wird gebraucht (Alignment ist CLI-Modus: --align / -o)
COPY --from=builder /src/build/qwen3-asr-cli /usr/local/bin/

# Shared libraries aus der Builder-Stage übernehmen (dort gebündelt in
# /src/libs; die Runtime-Stage hat kein /src/build — siehe Builder oben).
COPY --from=builder /src/libs/ /usr/local/lib/
RUN ldconfig

# Forced-Aligner-Modell (GGUF, ~1,8 GB) — fehlt die Datei, lädt der
# Entrypoint sie automatisch von HuggingFace nach (Volume ':rw' nötig).
ENV ALIGNER_MODEL=/models/qwen3-forced-aligner-0.6b-f16.gguf

COPY aligner_server.py /aligner_server.py
COPY openapi.json /app/openapi.json
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 5099

# Entrypoint prüft/lädt das Modell, startet dann den Wrapper-Server.
CMD ["/entrypoint.sh"]
