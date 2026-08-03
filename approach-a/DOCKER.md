# Docker Deployment Guide

This document covers Docker deployment options for PolySchnack ASR (Parakeet TDT) transcription service.

## Quick Start

Ein einziges hybrides Image (Weg 1): `onnxruntime-gpu` enthält CUDA- und
CPU-Provider — mit GPU-Zugriff (`--gpus all` / NVIDIA-Toolkit) läuft es auf
CUDA, ohne GPU automatisch auf CPU (INT8-Modell via `POLYSNACK_USE_GPU=auto`).

```bash
# Build
docker build -t polyschnack-asr:latest .

# Run (mit GPU: NVIDIA Container Toolkit nötig; ohne --gpus → CPU auto)
docker run -d --name polyschnack -p 5092:5092 \
    -v polyschnack-models:/app/models polyschnack-asr:latest

# Mit GPU explizit:
docker run -d --name polyschnack -p 5092:5092 --gpus all \
    -v polyschnack-models:/app/models polyschnack-asr:latest
```

## Endpoints

| Endpoint | Description |
|----------|-------------|
| `http://localhost:5092` | Web UI |
| `http://localhost:5092/health` | Health check |
| `http://localhost:5092/v1/audio/transcriptions` | OpenAI-compatible API |
| `http://localhost:5092/docs` | Swagger documentation |

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HF_HOME` | `/app/models` | HuggingFace model cache |
| `HF_HUB_CACHE` | `/app/models` | HuggingFace hub cache |

### Persistent Model Cache

Models are cached in a Docker volume to avoid re-downloading:

```bash
# List volumes
docker volume ls | grep polyschnack

# Inspect volume
docker volume inspect polyschnack-models

# Remove volume (forces model re-download)
docker volume rm polyschnack-models
```

## Files Created

| File | Description |
|------|-------------|
| `Dockerfile` | Hybrid-Image (onnxruntime-gpu = CUDA + CPU-Fallback, auto-detect) |
| `.dockerignore` | Excludes unnecessary files from build |

## Testing

```bash
# Check health
curl http://localhost:5092/health

# Transcribe audio (OpenAI-compatible)
curl -X POST http://localhost:5092/v1/audio/transcriptions \
    -F "file=@audio.mp3" \
    -F "model=parakeet-tdt-0.6b-v3"
```

## Troubleshooting

**Container won't start:**
- Check logs: `docker logs polyschnack-cpu`
- First startup takes ~60s to download the model

**GPU not detected:**
- Verify NVIDIA Container Toolkit: `nvidia-smi` should work inside container
- Run: `docker run --rm --gpus all nvidia/cuda:12.1.1-base-ubuntu22.04 nvidia-smi`

**Out of memory:**
- CPU image requires ~2GB RAM
- GPU image requires ~4GB VRAM
