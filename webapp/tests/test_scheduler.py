"""dispatcher/scheduler.py — Tests (Change 020 Phase 1).

Fake-InferenceBackend zählt die Interface-Aufrufe; damit werden
Backend-Auswahl (Modus/Datenklasse/Engpass/Budget), Job-Lebenszyklus
(acquire→ready→submit→poll→destroy) und der Auto-Destroy-Watchdog getestet.
"""
import time

import pytest

from app.dispatcher.backends.base import (
    DataClass,
    Endpoint,
    GpuFilter,
    InferenceBackend,
    Instance,
    JobResult,
    Offer,
)
from app.dispatcher.costs import JobCost
from app.dispatcher.scheduler import (
    NoBackendAvailable,
    Scheduler,
)


class FakeBackend(InferenceBackend):
    """Dummy-Backend mit Aufruf-Zähler und konfigurierbarem Verhalten."""

    def __init__(self, provider="local", jurisdiction="eu",
                 offers=None, fail_acquire=False, fail_poll=False,
                 poll_status="done", destroy_calls=None):
        self.provider_name = provider
        self.jurisdiction = jurisdiction
        self._offers = offers or [Offer(
            provider=provider, offer_id=f"{provider}-1", gpu_name="RTX 3060",
            vram_gb=12, price_usd_h=0.05, region="EU", reliability=0.99)]
        self.fail_acquire = fail_acquire
        self.fail_poll = fail_poll
        self.poll_status = poll_status
        self.calls = {"list_offers": 0, "acquire": 0, "wait_ready": 0,
                      "submit": 0, "poll": 0, "destroy": 0}
        self.destroy_calls = destroy_calls or []

    def list_offers(self, flt: GpuFilter) -> list[Offer]:
        self.calls["list_offers"] += 1
        return list(self._offers)

    def acquire(self, offer, image="", disk_gb=50, env=None) -> Instance:
        self.calls["acquire"] += 1
        if self.fail_acquire:
            raise RuntimeError("acquire kaputt")
        return Instance(provider=self.provider_name,
                        instance_id=f"{self.provider_name}-i1",
                        offer_id=offer.offer_id, region=offer.region,
                        status="running")

    def wait_ready(self, instance, timeout_s=900) -> Endpoint:
        self.calls["wait_ready"] += 1
        return Endpoint(url=f"http://{self.provider_name}:5092")

    def submit_job(self, endpoint, job) -> str:
        self.calls["submit"] += 1
        return "job-1"

    def poll(self, instance, job_id) -> JobResult:
        self.calls["poll"] += 1
        if self.fail_poll:
            raise RuntimeError("poll kaputt")
        if self.poll_status == "running":
            return JobResult(status="running", job_id=job_id)
        return JobResult(status=self.poll_status, job_id=job_id,
                         result_url="file:///tmp/result.json")

    def destroy(self, instance) -> None:
        self.calls["destroy"] += 1
        if self.destroy_calls is not None:
            self.destroy_calls.append(instance.instance_id)


def _scheduler(backends, **kw) -> Scheduler:
    return Scheduler(backends, **kw)


# ── Backend-Auswahl ───────────────────────────────────────────────────────

def test_local_preferred_when_queue_calm():
    local = FakeBackend("local", "eu")
    vast = FakeBackend("vast", "us")
    s = _scheduler([local, vast])
    assert s.choose_backend(DataClass.INTERNAL, queue_depth=0) is local
    assert s.choose_backend(DataClass.INTERNAL, queue_depth=2) is local


def test_remote_selected_on_engpass():
    local = FakeBackend("local", "eu")
    vast = FakeBackend("vast", "us")
    s = _scheduler([local, vast], burst_threshold=3)
    assert s.choose_backend(DataClass.INTERNAL, queue_depth=4) is vast


def test_eu_only_mode_blocks_us_backend():
    local = FakeBackend("local", "eu")
    vast = FakeBackend("vast", "us")
    s = _scheduler([local, vast], mode="stufe2")
    assert s.choose_backend(DataClass.INTERNAL, queue_depth=99) is local


def test_critical_job_never_uses_us_backend():
    local = FakeBackend("local", "eu")
    vast = FakeBackend("vast", "us")
    s = _scheduler([local, vast])  # stufe1
    assert s.choose_backend(DataClass.CRITICAL, queue_depth=99) is local


def test_no_backend_when_all_blocked():
    vast = FakeBackend("vast", "us")
    s = _scheduler([vast], mode="stufe2")
    assert s.choose_backend(DataClass.INTERNAL, queue_depth=0) is None


def test_budget_exhausted_blocks_bursting():
    local = FakeBackend("local", "eu")
    vast = FakeBackend("vast", "us")
    s = _scheduler([local, vast], monthly_budget_usd=0.01)
    s.costs.record(JobCost(
        job_id="x", provider="vast", price_usd_h=1.0, runtime_h=0.02))  # 0.02 $
    assert s.costs.over_budget()
    assert s.choose_backend(DataClass.INTERNAL, queue_depth=99) is local


# ── Job-Ausführung ────────────────────────────────────────────────────────

def test_run_job_local_lifecycle_and_destroy():
    local = FakeBackend("local", "eu")
    s = _scheduler([local])
    res = s.run_job({"audio": "chiffre"}, DataClass.INTERNAL)
    assert res.status == "done"
    assert local.calls["acquire"] == 1
    assert local.calls["wait_ready"] == 1
    assert local.calls["submit"] == 1
    assert local.calls["poll"] >= 1
    assert local.calls["destroy"] == 1  # Destroy IMMER im finally


def test_run_job_destroys_instance_on_error():
    local = FakeBackend("local", "eu", fail_poll=True)
    s = _scheduler([local])
    with pytest.raises(RuntimeError, match="poll kaputt"):
        s.run_job({"audio": "x"}, DataClass.INTERNAL)
    assert local.calls["destroy"] == 1


def test_run_job_acquire_failure_no_destroy_needed():
    local = FakeBackend("local", "eu", fail_acquire=True)
    s = _scheduler([local])
    with pytest.raises(RuntimeError, match="acquire kaputt"):
        s.run_job({"audio": "x"}, DataClass.INTERNAL)
    assert local.calls["destroy"] == 0  # nichts gemietet → kein Destroy


def test_run_job_no_backend_raises():
    vast = FakeBackend("vast", "us")
    s = _scheduler([vast], mode="stufe2")
    with pytest.raises(NoBackendAvailable):
        s.run_job({"audio": "x"}, DataClass.INTERNAL)


def test_run_job_records_costs():
    local = FakeBackend("local", "eu")
    s = _scheduler([local])
    s.run_job({"audio": "x"}, DataClass.INTERNAL)
    assert s.costs.spent_this_window() >= 0.0
    assert s.costs.summary()["jobs"] == 1


# ── Auto-Destroy-Watchdog ─────────────────────────────────────────────────

def test_watchdog_destroys_stale_instances():
    local = FakeBackend("local", "eu")
    s = _scheduler([local])
    inst = Instance(provider="local", instance_id="local-i9",
                    region="EU", status="running")
    s.track(inst)
    s._instances["local-i9"] = (inst, time.time() - 9999)  # alt
    destroyed = s.destroy_stale(ttl_s=100)
    assert destroyed == ["local-i9"]
    assert "local-i9" in (local.destroy_calls or [])


def test_watchdog_keeps_fresh_instances():
    local = FakeBackend("local", "eu")
    s = _scheduler([local])
    inst = Instance(provider="local", instance_id="local-i10",
                    region="EU", status="running")
    s.track(inst)
    assert s.destroy_stale(ttl_s=3600) == []
    assert (local.destroy_calls or []) == []
