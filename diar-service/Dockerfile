# ==============================================================
# PolySchnack Diarization Service — CrispASR-Server (Option B, ORT/GPU)
# ==============================================================
# Statt pyannote/CUDA-torch in der Webapp: eigener schlanker Container
# mit dem CrispASR-Binary und einem kleinen parakeet-Modell. Die Webapp
# ruft POST /v1/audio/transcriptions mit diarize=true auf.
#
# WEG B (Übergang, bis PR #364 upstream gemerged ist): Das Binary wird
# NICHT aus dem Source gebaut, sondern als verifiziertes Artefakt vom
# Fork-Release tilllt/CrispASR gezogen (crispasr-ort-poc1: CRISPASR_
# USE_ONNXRUNTIME=ON, onnxruntime-gpu 1.21.0, CUDA EP verifiziert auf
# RTX 3060: pyannote-seg + TitaNet als CUDA EP, 2-Sprecher-Referenz A B A B).
# Nach dem Upstream-Merge zurück aufs offizielle Release stellen (ARG).
#
# HYBRID: Das ORT-Binary versucht den CUDA-EP zur Laufzeit (dlsym) und
# fällt still auf CPU zurück; ohne GPU-Overlay (compose.gpu.yml) läuft
# der Container automatisch auf CPU. parakeet-ASR läuft über ggml (CPU).
# ==============================================================
FROM nvidia/cuda:12.8.0-runtime-ubuntu24.04

# cuDNN 9 für den onnxruntime CUDA-EP: das cuda-runtime-Image bringt
# cublas/curand/cufft mit, aber NICHT libcudnn.so.9 — ORT 1.21 verlangt
# cuDNN 9 (1.19.x wollte cuDNN 8, fiel sonst still auf CPU zurück).
# WICHTIG (CI-Fix 2026-08-16): das nvidia/cuda-Base-Image bringt bereits
# eigene /etc/apt/sources.list.d/*.list-Einträge für das CUDA-Repo mit →
# cuda-keyring würde eine ZWEITE Repo-Liste anlegen → apt bricht mit
# "Conflicting values set for option Signed-By" ab (exit 100). Vorher alle
# .list-Dateien entfernen (die Ubuntu-24.04-Basis nutzt .sources/deb822 in
# /etc/apt/sources.list.d/ubuntu.sources — die bleibt unangetastet):
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg ca-certificates wget curl libopenblas0 \
    && rm -f /etc/apt/sources.list.d/*.list \
    && wget -q https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/cuda-keyring_1.1-1_all.deb \
       -O /tmp/cuda-keyring.deb \
    && dpkg -i /tmp/cuda-keyring.deb && rm /tmp/cuda-keyring.deb \
    && apt-get update && apt-get install -y --no-install-recommends libcudnn9-cuda-12 \
    && rm -rf /var/lib/apt/lists/*

# CrispASR-ORT-Artefakt (Weg B): bin/crispasr + libcrispasr.so.1 +
# ggml-Libs + onnxruntime 1.21.0 (libonnxruntime + CUDA-Provider) +
# .onnx-Diarize-Modelle (pyannote-seg-3-0, TitaNet, 3dspeaker).
# GLIBC-Hinweis: Binary wurde auf Ubuntu-22.04-Basis gebaut und läuft
# auf 24.04 (abwärtskompatibel).
ARG CRISPASR_ORT_ARTIFACT_URL=https://github.com/tilllt/CrispASR/releases/download/v0.8.28-ort-poc1/crispasr-ort-poc1.tar.gz
RUN wget -q "${CRISPASR_ORT_ARTIFACT_URL}" -O /tmp/crispasr-ort.tar.gz \
    && tar xzf /tmp/crispasr-ort.tar.gz -C /opt \
    && rm /tmp/crispasr-ort.tar.gz \
    && ln -sf /opt/crispasr-ort/bin/crispasr /usr/local/bin/crispasr \
    && chmod +x /usr/local/bin/crispasr \
    # Das Release-Tarball enthält NUR libonnxruntime.so.1.21.0 (keine .so.1-
    # Symlinks!) — der Dynamic Linker matcht exakt den SONAME .so.1 → ohne
    # Link crasht das Binary trotz korrektem LD_LIBRARY_PATH. Link nach der
    # höchsten Version anlegen (fix: ORT 1.21.0; sort -V robust bei Wechsel):
    && ortlib="$(ls -1 /opt/crispasr-ort/lib/onnxruntime/libonnxruntime.so.* 2>/dev/null | sort -Vr | head -1)" \
    && [ -n "${ortlib}" ] \
    && ln -sf "$(basename "${ortlib}")" /opt/crispasr-ort/lib/onnxruntime/libonnxruntime.so.1

ENV LD_LIBRARY_PATH=/opt/crispasr-ort/lib:/opt/crispasr-ort/lib/onnxruntime

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
