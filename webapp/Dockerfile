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

ARG GIT_SHA=dev
ENV GIT_SHA=${GIT_SHA}
LABEL org.opencontainers.image.revision=${GIT_SHA}
WORKDIR /app

# Resolve Python deps first for layer caching
COPY pyproject.toml ./
# fonts-liberation + fontconfig: Change 201 misst die Untertitelbreite mit der
# echten Schrift (fc-match loest Arial auf Liberation Sans auf, wie im
# Render-Container).
RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg nodejs git fontconfig fonts-liberation \
    && rm -rf /var/lib/apt/lists/* /var/cache/fontconfig \
    && fc-cache -f >/dev/null
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

# Change 201: Die Schriftmessung muss im Image funktionieren — sonst bleibt
# fit_mode wirkungslos und meldet nur "fit_unavailable". Deshalb hier messen,
# nicht erst im Betrieb (Lehre: der Bau prueft, was der Dienst benutzt).
# Wichtig: `uv run` — dasselbe Python wie im CMD unten. Das nackte `python`
# des Basis-Images kennt die Projektabhaengigkeiten nicht (PIL fehlte).
RUN uv run python -c "\
from PIL import ImageFont; \
import subprocess; \
p = subprocess.run(['fc-match', '-f', '%{file}', 'Arial:bold'], capture_output=True, text=True).stdout.strip(); \
assert p, 'fc-match findet keine Schrift fuer Arial'; \
w = ImageFont.truetype(p, 100).getlength('Hallo Welt'); \
assert w > 0, 'Textmessung liefert 0'; \
print('Schriftmessung OK:', p.split('/')[-1], round(w, 1), 'px bei 100')"

ENV DATA_DIR=/data \
    PYTHONUNBUFFERED=1

EXPOSE 8088

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8088"]