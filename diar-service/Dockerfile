# ==============================================================
# PolySchnack Diarization Service — CrispASR-Server (Option B, ORT/GPU)
# ==============================================================
# Statt pyannote/CUDA-torch in der Webapp: eigener schlanker Container
# mit dem CrispASR-Binary und einem kleinen parakeet-Modell. Die Webapp
# ruft POST /v1/audio/transcriptions mit diarize=true auf.
#
# WEG B ist beendet (2026-08-29): Der ORT-POC war ein GPU-Experiment und
# wurde verworfen (6× langsamer als ggml-CPU). Seitdem wird das Binary
# aus dem ORIGINAL-Repo CrispStrobe/CrispASR gezogen (offizielles Release
# v0.8.30, ARG CRISPASR_VERSION). Der Server läuft mit parakeet-GGUF +
# foxnose-Diarize + wespeaker-Embedder (alles ggml).
#
# HYBRID: Die CUDA-Binary ist hart an libcuda.so.1 gelinkt und startet
# ohne NVIDIA-Container-Toolkit nicht; ohne GPU-Overlay (compose.gpu.yml)
# läuft der Container nicht (CPU-Fallback via ggml wäre nur über die
# CPU-Binary — hier nicht vorgesehen).
# ==============================================================
FROM nvidia/cuda:12.8.0-runtime-ubuntu24.04

ARG GIT_SHA=dev
ENV GIT_SHA=${GIT_SHA}
LABEL org.opencontainers.image.revision=${GIT_SHA}
# ORT-POC (v0.8.28-ort-poc1, tilllt/CrispASR) VERWORFEN (2026-08-17:
# ORT/GPU-Weg 6× langsamer als ggml-CPU; die .onnx-Diarize-Modelle
# werden nicht genutzt) → seit 2026-08-29 offizielles Release
# CrispStrobe/CrispASR v0.8.30 (das cuda-runtime-Image bringt cublas/
# curand/cufft für das ggml-CUDA-Backend mit; cuDNN wird nicht benötigt).
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg ca-certificates wget curl libopenblas0 \
    && rm -rf /var/lib/apt/lists/*

# CrispASR-Binary aus dem ORIGINAL-Repo (v0.8.30, CUDA+CPU-Hybrid):
# Layout crispasr-linux-x86_64-cuda/crispasr + libc2pa_c.so (wie
# whisper-crisp). Der Server läuft mit parakeet-GGUF (ggml) + foxnose-
# Diarize + wespeaker-Embedder (ggml) — alles im offiziellen Release.
ARG CRISPASR_VERSION=v0.8.30
RUN wget -q "https://github.com/CrispStrobe/CrispASR/releases/download/${CRISPASR_VERSION}/crispasr-linux-x86_64-cuda.tar.gz" \
    -O /tmp/crispasr-cuda.tar.gz \
    && tar xzf /tmp/crispasr-cuda.tar.gz -C /tmp \
    && cp /tmp/crispasr-linux-x86_64-cuda/crispasr /usr/local/bin/crispasr \
    && cp /tmp/crispasr-linux-x86_64-cuda/libc2pa_c.so /usr/local/lib/libc2pa_c.so \
    && rm -rf /tmp/crispasr-cuda.tar.gz /tmp/crispasr-linux-x86_64-cuda \
    && ldconfig

# Verify — OHNE Pipe: der Exit-Code von crispasr muss durchschlagen
# (2026-08-16: `crispasr --help | head -5` maskierte den Crash — Build
#  wurde gruen, obwohl libonnxruntime.so.1 fehlte → kaputtes Image).
RUN crispasr --help >/dev/null 2>&1 && echo "crispasr: libraries OK"

# Model volume — parakeet GGUF hier mounten (q8_0, ~640 MB). Fehlt die
# Datei, lädt der Entrypoint sie automatisch von HuggingFace nach
# (Volume muss dafür beschreibbar sein, also KEIN ':ro').
ENV DIAR_MODEL=/models/parakeet-tdt-0.6b-v3-q8_0.gguf

# Diarize-Modelle (pyannote-seg + Embedder): IMMER via CrispASR-"auto"
# (GGUF-Download in CRISPASR_CACHE_DIR, s. entrypoint.sh). Die .onnx-
# Modelle im Artefakt (pyannote-seg-3-0, TitaNet) werden NICHT mehr
# genutzt: der --diarize-embedder-Weg ist GGUF-only (wespeaker.cpp), und
# der ORT/GPU-Weg ist widerlegt (2026-08-17, 6× langsamer als ggml-CPU).

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 5098

# Entrypoint prüft/lädt das Modell, startet dann den CrispASR-Server.
CMD ["/entrypoint.sh"]