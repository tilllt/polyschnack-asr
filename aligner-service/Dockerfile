# ==============================================================
# PolySchnack Forced-Aligner Service — CrispASR-Basis (Change 133)
# ==============================================================
# EIN Binary fuer ALLE 3 Aligner (qwen3-forced-aligner, TADA,
# wav2vec2-xlsr-de) — ersetzt den separaten qwen3-asr.cpp-CUDA-Build.
#
# Hintergrund (Change 133, 2026-08-26):
#   - CrispASR hat seit April 2026 einen nativen Qwen3FA-Pfad
#     (crispasr_aligner.cpp, AlignerType::Qwen3FA, Dispatch am
#     Dateinamen "forced-aligner").
#   - Das OpenVoiceOS-qwen3-forced-aligner-GGUF (bisher genutzt)
#     enthaelt die benoetigten Tensoren audio.mel_filters /
#     audio.mel_window NICHT -> "mel failed". Die CrispStrobe-
#     Konvertierung cstr/qwen3-forced-aligner-0.6b-GGUF bettet sie
#     ein -> laeuft. Wortzeiten bitweise identisch zum alten CLI.
#   - Seit 2026-08-29: Binary aus dem ORIGINAL-Repo CrispStrobe/CrispASR
#     (offizielles Release v0.8.30, ARG CRISPASR_VERSION). Der bisherige
#     ORT-POC (v0.8.28-ort-poc1, tilllt/CrispASR) war ein verworfenes GPU-
#     Experiment und wird nicht mehr genutzt. Alle 3 Aligner-Pfade laufen
#     über ggml im offiziellen Release.
#
# HYBRID CPU/GPU: CUDA-Binary (hart an libcuda.so.1) startet ohne
# NVIDIA-Container-Toolkit nicht; mit GPU-Overlay nutzt sie das
# ggml-CUDA-Backend, ohne Overlay CPU-Fallback via CPU-Binary.
# ==============================================================
FROM nvidia/cuda:12.8.0-runtime-ubuntu24.04

ARG GIT_SHA=dev
ENV GIT_SHA=${GIT_SHA}
LABEL org.opencontainers.image.revision=${GIT_SHA}
# ORT-POC (v0.8.28-ort-poc1, tilllt/CrispASR) VERWORFEN (GPU-Experiment,
# 6× langsamer als ggml-CPU) → seit 2026-08-29 offizielles Release
# CrispStrobe/CrispASR v0.8.30 (cuda-runtime-Image bringt cublas/curand/
# cufft für das ggml-CUDA-Backend mit; cuDNN wird nicht benötigt).
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg ca-certificates wget curl libopenblas0 python3 \
    && rm -rf /var/lib/apt/lists/*

# CrispASR-Binary aus dem ORIGINAL-Repo (v0.8.30, CUDA+CPU-Hybrid):
# Layout crispasr-linux-x86_64-cuda/crispasr + libc2pa_c.so (wie
# whisper-crisp). Alle 3 Aligner-Pfade (qwen3-FA, TADA, wav2vec2)
# laufen über ggml — im offiziellen Release enthalten.
ARG CRISPASR_VERSION=v0.8.30
RUN wget -q "https://github.com/CrispStrobe/CrispASR/releases/download/${CRISPASR_VERSION}/crispasr-linux-x86_64-cuda.tar.gz" \
    -O /tmp/crispasr-cuda.tar.gz \
    && tar xzf /tmp/crispasr-cuda.tar.gz -C /tmp \
    && cp /tmp/crispasr-linux-x86_64-cuda/crispasr /usr/local/bin/crispasr \
    && cp /tmp/crispasr-linux-x86_64-cuda/libc2pa_c.so /usr/local/lib/libc2pa_c.so \
    && rm -rf /tmp/crispasr-cuda.tar.gz /tmp/crispasr-linux-x86_64-cuda \
    && ldconfig

# Verify — OHNE Pipe: der Exit-Code von crispasr muss durchschlagen.
RUN crispasr --help >/dev/null 2>&1 && echo "crispasr: libraries OK"

# ------------------------------------------------------------------
# Modell-Pfade (Volume /models, Entrypoint laedt fehlende nach)
# ------------------------------------------------------------------
# qwen3-forced-aligner: CrispStrobe-GGUF MIT Mel-Tensoren (cstr/*).
# q8_0 = f16 bitweise identisch (0 Zeit-Diffs, 2026-08-26 belegt) —
# 986 MB statt 1,84 GB.
ENV ALIGNER_MODEL_QWEN3=/models/qwen3-forced-aligner-0.6b-q8_0.gguf \
    ALIGNER_MODEL_TADA=/models/tada-tts-1b-q4_k.gguf \
    ALIGNER_MODEL_TADA_CODEC=/models/tada-codec-f16.gguf \
    ALIGNER_MODEL_WAV2VEC2=/models/wav2vec2-large-xlsr-53-german-q4_k.gguf

# CrispASR-Cache fuer automatisch nachgeladene Companion-Modelle
# (tada-encoder-f16.gguf, tada-aligner-*.gguf): im Volume, damit der
# Download nur einmal passiert. Volume muss :rw sein.
ENV CRISPASR_CACHE_DIR=/models/.crispasr-cache

COPY aligner_server.py /aligner_server.py
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 5099

# Entrypoint prueft/laedt die 3 Aligner-Modelle, startet dann den
# Server mit allen Modell-Pfaden als Env.
CMD ["/entrypoint.sh"]