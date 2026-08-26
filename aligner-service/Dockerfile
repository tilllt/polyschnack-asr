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
#   - Das ORT-Artefakt v0.8.28-ort-poc1 (gleiches wie diar-service)
#     kann alle 3 Pfade: --align-only -am (qwen3-FA, wav2vec2),
#     --align (TADA mit --codec-model/--voice/--source-lang).
#
# HYBRID CPU/GPU wie diar-service: ORT-Binary versucht CUDA-EP zur
# Laufzeit (dlsym) und faellt still auf CPU zurueck; alle Aligner
# laufen ueber ggml (CPU) bzw. CUDA-ggml, je nach Build des Artefakts.
# ==============================================================
FROM nvidia/cuda:12.8.0-runtime-ubuntu24.04

ARG GIT_SHA=dev
ENV GIT_SHA=${GIT_SHA}
LABEL org.opencontainers.image.revision=${GIT_SHA}
# cuDNN 9 fuer den onnxruntime CUDA-EP (gleicher Fix wie diar-service:
# cuda-runtime-Image bringt cublas/curand/cufft mit, aber NICHT
# libcudnn.so.9). Vorher .list-Dateien entfernen (doppelte CUDA-Repo-
# Eintraege -> apt exit 100).
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg ca-certificates wget curl libopenblas0 python3 \
    && rm -f /etc/apt/sources.list.d/*.list \
    && wget -q https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/cuda-keyring_1.1-1_all.deb \
       -O /tmp/cuda-keyring.deb \
    && dpkg -i /tmp/cuda-keyring.deb && rm /tmp/cuda-keyring.deb \
    && apt-get update && apt-get install -y --no-install-recommends libcudnn9-cuda-12 \
    && rm -rf /var/lib/apt/lists/*

# CrispASR-ORT-Artefakt (gleiches wie diar-service, verifiziert
# 2026-08-26 mit allen 3 Aligner-Pfaden auf POC-Audio):
# bin/crispasr + libcrispasr.so.1 + ggml-Libs + onnxruntime 1.21.0.
ARG CRISPASR_ORT_ARTIFACT_URL=https://github.com/tilllt/CrispASR/releases/download/v0.8.28-ort-poc1/crispasr-ort-poc1.tar.gz
RUN wget -q "${CRISPASR_ORT_ARTIFACT_URL}" -O /tmp/crispasr-ort.tar.gz \
    && tar xzf /tmp/crispasr-ort.tar.gz -C /opt \
    && rm /tmp/crispasr-ort.tar.gz \
    && ln -sf /opt/crispasr-ort/bin/crispasr /usr/local/bin/crispasr \
    && chmod +x /usr/local/bin/crispasr \
    # Release-Tarball enthaelt NUR libonnxruntime.so.1.21.0 (keine
    # .so.1-Symlinks) — Link nach der hoechsten Version anlegen:
    && ortlib="$(ls -1 /opt/crispasr-ort/lib/onnxruntime/libonnxruntime.so.* 2>/dev/null | sort -Vr | head -1)" \
    && [ -n "${ortlib}" ] \
    && ln -sf "$(basename "${ortlib}")" /opt/crispasr-ort/lib/onnxruntime/libonnxruntime.so.1

ENV LD_LIBRARY_PATH=/opt/crispasr-ort/lib:/opt/crispasr-ort/lib/onnxruntime

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