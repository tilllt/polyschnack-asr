# PolySchnack ASR Server — Approach A Benchmark

## Server Info
- Device: `cpu`
- Model: `parakeet-tdt-0.6b-v3`
- Total requests (server): 0
- Avg latency (server): 0.0 ms
- P95 latency (server): 0.0 ms
- Queue depth: 0

> **Note:** Running on CPU. VRAM metrics require an NVIDIA GPU.

## Latency — `/v1/audio/transcriptions`

| Fixture | Duration | Runs | p50 (s) | p95 (s) | p99 (s) | Mean (s) | RTF | WER | VRAM (MB) |
|---------|----------|------|---------|---------|---------|----------|-----|-----|-----------|
| short_10s.wav | 14.4s | 5 | 2.089 | 2.624 | 2.672 | 2.073 | 0.1436 | 0.0370 | n/a |
| medium_60s.wav | 64.3s | 5 | 8.308 | 9.244 | 9.386 | 8.130 | 0.1264 | 0.0702 | n/a |

## Throughput — Concurrent requests on `short_10s.wav`

- Concurrency: 5
- Successful: 5  /  Failed: 0
- Wall time: 6.66s
- **Req/s: 0.75**

## Streaming — `/v1/audio/transcriptions/stream`

- Fixture: short_10s.wav
- Time to first event: 1.117s
- Total elapsed: 1.121s
- Events received: 1
- Incremental (>1 event): False
- WER: 0.0370

## Async Job — `/v1/audio/transcriptions/async`

- Fixture: long_30min.wav
- Job ID: `07ae850651d24894903968a1268d07d8`
- Final status: `done`
- Total wall time: 231.5s
- Has text result: True

---
*RTF = processing_time / audio_duration (lower is better)*  
*WER = Word Error Rate against reference transcript (lower is better)*  
*VRAM = GPU memory used (null when device=cpu)*