# PolySchnack ASR (Parakeet TDT 0.6B ONNX) - hybrides Image (Weg 1)
# High-performance speech transcription — GPU (CUDA) und CPU im selben Image.
# onnxruntime-gpu enthält beide Provider; POLYSCHNACK_USE_GPU=auto wählt
# automatisch (CUDA wenn verfügbar, sonst CPU + INT8-Modell).

FROM nvidia/cuda:12.8.0-runtime-ubuntu24.04

LABEL maintainer="PolySchnack"
LABEL description="ONNX-optimized speech transcription service (GPU/CUDA)"

# Prevent interactive prompts during build
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies and Python 3.12
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12 \
    python3.12-venv \
    python3-pip \
    ffmpeg \
    && ln -sf /usr/bin/python3.12 /usr/bin/python \
    && ln -sf /usr/bin/python3.12 /usr/bin/python3 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash polyschnack
WORKDIR /app

# Copy requirements first for layer caching
COPY requirements.txt .

# Install Python dependencies with GPU support via requirements.txt
# --break-system-packages: Ubuntu 24.04 (PEP 668) blockt system-pip sonst.
# Kein "pip --upgrade pip": Debian-pip (24.0) hat keine RECORD-Datei -> Uninstall-Fehler.
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

# Copy application code
COPY server.py .
COPY polyschnack_service/ polyschnack_service/
COPY app.py .
COPY templates/ templates/
COPY polyschnack.png .

# Create directories for runtime
RUN mkdir -p temp_uploads models && \
    chown -R polyschnack:polyschnack /app

# Run as root so the model download volume works without permission issues

# Environment variables
ENV HF_HOME=/app/models
ENV HF_HUB_CACHE=/app/models
ENV HF_HUB_DISABLE_SYMLINKS_WARNING=true
ENV PYTHONUNBUFFERED=1
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility
ENV POLYSCHNACK_USE_GPU=true
ENV POLYSCHNACK_DEFAULT_MODEL=istupakov/parakeet-tdt-0.6b-v3-onnx
ENV POLYSCHNACK_BATCHED=1
ENV POLYSCHNACK_MAX_BATCH_SIZE=4
ENV POLYSCHNACK_BATCH_WINDOW_MS=4
ENV POLYSCHNACK_ORT_INTRA_THREADS=1
ENV POLYSCHNACK_AUDIO_WORKERS=8

# Expose the API port
EXPOSE 5092

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5092/health')" || exit 1

# Run the application
CMD ["python", "server.py"]
