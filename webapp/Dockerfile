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
RUN uv sync

# Copy application source
COPY app ./app

# Inject the built frontend into app/static/ so FastAPI serves it
COPY --from=fe /fe/dist ./app/static

ENV DATA_DIR=/data \
    PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
