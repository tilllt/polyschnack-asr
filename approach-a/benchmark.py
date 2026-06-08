"""Async benchmark client for the Parakeet ASR server (approach-a).

Exercises all server endpoints and writes results to results/approach-a.{json,md}.

Usage:
    uv run python benchmark.py [options]

Options:
    --base-url   Server base URL  (default: http://localhost:5092)
    --audio-dir  Path to test WAV fixtures  (default: <repo-root>/tests/audio)
    --concurrency  Parallel workers for throughput test  (default: 5)
    --runs       Sequential runs per fixture for latency stats  (default: 5)
    --out        Output directory for results  (default: <repo-root>/results)

Example:
    uv run python benchmark.py --base-url http://localhost:5092 --concurrency 8

Generate fixtures first:
    uv run python scripts/gen_test_audio.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import subprocess
import sys
import time
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

try:
    from jiwer import wer as compute_wer
    HAS_JIWER = True
except ImportError:
    HAS_JIWER = False

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent
# Repo root = parakeet-asr-server/
REPO_ROOT = _THIS_DIR.parent
DEFAULT_AUDIO_DIR = REPO_ROOT / "tests" / "audio"
DEFAULT_RESULTS_DIR = REPO_ROOT / "results"

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------
Metrics = Dict[str, Any]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def wav_duration(path: Path) -> float:
    """Return duration in seconds of a WAV file without ffprobe."""
    with wave.open(str(path), "rb") as wf:
        return wf.getnframes() / wf.getframerate()


def percentile(data: List[float], p: float) -> float:
    """Compute p-th percentile (0-100) of a sorted or unsorted list."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    idx = (p / 100) * (len(sorted_data) - 1)
    lo = int(idx)
    hi = lo + 1
    if hi >= len(sorted_data):
        return sorted_data[-1]
    frac = idx - lo
    return sorted_data[lo] + frac * (sorted_data[hi] - sorted_data[lo])


def latency_stats(times: List[float]) -> Dict[str, float]:
    if not times:
        return {"p50": 0.0, "p95": 0.0, "p99": 0.0, "mean": 0.0, "min": 0.0, "max": 0.0}
    return {
        "p50": percentile(times, 50),
        "p95": percentile(times, 95),
        "p99": percentile(times, 99),
        "mean": statistics.mean(times),
        "min": min(times),
        "max": max(times),
    }


def read_reference(audio_path: Path) -> Optional[str]:
    txt = audio_path.with_suffix(".txt")
    if txt.exists():
        return txt.read_text(encoding="utf-8").strip()
    return None


def calc_wer(reference: str, hypothesis: str) -> Optional[float]:
    if not HAS_JIWER:
        return None
    if not reference or not hypothesis:
        return None
    try:
        return float(compute_wer(reference, hypothesis))
    except Exception:
        return None


def maybe_vram_mb(device: str) -> Optional[float]:
    """Try to read GPU VRAM usage via nvidia-smi (only on CUDA devices)."""
    if device != "cuda":
        return None
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            timeout=5,
        )
        return float(out.decode().strip().splitlines()[0])
    except Exception:
        return None


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------
async def check_health(client: httpx.AsyncClient, base_url: str) -> Dict[str, Any]:
    resp = await client.get(f"{base_url}/health", timeout=10)
    resp.raise_for_status()
    return resp.json()


async def get_metrics(client: httpx.AsyncClient, base_url: str) -> Dict[str, Any]:
    resp = await client.get(f"{base_url}/metrics", timeout=10)
    resp.raise_for_status()
    return resp.json()


async def post_transcription(
    client: httpx.AsyncClient,
    base_url: str,
    wav_path: Path,
    response_format: str = "json",
) -> tuple[Dict[str, Any], float]:
    """POST to /v1/audio/transcriptions.  Returns (response_body_dict, elapsed_s)."""
    audio_bytes = wav_path.read_bytes()
    t0 = time.perf_counter()
    resp = await client.post(
        f"{base_url}/v1/audio/transcriptions",
        files={"file": (wav_path.name, audio_bytes, "audio/wav")},
        data={"model": "parakeet-tdt-0.6b-v3", "response_format": response_format},
        timeout=120,
    )
    elapsed = time.perf_counter() - t0
    resp.raise_for_status()
    if response_format == "text":
        return {"text": resp.text}, elapsed
    return resp.json(), elapsed


async def post_stream(
    client: httpx.AsyncClient,
    base_url: str,
    wav_path: Path,
) -> Dict[str, Any]:
    """POST to /v1/audio/transcriptions/stream.  Returns stream metrics."""
    audio_bytes = wav_path.read_bytes()
    events: List[Dict[str, Any]] = []
    time_to_first: Optional[float] = None
    t0 = time.perf_counter()

    async with client.stream(
        "POST",
        f"{base_url}/v1/audio/transcriptions/stream",
        files={"file": (wav_path.name, audio_bytes, "audio/wav")},  # type: ignore[arg-type]
        data={"model": "parakeet-tdt-0.6b-v3"},
        timeout=180,
    ) as resp:
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            payload = line[len("data:"):].strip()
            if not payload:
                continue
            elapsed = time.perf_counter() - t0
            if time_to_first is None:
                time_to_first = elapsed
            try:
                ev = json.loads(payload)
                ev["_elapsed_s"] = elapsed
                events.append(ev)
            except json.JSONDecodeError:
                pass

    total_elapsed = time.perf_counter() - t0
    full_text = " ".join(
        ev.get("text", "") for ev in events if not ev.get("error")
    ).strip()

    return {
        "time_to_first_event_s": time_to_first,
        "total_elapsed_s": total_elapsed,
        "num_events": len(events),
        "text": full_text,
        "incremental": len(events) > 1,
    }


async def post_async_job(
    client: httpx.AsyncClient,
    base_url: str,
    wav_path: Path,
) -> str:
    """POST to /v1/audio/transcriptions/async.  Returns job_id."""
    audio_bytes = wav_path.read_bytes()
    resp = await client.post(
        f"{base_url}/v1/audio/transcriptions/async",
        files={"file": (wav_path.name, audio_bytes, "audio/wav")},
        data={"model": "parakeet-tdt-0.6b-v3"},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["job_id"]


async def poll_job(
    client: httpx.AsyncClient,
    base_url: str,
    job_id: str,
    poll_interval: float = 2.0,
    timeout: float = 3600,
) -> Dict[str, Any]:
    """Poll /v1/audio/jobs/{job_id} until done or failed."""
    t0 = time.perf_counter()
    while True:
        elapsed = time.perf_counter() - t0
        if elapsed > timeout:
            return {"status": "timeout", "elapsed_s": elapsed}
        resp = await client.get(f"{base_url}/v1/audio/jobs/{job_id}", timeout=30)
        resp.raise_for_status()
        job = resp.json()
        if job.get("status") in ("done", "failed"):
            job["elapsed_s"] = elapsed
            return job
        await asyncio.sleep(poll_interval)


# ---------------------------------------------------------------------------
# Benchmark suites
# ---------------------------------------------------------------------------
async def bench_latency(
    client: httpx.AsyncClient,
    base_url: str,
    wav_path: Path,
    runs: int,
    device: str,
) -> Metrics:
    """Sequential latency benchmark for a single fixture."""
    duration = wav_duration(wav_path)
    latencies: List[float] = []
    errors: List[str] = []
    last_text = ""

    for i in range(runs):
        try:
            body, elapsed = await post_transcription(client, base_url, wav_path)
            latencies.append(elapsed)
            last_text = body.get("text", "")
        except Exception as exc:
            errors.append(f"run {i}: {exc}")

    stats = latency_stats(latencies)
    rtf = stats["mean"] / duration if duration > 0 and stats["mean"] > 0 else None

    reference = read_reference(wav_path)
    wer_score = calc_wer(reference, last_text) if reference else None

    vram_mb = maybe_vram_mb(device)

    return {
        "fixture": wav_path.name,
        "audio_duration_s": round(duration, 2),
        "runs": runs,
        "latency_s": {k: round(v, 3) for k, v in stats.items()},
        "rtf": round(rtf, 4) if rtf is not None else None,
        "wer": round(wer_score, 4) if wer_score is not None else None,
        "vram_mb": vram_mb,
        "errors": errors,
    }


async def bench_throughput(
    client: httpx.AsyncClient,
    base_url: str,
    wav_path: Path,
    concurrency: int,
) -> Metrics:
    """Fire `concurrency` concurrent requests and measure req/s."""
    errors: List[str] = []

    async def one_request() -> Optional[float]:
        try:
            _, elapsed = await post_transcription(client, base_url, wav_path)
            return elapsed
        except Exception as exc:
            errors.append(str(exc))
            return None

    t0 = time.perf_counter()
    results = await asyncio.gather(*[one_request() for _ in range(concurrency)])
    wall_time = time.perf_counter() - t0

    successful = [r for r in results if r is not None]
    rps = len(successful) / wall_time if wall_time > 0 else 0.0

    return {
        "fixture": wav_path.name,
        "concurrency": concurrency,
        "successful_requests": len(successful),
        "failed_requests": len(errors),
        "wall_time_s": round(wall_time, 3),
        "req_per_s": round(rps, 3),
        "errors": errors,
    }


async def bench_stream(
    client: httpx.AsyncClient,
    base_url: str,
    wav_path: Path,
    device: str,
) -> Metrics:
    """Stream benchmark: time-to-first-event and total time."""
    try:
        result = await post_stream(client, base_url, wav_path)
        wer_score = None
        reference = read_reference(wav_path)
        if reference and result.get("text"):
            wer_score = calc_wer(reference, result["text"])

        vram_mb = maybe_vram_mb(device)
        return {
            "fixture": wav_path.name,
            "time_to_first_event_s": round(result["time_to_first_event_s"] or 0, 3),
            "total_elapsed_s": round(result["total_elapsed_s"], 3),
            "num_events": result["num_events"],
            "incremental": result["incremental"],
            "wer": round(wer_score, 4) if wer_score is not None else None,
            "vram_mb": vram_mb,
            "error": None,
        }
    except Exception as exc:
        return {
            "fixture": wav_path.name,
            "error": str(exc),
        }


async def bench_async_job(
    client: httpx.AsyncClient,
    base_url: str,
    wav_path: Path,
) -> Metrics:
    """Async job benchmark: submit + poll until completion."""
    try:
        t0 = time.perf_counter()
        job_id = await post_async_job(client, base_url, wav_path)
        job_result = await poll_job(client, base_url, job_id)
        total = time.perf_counter() - t0

        return {
            "fixture": wav_path.name,
            "job_id": job_id,
            "final_status": job_result.get("status"),
            "total_wall_time_s": round(total, 2),
            "has_text": bool(job_result.get("text")),
            "error": job_result.get("error"),
        }
    except Exception as exc:
        return {
            "fixture": wav_path.name,
            "error": str(exc),
        }


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------
def _fmt(val: Any, decimals: int = 3, suffix: str = "") -> str:
    if val is None:
        return "n/a"
    if isinstance(val, float):
        return f"{val:.{decimals}f}{suffix}"
    return str(val)


def build_markdown_report(
    health: Dict[str, Any],
    server_metrics: Dict[str, Any],
    latency_results: List[Metrics],
    throughput: Metrics,
    stream_result: Metrics,
    async_result: Metrics,
    device: str,
) -> str:
    lines = ["# Parakeet ASR Server — Approach A Benchmark", ""]
    lines += [
        "## Server Info",
        f"- Device: `{device}`",
        f"- Model: `{health.get('model', 'n/a')}`",
        f"- Total requests (server): {server_metrics.get('total_requests', 'n/a')}",
        f"- Avg latency (server): {_fmt(server_metrics.get('avg_latency_ms'), 1, ' ms')}",
        f"- P95 latency (server): {_fmt(server_metrics.get('p95_latency_ms'), 1, ' ms')}",
        f"- Queue depth: {server_metrics.get('queue_depth', 'n/a')}",
        "",
    ]

    if device == "cpu":
        lines += [
            "> **Note:** Running on CPU. VRAM metrics require an NVIDIA GPU.",
            "",
        ]

    # Latency table
    lines += [
        "## Latency — `/v1/audio/transcriptions`",
        "",
        "| Fixture | Duration | Runs | p50 (s) | p95 (s) | p99 (s) | Mean (s) | RTF | WER | VRAM (MB) |",
        "|---------|----------|------|---------|---------|---------|----------|-----|-----|-----------|",
    ]
    for r in latency_results:
        ls = r.get("latency_s", {})
        lines.append(
            f"| {r['fixture']} "
            f"| {_fmt(r.get('audio_duration_s'), 1, 's')} "
            f"| {r.get('runs', '-')} "
            f"| {_fmt(ls.get('p50'))} "
            f"| {_fmt(ls.get('p95'))} "
            f"| {_fmt(ls.get('p99'))} "
            f"| {_fmt(ls.get('mean'))} "
            f"| {_fmt(r.get('rtf'), 4)} "
            f"| {_fmt(r.get('wer'), 4)} "
            f"| {_fmt(r.get('vram_mb'), 0)} |"
        )
    lines.append("")

    # Throughput
    lines += [
        "## Throughput — Concurrent requests on `short_10s.wav`",
        "",
        f"- Concurrency: {throughput.get('concurrency')}",
        f"- Successful: {throughput.get('successful_requests')}  /  Failed: {throughput.get('failed_requests')}",
        f"- Wall time: {_fmt(throughput.get('wall_time_s'), 2, 's')}",
        f"- **Req/s: {_fmt(throughput.get('req_per_s'), 2)}**",
        "",
    ]

    # Stream
    lines += [
        "## Streaming — `/v1/audio/transcriptions/stream`",
        "",
    ]
    if stream_result.get("error"):
        lines.append(f"**Error:** {stream_result['error']}")
    else:
        lines += [
            f"- Fixture: {stream_result.get('fixture')}",
            f"- Time to first event: {_fmt(stream_result.get('time_to_first_event_s'), 3, 's')}",
            f"- Total elapsed: {_fmt(stream_result.get('total_elapsed_s'), 3, 's')}",
            f"- Events received: {stream_result.get('num_events')}",
            f"- Incremental (>1 event): {stream_result.get('incremental')}",
            f"- WER: {_fmt(stream_result.get('wer'), 4)}",
        ]
    lines.append("")

    # Async job
    lines += [
        "## Async Job — `/v1/audio/transcriptions/async`",
        "",
    ]
    if async_result.get("error"):
        lines.append(f"**Error:** {async_result['error']}")
    else:
        lines += [
            f"- Fixture: {async_result.get('fixture')}",
            f"- Job ID: `{async_result.get('job_id')}`",
            f"- Final status: `{async_result.get('final_status')}`",
            f"- Total wall time: {_fmt(async_result.get('total_wall_time_s'), 1, 's')}",
            f"- Has text result: {async_result.get('has_text')}",
        ]
    lines.append("")

    lines += [
        "---",
        "*RTF = processing_time / audio_duration (lower is better)*  ",
        "*WER = Word Error Rate against reference transcript (lower is better)*  ",
        "*VRAM = GPU memory used (null when device=cpu)*",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------
async def run_benchmark(
    base_url: str,
    audio_dir: Path,
    concurrency: int,
    runs: int,
    out_dir: Path,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient() as client:
        # ---- Health check ------------------------------------------------
        print("Checking /health ...")
        try:
            health = await check_health(client, base_url)
            device = health.get("device", "cpu")
            print(f"  status={health.get('status')}  model={health.get('model')}  device={device}")
        except Exception as exc:
            print(f"ERROR: /health failed: {exc}")
            sys.exit(1)

        # ---- Server metrics snapshot -------------------------------------
        print("Fetching /metrics ...")
        try:
            server_metrics = await get_metrics(client, base_url)
        except Exception as exc:
            print(f"  Warning: /metrics failed: {exc}")
            server_metrics = {}

        # ---- Fixture paths -----------------------------------------------
        short_wav = audio_dir / "short_10s.wav"
        medium_wav = audio_dir / "medium_60s.wav"
        long_wav = audio_dir / "long_30min.wav"

        fixtures = [(short_wav, "short_10s"), (medium_wav, "medium_60s")]
        for p, name in fixtures:
            if not p.exists():
                print(f"  Warning: {p} not found — run gen_test_audio.py first")

        # ---- Latency tests -----------------------------------------------
        latency_results: List[Metrics] = []
        for wav_path, label in fixtures:
            if not wav_path.exists():
                latency_results.append({"fixture": wav_path.name, "error": "file not found"})
                continue
            print(f"\nLatency benchmark: {label} ({runs} runs) ...")
            try:
                result = await bench_latency(client, base_url, wav_path, runs, device)
                latency_results.append(result)
                ls = result["latency_s"]
                print(
                    f"  p50={ls['p50']:.3f}s  p95={ls['p95']:.3f}s  "
                    f"RTF={result.get('rtf', 'n/a')}  WER={result.get('wer', 'n/a')}"
                )
            except Exception as exc:
                print(f"  ERROR: {exc}")
                latency_results.append({"fixture": wav_path.name, "error": str(exc)})

        # ---- Throughput test ---------------------------------------------
        print(f"\nThroughput benchmark: {concurrency} concurrent on short_10s ...")
        throughput: Metrics = {"fixture": "short_10s.wav", "error": "file not found"}
        if short_wav.exists():
            try:
                throughput = await bench_throughput(client, base_url, short_wav, concurrency)
                print(f"  {throughput['req_per_s']:.2f} req/s  "
                      f"({throughput['successful_requests']} ok / {throughput['failed_requests']} fail)")
            except Exception as exc:
                print(f"  ERROR: {exc}")
                throughput = {"fixture": "short_10s.wav", "error": str(exc)}

        # ---- Stream test -------------------------------------------------
        print("\nStream benchmark: short_10s ...")
        stream_result: Metrics = {"fixture": "short_10s.wav", "error": "file not found"}
        if short_wav.exists():
            try:
                stream_result = await bench_stream(client, base_url, short_wav, device)
                if stream_result.get("error"):
                    print(f"  ERROR: {stream_result['error']}")
                else:
                    print(
                        f"  first_event={stream_result['time_to_first_event_s']:.3f}s  "
                        f"total={stream_result['total_elapsed_s']:.3f}s  "
                        f"events={stream_result['num_events']}  "
                        f"incremental={stream_result['incremental']}"
                    )
            except Exception as exc:
                print(f"  ERROR: {exc}")
                stream_result = {"fixture": "short_10s.wav", "error": str(exc)}

        # ---- Async job test ----------------------------------------------
        print("\nAsync job benchmark: long_30min (submit + poll) ...")
        async_result: Metrics = {"fixture": "long_30min.wav", "error": "file not found"}
        if long_wav.exists():
            try:
                async_result = await bench_async_job(client, base_url, long_wav)
                if async_result.get("error"):
                    print(f"  ERROR: {async_result['error']}")
                else:
                    print(
                        f"  status={async_result['final_status']}  "
                        f"wall_time={async_result['total_wall_time_s']:.1f}s  "
                        f"has_text={async_result['has_text']}"
                    )
            except Exception as exc:
                print(f"  ERROR: {exc}")
                async_result = {"fixture": "long_30min.wav", "error": str(exc)}

        # ---- Write outputs -----------------------------------------------
        json_path = out_dir / "approach-a.json"
        md_path = out_dir / "approach-a.md"

        raw: Dict[str, Any] = {
            "health": health,
            "server_metrics_snapshot": server_metrics,
            "latency": latency_results,
            "throughput": throughput,
            "stream": stream_result,
            "async_job": async_result,
            "config": {
                "base_url": base_url,
                "audio_dir": str(audio_dir),
                "concurrency": concurrency,
                "runs": runs,
            },
        }

        json_path.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nJSON results -> {json_path}")

        md = build_markdown_report(
            health=health,
            server_metrics=server_metrics,
            latency_results=latency_results,
            throughput=throughput,
            stream_result=stream_result,
            async_result=async_result,
            device=device,
        )
        md_path.write_text(md, encoding="utf-8")
        print(f"MD  results -> {md_path}")
        print("\nBenchmark complete.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark the Parakeet ASR server (approach-a)."
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:5092",
        help="Server base URL (default: http://localhost:5092)",
    )
    parser.add_argument(
        "--audio-dir",
        type=Path,
        default=DEFAULT_AUDIO_DIR,
        help=f"Directory containing .wav fixtures (default: {DEFAULT_AUDIO_DIR})",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="Number of concurrent requests for throughput test (default: 5)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=5,
        help="Sequential runs per fixture for latency stats (default: 5)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_RESULTS_DIR,
        help=f"Output directory for results (default: {DEFAULT_RESULTS_DIR})",
    )
    args = parser.parse_args()

    asyncio.run(
        run_benchmark(
            base_url=args.base_url,
            audio_dir=args.audio_dir,
            concurrency=args.concurrency,
            runs=args.runs,
            out_dir=args.out,
        )
    )


if __name__ == "__main__":
    main()
