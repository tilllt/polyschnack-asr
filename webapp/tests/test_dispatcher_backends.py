"""Tests für dispatcher/backends — Protokoll, Modus-Regeln, LocalBackend.

Change 020: InferenceBackend-Abstraktion + Zwei-Stufen-Modus
(Stufe 1 günstig/verschlüsselt, Stufe 2 EU-only).
"""
import json

import pytest

from app.dispatcher.backends.base import (
    DataClass,
    GpuClass,
    GpuFilter,
    InferenceBackend,
    Offer,
    backend_allowed,
)
from app.dispatcher.backends.local import LocalBackend


class FakeEU(InferenceBackend):
    provider_name = "fake-eu"
    jurisdiction = "eu"
    def list_offers(self, flt): return []
    def acquire(self, offer, image="", disk_gb=50, env=None): raise NotImplementedError
    def wait_ready(self, instance, timeout_s=900): raise NotImplementedError
    def submit_job(self, endpoint, job): raise NotImplementedError
    def poll(self, instance, job_id): raise NotImplementedError
    def destroy(self, instance): return None


class FakeUS(InferenceBackend):
    provider_name = "fake-us"
    jurisdiction = "us"
    def list_offers(self, flt): return []
    def acquire(self, offer, image="", disk_gb=50, env=None): raise NotImplementedError
    def wait_ready(self, instance, timeout_s=900): raise NotImplementedError
    def submit_job(self, endpoint, job): raise NotImplementedError
    def poll(self, instance, job_id): raise NotImplementedError
    def destroy(self, instance): return None


def test_offer_dataclass():
    o = Offer(provider="theta", offer_id="x1", gpu_name="RTX 3090",
              vram_gb=24, price_usd_h=0.14, region="US")
    assert o.price_usd_h == 0.14
    assert o.vram_gb == 24


def test_backend_allowed_stufe1():
    # Stufe 1 (eu_only=False): internal erlaubt alle Backends
    assert backend_allowed(FakeUS(), DataClass.INTERNAL, eu_only=False)
    assert backend_allowed(FakeEU(), DataClass.INTERNAL, eu_only=False)
    # critical erzwingt auch in Stufe 1 EU-Jurisdiktion
    assert not backend_allowed(FakeUS(), DataClass.CRITICAL, eu_only=False)
    assert backend_allowed(FakeEU(), DataClass.CRITICAL, eu_only=False)


def test_backend_allowed_eu_only_mode():
    # Stufe 2 (eu_only=True): Nicht-EU-Backends global gesperrt
    assert not backend_allowed(FakeUS(), DataClass.INTERNAL, eu_only=True)
    assert not backend_allowed(FakeUS(), DataClass.CRITICAL, eu_only=True)
    assert backend_allowed(FakeEU(), DataClass.INTERNAL, eu_only=True)
    assert backend_allowed(FakeEU(), DataClass.CRITICAL, eu_only=True)


# ── LocalBackend ─────────────────────────────────────────────────────────

def test_local_list_offers():
    b = LocalBackend()
    offers = b.list_offers(GpuFilter())
    assert len(offers) == 1
    assert offers[0].provider == "local"
    assert offers[0].price_usd_h <= 0.1


def test_local_job_lifecycle(tmp_path):
    # run_command: schreibt result.json mit dem Job-Ordner-Pfad
    b = LocalBackend(
        run_command=(
            "python3 -c \"import json,sys; "
            "json.dump({'ok': True}, open(sys.argv[1]+'/result.json','w'))\""
        ),
        workdir=tmp_path,
    )
    inst = b.acquire(b.list_offers(GpuFilter())[0])
    ep = b.wait_ready(inst)
    job_id = b.submit_job(ep, {"audio_enc": "/tmp/x.enc"})
    # Job läuft asynchron — kurz warten, dann poll
    import time
    deadline = time.time() + 5
    res = None
    while time.time() < deadline:
        res = b.poll(inst, job_id)
        if res.status in ("done", "failed"):
            break
        time.sleep(0.05)
    assert res.status == "done"
    assert res.result_url is not None
    # job.json dokumentiert das Payload
    job_json = tmp_path / f"psjob-{job_id}" / "job.json"
    assert json.loads(job_json.read_text())["audio_enc"] == "/tmp/x.enc"


def test_local_job_failure(tmp_path):
    b = LocalBackend(run_command="exit 3", workdir=tmp_path)
    inst = b.acquire(b.list_offers(GpuFilter())[0])
    job_id = b.submit_job(b.wait_ready(inst), {"x": 1})
    import time
    deadline = time.time() + 5
    res = None
    while time.time() < deadline:
        res = b.poll(inst, job_id)
        if res.status in ("done", "failed"):
            break
        time.sleep(0.05)
    assert res.status == "failed"
    assert "3" in (res.error or "")


def test_local_destroy_is_noop():
    b = LocalBackend()
    inst = b.acquire(b.list_offers(GpuFilter())[0])
    b.destroy(inst)  # darf nicht werfen
