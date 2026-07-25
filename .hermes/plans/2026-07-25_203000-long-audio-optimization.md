# Long-Audio Transcription Optimization Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Make the ASR pipeline handle very long audio files (30min+) efficiently, with real per-chunk progress and ETA, dynamic chunk sizing, silence-skipping, and overall higher throughput.

**Architecture:** The ASR service (`approach-a/`) already has a sync path (`transcribe_wav` → `submit_many`) and a stream path (`stream_wav` → `submit`). The sync path is 2-3x faster for long audio because `submit_many` lets the BatchWorker gather all chunks and run batched GPU inference. The stream path is sequential. The plan modifies the sync path to report real chunk-level progress to the webapp, adds dynamic chunk sizing, and skips silent chunks.

**Tech Stack:** Python (ASR service), httpx (webapp → ASR), ONNX Runtime (GPU batching).

---
## Task 1: Add per-chunk progress reporting to ASR sync endpoint

**Objective:** The existing `transcribe_wav` → `submit_many` → `stitch` pipeline runs all chunks silently. Add a callback mechanism so the sync endpoint can report progress (chunks_completed / total_chunks → percentage) back to the caller via a lightweight side-channel (HTTP headers or response metadata).

**Files:**
- Modify: `approach-a/parakeet_service/core.py`
- Modify: `approach-a/parakeet_service/routes.py`

**Step 1:** Add a `progress_callback` parameter to `transcribe_wav(..., progress_callback=None)` that is called after each chunk is processed.

```python
async def transcribe_wav(worker, wav: np.ndarray, model_name: str,
                         progress_callback=None) -> Dict[str, Any]:
    duration = wav.size / TARGET_SR
    ranges = auto_chunk(wav)
    pieces = slice_chunks(wav, ranges)
    total = len(pieces)
    t1 = time.perf_counter()
    results = await worker.submit_many(pieces, model_name)
    infer_ms = (time.perf_counter() - t1) * 1000
    out = stitch(ranges, results)
    out["duration"] = duration
    out["chunks"] = total
    out["infer_ms"] = infer_ms
    logger.info("transcribe_wav model=%s dur=%.2fs chunks=%d infer=%.0fms",
                model_name, duration, total, infer_ms)
    return out
```

Change to:

```python
async def transcribe_wav(worker, wav: np.ndarray, model_name: str,
                         progress_callback=None) -> Dict[str, Any]:
    duration = wav.size / TARGET_SR
    ranges = auto_chunk(wav)
    pieces = slice_chunks(wav, ranges)
    total = len(pieces)
    t1 = time.perf_counter()
    results = []
    for i, (rng, piece) in enumerate(zip(ranges, pieces)):
        result = await worker.submit(piece, model_name)
        results.append(result)
        if progress_callback:
            await progress_callback(i + 1, total)
    infer_ms = (time.perf_counter() - t1) * 1000
    out = stitch(ranges, results)
    out["duration"] = duration
    out["chunks"] = total
    out["infer_ms"] = infer_ms
    out["progress"] = 100
    logger.info(...)
    return out
```

**NOTE:** This changes `submit_many` → individual `submit` calls, which loses GPU batching. See Risk section.

**Alternative (better):** Keep `submit_many` but wrap each future with a done-callback that updates progress:

```python
async def transcribe_wav(worker, wav, model_name, progress_callback=None):
    ...
    total = len(pieces)
    done = 0
    async def on_chunk_done(fut):
        nonlocal done
        done += 1
        if progress_callback:
            await progress_callback(done, total)
    futures = [worker.submit(p, model_name) for p in pieces]
    for f in futures:
        f.add_done_callback(lambda fut: asyncio.ensure_future(on_chunk_done(fut)))
    results = await asyncio.gather(*futures)
    ...
```

**Step 2:** In routes, modify the sync endpoint to pass a callback that updates an in-memory progress store (dict keyed by job_id).

**Step 3:** Add `GET /v1/audio/transcriptions/{job_id}/progress` endpoint that returns `{"done": N, "total": M, "pct": N/M*100}`.

**Step 4:** Commit.

**Verification:** curl the progress endpoint while a long transcription is running — it should show incrementing count.

---
## Task 2: Wire real progress into webapp backend

**Objective:** The webapp backend (`service.py` → `asr_client.py`) currently calls the ASR sync endpoint and waits. Change it to poll the progress endpoint periodically while waiting for the main task to complete.

**Files:**
- Modify: `webapp/app/asr_client.py`
- Modify: `webapp/app/service.py`

**Step 1:** Add a polling loop to `asr_client.transcribe()` — after sending the job, poll `/v1/audio/transcriptions/{job_id}/progress` every 2 seconds and pass progress to a callback.

```python
async def transcribe(audio_bytes, filename, mime, on_progress=None) -> dict:
    # Send file to ASR
    job_id = await _submit_job(audio_bytes, filename, mime)
    # Poll progress
    while True:
        p = await _get_progress(job_id)
        if on_progress:
            on_progress(p["done"], p["total"])
        if p["pct"] == 100:
            break
        await asyncio.sleep(2)
    return await _get_result(job_id)
```

**Step 2:** In `service.py`, call `set_progress(session, rec_id, pct)` inside the `on_progress` callback — this gives REAL progress instead of the current timer-based bump.

**Step 3:** Remove the timer-based progress bump thread from `service.py`.

**Step 4:** Commit.

**Verification:** Upload a long file — progress bar should move smoothly as chunks finish.

---
## Task 3: Dynamic chunk sizing

**Objective:** For audio >30min, increase chunk target to reduce total chunk count and ORT call overhead.

**Files:**
- Modify: `approach-a/parakeet_service/chunker.py`

**Step 1:** In `auto_chunk()`, add adaptive sizing: if total audio > 30min, scale TARGET_SEC:

```python
MIN_CHUNKS = 4
if total / TARGET_SR > 30 * 60:
    # Aim for ~20 chunks total for long audio
    target_samples = max(int(total / 20 / TARGET_SR) * TARGET_SR, int(CHUNK_TARGET_SEC * TARGET_SR))
else:
    target_samples = int(CHUNK_TARGET_SEC * TARGET_SR)
```

**Step 2:** Commit.

**Verification:** A 2-hour file should produce ~20 chunks instead of ~120.

---
## Task 4: Skip silent chunks

**Objective:** After VAD-based chunking, skip chunks that contain no speech (pure silence) before sending to ASR. The chunker already uses VAD to find speech segments — silent sections between them are already excluded from chunks. But verify and add a guard.

**Files:**
- Modify: `approach-a/parakeet_service/chunker.py`

**Step 1:** Add a RMS-based silence check in `slice_chunks` or after auto_chunk:

```python
def slice_chunks(wav, ranges, min_rms=1e-4):
    out = []
    for s, e in ranges:
        piece = wav[s:e]
        if np.sqrt((piece ** 2).mean()) < min_rms:
            continue  # skip near-silent chunk
        out.append(piece.copy())
    return out
```

**Step 2:** Commit.

---
## Task 5: Remove timer-based progress bump from webapp

**Objective:** The current fake progress bump thread in `service.py` is no longer needed once real progress comes from the ASR service.

**Files:**
- Modify: `webapp/app/service.py`

**Step 1:** Remove the `_progress_stop_event` / `_bump()` / threading code. Replace with a simple call that passes the `on_progress` callback.

**Step 2:** Commit.

---
## Verification

1. Upload a 10s file → should transcribe as before (no change for short files)
2. Upload a 2-hour file → progress bar increments smoothly every few seconds
3. Upload a file with long silence → silent chunks skipped, faster processing
4. ETA based on real chunk progress, not timer guess

---
## Risks & Tradeoffs

| Risk | Mitigation |
|------|------------|
| Progress poll overhead (2s interval) | Negligible — the ASR call takes minutes |
| In-memory job_id store lost on restart | Acceptable for single-worker; lost jobs get status "failed" on restart |
| Dynamic chunk sizing may degrade quality for very long audio | Cap at 180s max; VAD boundaries prevent cutting mid-word |
| Skipping silent chunks skips the last word before a long pause | VAD already pads speech segments; the risk is very low |
| GPU batching lost if switching to sequential `submit` | Keep `submit_many` + done-callbacks (not sequential) — see Task 1 alternative |

---
## Open Questions

1. **Memory:** For a 2-hour WAV file (~230MB at 16kHz/16bit), the entire `wav` array stays in memory during processing. Should we add streaming file reads?
2. **Parallel jobs:** What happens when two long files are uploaded simultaneously? The BatchWorker handles cross-request batching, but both would compete for GPU memory.
