"""Lightweight in-process metrics (thread-safe; audio decode runs in a pool)."""
from __future__ import annotations
import threading
from collections import deque
from typing import Deque, Dict


class Metrics:
    def __init__(self, window: int = 1000):
        self._lock = threading.Lock()
        self.total_requests = 0
        self.total_errors = 0
        self._latencies: Deque[float] = deque(maxlen=window)

    def record(self, latency_ms: float, ok: bool = True) -> None:
        with self._lock:
            self.total_requests += 1
            if not ok:
                self.total_errors += 1
            self._latencies.append(latency_ms)

    def snapshot(self, queue_depth: int = 0) -> Dict[str, float]:
        with self._lock:
            lat = sorted(self._latencies)
            n = len(lat)
            avg = sum(lat) / n if n else 0.0
            p95 = lat[min(n - 1, int(n * 0.95))] if n else 0.0
        return {
            "queue_depth": queue_depth,
            "total_requests": self.total_requests,
            "total_errors": self.total_errors,
            "avg_latency_ms": round(avg, 1),
            "p95_latency_ms": round(p95, 1),
        }
