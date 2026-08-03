# Approach A — PoC notes

OpenAI-compatible PolySchnack ASR (ONNX via `onnx_asr`), FastAPI. Adapted from
[groxaxo/parakeet-tdt-0.6b-v3-fastapi-openai](https://github.com/groxaxo/parakeet-tdt-0.6b-v3-fastapi-openai).

## New modules added for the PoC

| File | Purpose |
|---|---|
| `polyschnack_service/core.py` | Shared decode→chunk→infer→stitch. Sync, stream, async all use it. |
| `polyschnack_service/streaming.py`* | (logic lives in `core.stream_wav`) per-chunk async generator |
| `polyschnack_service/jobs.py` | Async job queue (`asyncio.Queue` + background worker) + in-memory job store |
| `polyschnack_service/metrics.py` | Thread-safe counters (requests, errors, latency p95) |

\* streaming generator is in `core.py`; routing in `routes.py`.

## Endpoints

| Method | Path | Notes |
|---|---|---|
| POST | `/v1/audio/transcriptions` | OpenAI-compat. `response_format=json\|text\|srt\|vtt\|verbose_json` |
| POST | `/v1/audio/transcriptions/stream` | SSE; one `data:` event per VAD chunk; last has `final:true` |
| POST | `/v1/audio/transcriptions/async` | → `202 {job_id, status:"queued"}` |
| GET | `/v1/audio/jobs/{job_id}` | → `{status: queued\|processing\|done\|failed, text?, ...}` |
| GET | `/metrics` | `{queue_depth, total_requests, total_errors, avg_latency_ms, p95_latency_ms}` |
| GET | `/health` | `{status:"ok", model, device, ...}` |
| POST | `/v1/audio/transcriptions/batch` | non-OpenAI multi-file helper (pre-existing) |

## Run (CPU, Docker)

```bash
docker compose --profile cpu up -d --build polyschnack-cpu
# first boot downloads the int8 model (~600MB) to the polyschnack-models volume
curl localhost:5092/health
```

GPU (Linux server, NVIDIA Container Toolkit):
```bash
docker compose up -d --build polyschnack-gpu
```

## Benchmark + fixtures (host tooling, uv)

```bash
uv sync
uv run python scripts/gen_test_audio.py          # -> ../tests/audio/*.wav (+ .txt refs)
uv run python benchmark.py --runs 3 --concurrency 3   # -> ../results/approach-a.{json,md}
```

## CPU / low-RAM gotchas (found during validation on Apple M1, 2.8GB Docker VM)

The process gets **OOM-killed (silent, no traceback)** when peak inference memory
is too high. Two independent causes, both fixed via env (siehe `compose.yml`, `asr`-Service):

1. **Long single chunk** — a 60s+ audio = one ORT `recognize()` over a long
   sequence → large activation memory. Fixed by capping the sliding window:
   `POLYSNACK_CHUNK_SECONDS=120`, `POLYSNACK_CHUNK_OVERLAP_SECONDS=15`.
2. **Parallel chunk inference** — `InferencePool` fans chunks across
   `POLYSNACK_INFER_WORKERS` threads → N× model working set. Fixed by serializing:
   `POLYSNACK_INFER_WORKERS=1`.

On the real Linux/GPU target (more RAM, GPU memory) these caps can be relaxed;
GPU mode uses the single-threaded `BatchWorker` already.

### Other fixes
- `requirements.txt` / `Dockerfile.cpu` pinned `onnxruntime(-gpu)==1.26.0` which
  **does not exist** (max published is 1.23.2). Repinned to `1.23.2`.

## Deviation from spec
Spec: "audio >60s auto-routes to the async queue." Implemented as an **explicit**
`/async` endpoint instead — auto-routing the OpenAI `/v1/audio/transcriptions`
path would break clients expecting an inline text response. Large-audio async is
opt-in by the caller.
