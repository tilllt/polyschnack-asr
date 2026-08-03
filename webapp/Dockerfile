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
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
RUN uv pip install --system "yt-dlp>=2026.05.29"
RUN uv sync
# CUDA-torch für GPU-Diarization (Hybrid): pyannote läuft mit CUDA, wenn der
# Container GPU-Zugriff hat (compose.gpu.yml → runtime: nvidia), sonst CPU —
# gleiches Image für beide Fälle (device auto-detect in app/diarize.py).
# Versionen müssen zur uv.lock passen (pyannote-Constraints) — per ARG
# anpassbar, wenn der CUDA-Index eine andere Minor-Version führt.
# Achtung: macht das Image ~2-3 GB größer; CPU-torch allein wäre kleiner,
# würde aber GPU-Diarization im selben Container unmöglich machen.
ARG TORCH_VERSION=2.13.0
ARG TORCHAUDIO_VERSION=2.11.0
# cu126 (nicht cu124!): nur dieser Index führt die Lock-Versionen torch
# 2.13.0 / torchaudio 2.11.0 — cu124 endet bei 2.6.0.
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cu126
RUN uv pip install --system --index-url ${TORCH_INDEX_URL} \
    torch==${TORCH_VERSION} torchaudio==${TORCHAUDIO_VERSION}

# Copy application source
COPY app ./app

# Inject the built frontend into app/static/ so FastAPI serves it
COPY --from=fe /fe/dist ./app/static

ENV DATA_DIR=/data \
    PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
