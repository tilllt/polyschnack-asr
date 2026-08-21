# --------------------------------------------------------------------------- #
# Stage 1 — build the React SPA                                               #
# --------------------------------------------------------------------------- #
FROM node:20-slim AS fe

WORKDIR /fe

# Install deps first for layer caching
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install

# Copy the rest of the frontend source and build
COPY frontend/ .
RUN npm run build
# Vite outputs to dist/ by default

# --------------------------------------------------------------------------- #
# Stage 2 — Python API + static SPA                                           #
# --------------------------------------------------------------------------- #
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Resolve Python deps first for layer caching
COPY pyproject.toml ./
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg nodejs git && rm -rf /var/lib/apt/lists/*
# Node.js als JS-Runtime für yt-dlp (YouTube-JS-Challenge, seit 2026 Pflicht):
# ohne Node/Deno scheitert der YouTube-Import mit 403 "no supported
# JavaScript runtime was found" (Bot-Schutz der Player-Challenge).
RUN uv pip install --system "yt-dlp>=2026.05.29"
RUN uv sync
# Kein torch/torchaudio in der Webapp (Change 060): Diarization läuft im
# separaten CrispASR-diar-Container, VAD nutzt silero_vad.onnx direkt via
# onnxruntime (das PyPI-Paket silero-vad zog torch transitiv ins Image —
# ~2,5-3 GB). Die Webapp bleibt CPU-only; GPU-Zugriff bekommen asr + diar
# via compose.gpu.yml.

# Copy application source
COPY app ./app

# Inject the built frontend into app/static/ so FastAPI serves it
COPY --from=fe /fe/dist ./app/static

ENV DATA_DIR=/data \
    PYTHONUNBUFFERED=1

EXPOSE 8088

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8088"]
