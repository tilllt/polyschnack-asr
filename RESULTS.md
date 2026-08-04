# PolySchnack ASR Server — PoC Results

> ⚠️ **HISTORISCH (2026-07, PoC-Phase).** Dieses Dokument beschreibt die
> ursprüngliche PoC-Evaluierung von Approach A (Python/ONNX) auf einer
> Apple-M1-Entwicklungsmaschine. Das Projekt ist seitdem weit darüber
> hinausgewachsen: Multi-Backend-Architektur (CrispASR-hybride Backends),
> Webapp mit Diarization (eigener `diar`-Container), OIDC-Workspaces,
> Segment-Editor, Sharing, Post-Processing. Die aktuellen Architektur- und
> Deploy-Infos stehen in der [README](README.md); WER-Vergleiche der Backends
> laufen über das separate Repo `polyschnack-benchmark` (CommonVoice-DE-Korpus).
> Die Zahlen unten sind nur noch als PoC-Referenz (CPU-Baseline) relevant.

## Approaches

| Approach | Stack | Status |
|---|---|---|
| A | Python / FastAPI + ONNX (`onnx_asr`), adapted from groxaxo | ✅ built, CPU-validated |
| B | Rust + sherpa-onnx | ⬜ not started |
| C | Python + NeMo baseline | ⬜ not started |

## Approach A — what was added on top of groxaxo

Base repo already had: `POST /v1/audio/transcriptions` (OpenAI-compat), `/health`,
`/healthz`, `/v1/audio/transcriptions/batch`, ONNX inference pool, Silero-VAD chunking,
Dockerfile.gpu/cpu + compose.

Added for the PoC:
- **SSE streaming** — `POST /v1/audio/transcriptions/stream`, one `data:` event per VAD chunk.
- **Async jobs** — `POST /v1/audio/transcriptions/async` → `{job_id}`; `GET /v1/audio/jobs/{id}` → status + result. In-memory queue + background worker (PoC scope).
- **/metrics** — `{queue_depth, total_requests, avg_latency_ms, p95_latency_ms, total_errors}`.
- **/health** extended with `status:"ok"`, `model`, `device` (cpu|cuda).
- Refactored shared decode→chunk→infer→stitch into `core.py` so sync/stream/async share one path.

### Deviation from spec
Spec said "audio >60s auto-routes to async queue". **Not implemented as auto-routing** —
that would break OpenAI clients calling `/v1/audio/transcriptions` and expecting text back.
Instead: explicit `/async` endpoint. Large-audio handling is opt-in by the caller.

## Measured — Approach A on CPU

Host: Apple M1 Pro, Docker Desktop (Linux **arm64** VM, **2 CPUs / 2.8 GiB**) — a
deliberately small box. INT8 model (`parakeet-tdt-0.6b-v3`), serial inference.

| Fixture | Audio dur | p50 | p95 | RTF | WER† |
|---|---|---|---|---|---|
| short_10s | 13.9s | 2.09s | 2.62s | 0.14 | 0.037 |
| medium_60s | 64.3s | 8.31s | 9.24s | 0.13 | 0.070 |
| long_30min (async) | 1800s | — | — | 0.11 | — |

- **Throughput** (5 concurrent, short): 0.75 req/s — *serialized through one ORT
  thread on purpose* (see memory note in `approach-a/POC_NOTES.md`); not the real
  throughput ceiling.
- **Streaming**: incremental — medium_60s → 4 SSE events (chunk 0→3, `final:true`
  on last); short (single chunk) → 1 event @1.1s.
- **30 min audio**: async job `done` in ~231s wall, no crash, peak RAM ~1.3 GiB.

† WER inflated by case/punctuation mismatch (gTTS reference has caps+punct, ASR
output is lowercase/no-punct). Real WER is lower; treat as a rough upper bound.

## Acceptance criteria

| Criterion | Target | Approach A — CPU (this box) | GPU 4GB (Linux server) |
|---|---|---|---|
| Latency 10s | <500ms GPU / <3s CPU | ✅ p50 2.09s | deferred (no NVIDIA here) |
| Throughput | >5 req/s GPU | n/a (CPU serialized) | deferred |
| 30min audio | no crash, returns | ✅ async done ~231s | deferred |
| OpenAI-compat | client unmodified | ✅ `/v1/audio/transcriptions` | deferred |
| Streaming | first tokens <1s for >30s | ⚠️ incremental ✅, first event ~2–3s on this 2-CPU box (chunk must infer first); <1s is GPU-bound | deferred |
| Docker GPU 4GB | no OOM | n/a | **deferred — must verify on target** |
| Docker CPU | works | ✅ | — |

Raw: `results/approach-a.{json,md}`.

## Key risks carried to the GPU target
1. **GPU 4GB OOM untested** — FP32 GPU default may not fit 4GB; may need the
   `grikdotnet/...-fp16` model or INT8 on GPU. Verify on the NVIDIA box.
2. `onnxruntime-gpu==1.23.2` must match the server's CUDA/cuDNN.
3. CPU memory caps (`INFER_WORKERS=1`, chunk 25s, arena off) can be relaxed on a
   bigger host — they exist only to fit this 2.8 GiB VM.
