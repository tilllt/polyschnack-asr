# PolySchnack ASR Whisper (faster-whisper large-v3) — OpenAI-kompatible API.
# Modell lädt beim Container-Start von HuggingFace (HF_HOME=/app/models),
# GPU (CUDA, int8_float16) mit CPU-Fallback (int8).

FROM nvidia/cuda:12.8.0-runtime-ubuntu24.04

LABEL maintainer="PolySchnack"
LABEL description="Whisper large-v3 transcription service (faster-whisper, GPU/CUDA + CPU-Fallback)"

ENV DEBIAN_FRONTEND=noninteractive

# Systemdependencies + Python 3.12 (Muster approach-a)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12 \
    python3.12-venv \
    python3-pip \
    ffmpeg \
    && ln -sf /usr/bin/python3.12 /usr/bin/python \
    && ln -sf /usr/bin/python3.12 /usr/bin/python3 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

RUN useradd --create-home --shell /bin/bash polyschnack
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

COPY server.py .

RUN mkdir -p models && chown -R polyschnack:polyschnack /app

ENV HF_HOME=/app/models
ENV HF_HUB_CACHE=/app/models
ENV HF_HUB_DISABLE_SYMLINKS_WARNING=true
ENV PYTHONUNBUFFERED=1
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility
ENV ASR_MODEL=large-v3
ENV COMPUTE_TYPE=int8_float16

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=240s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["python", "server.py"]
