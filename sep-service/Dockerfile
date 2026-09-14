# ==============================================================
# PolySchnack Source-Separation-Service (crispr-sep)
# ==============================================================
# Music-Removal / Vocal-Extraction als Pre-Processing für ASR +
# Forced-Aligner (Change 106): htdemucs (4 Stems) und
# mel-band-roformer (vocals/other) direkt über das CrispASR-Binary
# (--separate), GGUF-Modelle von cstr auf HuggingFace.
#
# Basis: aligner-service/Dockerfile-Muster (Builder mit CUDA,
# Runtime schlank) + CrispASR aus dem ORIGINAL-Repo CrispStrobe/CrispASR.
# Ref ueber --build-arg CRISPASR_REF waehlbar (Default s. ARG unten); der
# Fork tilllt/CrispASR ist ein veralteter Upstream-Stand, 0 eigene Commits.
#
# GPU-Pfad Mel-Band-RoFormer: unser Upstream-Port (#422, Commits vom 03./04.09.)
# liegt in main, aber NICHT im Release v0.8.32 — v0.8.32 ist 11 Commits
# AELTER als 7458ce24f ("fix(c-api,#422): forward use_gpu to
# mel-band-roformer"). Der alte Pin 81595d17 (29.08., v0.8.30) kannte den
# GPU-Pfad fuer MBR nicht: gemessen 10 s Audio = 1 min 54 s Wall /
# 16 min 46 s CPU-Zeit, kein ggml_cuda_init (htdemucs dagegen backend=CUDA0).
#
# HYBRID (wie aligner): Der CUDA-Build enthält den CPU-Backend
# (ggml_backend_init_best = CUDA > Metal > Vulkan > CPU). GPU-Zugriff
# NUR via compose.gpu.yml (runtime: nvidia); ohne Overlay läuft der
# Container automatisch auf CPU (langsam — siehe Change 106, Risiko).
# ==============================================================

# ---- Builder stage — CrispASR (Original-Repo) mit CUDA (CPU-Fallback via ggml) ----
FROM nvidia/cuda:12.8.0-devel-ubuntu24.04 AS builder

ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    git cmake build-essential \
    && rm -rf /var/lib/apt/lists/*

# CrispASR-Ref: enthaelt den Mel-Band-RoFormer-GPU-Port (#422) inkl. der
# use_gpu-Weiterleitung an der C-API (7458ce24f, 04.09.).
ARG CRISPASR_REF=7458ce24fbb3ee3516327b85db372798f1cec337

WORKDIR /src
RUN git clone --recursive https://github.com/CrispStrobe/CrispASR.git . \
    && git checkout ${CRISPASR_REF}
# CUDA-Backend explizit aktivieren (gleiches Muster wie aligner):
# -DGGML_CUDA=ON, arch 86 für RTX 3090 (sm_86), Linker-Flags für die
# Driver-Stub-Library (-lcuda) wegen BUILD_SHARED_LIBS=ON.
RUN cmake -B build -DCMAKE_BUILD_TYPE=Release \
    -DGGML_CUDA=ON \
    -DGGML_CUDA_F16=ON \
    -DCMAKE_CUDA_ARCHITECTURES=86 \
    -DCRISPASR_BUILD_EXAMPLES=ON \
    -DCRISPASR_BUILD_SERVER=ON \
    -DCRISPASR_BUILD_TESTS=OFF \
    -DCMAKE_EXE_LINKER_FLAGS="-L/usr/local/cuda/lib64/stubs -lcuda" \
    -DCMAKE_SHARED_LINKER_FLAGS="-L/usr/local/cuda/lib64/stubs -lcuda" && \
    cmake --build build -j$(nproc) --target crispasr-cli
# Shared libraries EINSAMMELN (im Builder — Runtime hat kein /src/build).
RUN mkdir -p /src/libs && find /src/build -name '*.so*' -exec cp -a {} /src/libs/ \;

# ---- Runtime stage — schlank, nur CLI + Python-stdlib-Wrapper ----
FROM nvidia/cuda:12.8.0-runtime-ubuntu24.04

ARG GIT_SHA=dev
ENV GIT_SHA=${GIT_SHA}
LABEL org.opencontainers.image.revision=${GIT_SHA}
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg ca-certificates wget curl python3 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /src/build/bin/crispasr /usr/local/bin/
COPY --from=builder /src/libs/ /usr/local/lib/
RUN ldconfig

# Source-Separation-Modelle (GGUF von cstr auf HuggingFace) — fehlen
# die Dateien, lädt der Entrypoint sie automatisch nach (Volume ':rw').
ENV SEP_HTDEMUCS_MODEL=/models/htdemucs-f16.gguf
ENV SEP_MELBAND_MODEL=/models/mel-band-roformer-vocals-f16.gguf

COPY sep_server.py /sep_server.py
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 5100

# Entrypoint prüft/lädt beide Modelle, startet dann den Wrapper-Server.
CMD ["/entrypoint.sh"]