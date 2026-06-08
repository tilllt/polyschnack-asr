"""Async job queue for large-audio transcription.

A single background worker pulls jobs off an asyncio.Queue and runs them through
the shared transcription core. Results are kept in an in-memory dict (PoC scope;
swap for Redis/DB for production). Decode happens inside the worker so the HTTP
handler returns a job_id immediately.
"""
from __future__ import annotations
import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .audio import load_audio
from .config import logger
from .core import transcribe_wav

QUEUED = "queued"
PROCESSING = "processing"
DONE = "done"
FAILED = "failed"


@dataclass
class Job:
    id: str
    model_name: str
    raw: bytes = field(repr=False, default=b"")
    status: str = QUEUED
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: float = 0.0
    started_at: Optional[float] = None
    finished_at: Optional[float] = None

    def public(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "job_id": self.id,
            "status": self.status,
            "model": self.model_name,
            "created_at": self.created_at,
        }
        if self.status == DONE and self.result is not None:
            out["text"] = self.result["text"]
            out["duration"] = self.result["duration"]
            out["segments"] = self.result["segments"]
            out["processing_ms"] = round((self.finished_at - self.started_at) * 1000, 1) \
                if self.started_at and self.finished_at else None
        if self.status == FAILED:
            out["error"] = self.error
        return out


class JobManager:
    def __init__(self, get_worker, clock=time.monotonic):
        self._get_worker = get_worker
        self._clock = clock
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._jobs: Dict[str, Job] = {}
        self._task: Optional[asyncio.Task] = None

    @property
    def queue_depth(self) -> int:
        return self._queue.qsize()

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="job_worker")
            logger.info("JobManager started")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass

    async def submit(self, job_id: str, raw: bytes, model_name: str) -> Job:
        job = Job(id=job_id, model_name=model_name, raw=raw, created_at=self._clock())
        self._jobs[job_id] = job
        await self._queue.put(job_id)
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    async def _run(self) -> None:
        while True:
            try:
                job_id = await self._queue.get()
            except asyncio.CancelledError:
                return
            job = self._jobs.get(job_id)
            if job is None:
                continue
            job.status = PROCESSING
            job.started_at = self._clock()
            try:
                wav = await asyncio.to_thread(load_audio, job.raw)
                if wav.size == 0:
                    raise ValueError("empty audio")
                job.result = await transcribe_wav(self._get_worker(), wav, job.model_name)
                job.status = DONE
            except Exception as exc:  # noqa: BLE001 - record any failure on the job
                logger.exception("job %s failed", job_id)
                job.status = FAILED
                job.error = f"{type(exc).__name__}: {exc}"
            finally:
                job.finished_at = self._clock()
                job.raw = b""  # free audio bytes once processed
