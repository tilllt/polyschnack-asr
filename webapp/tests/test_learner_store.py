"""Change 085 Phase 0: learner_store — Faktor-Bildung + Persistenz."""
import pytest

from app.db import init_db
from app.learner_store import (
    align_factor,
    factor_from_phase,
    ingest_align_sample,
    ingest_job_sample,
    job_factors,
    load_learner,
    reset_estimates,
)
from app.rtf_learner import RtfLearner


@pytest.fixture(autouse=True)
def _clean_estimates():
    init_db()  # Tabelle existiert (auch auf frischer CI-DB)
    reset_estimates()
    yield
    reset_estimates()


# ── Pure Faktor-Bildung ───────────────────────────────────────────────────

def test_factor_from_phase_normal():
    # 30 s ASR auf 600 s Audio → RTF 0.05
    assert factor_from_phase(30_000.0, 600.0) == pytest.approx(0.05)


def test_factor_from_phase_ungueltige_basis_none():
    assert factor_from_phase(30_000.0, None) is None
    assert factor_from_phase(30_000.0, 0.0) is None
    assert factor_from_phase(30_000.0, -1.0) is None
    assert factor_from_phase(0.0, 600.0) is None      # < MIN_PHASE_MS
    assert factor_from_phase(0.5, 600.0) is None


def test_job_factors_filtern_ungueltige():
    f = job_factors({"asr:ps-pk-onnx": 30_000.0, "vad": 0.0}, 600.0)
    assert f == {"asr:ps-pk-onnx": pytest.approx(0.05)}


def test_align_factor():
    assert align_factor(2_500.0, 5) == pytest.approx(500.0)  # ms/Gruppe
    assert align_factor(2_500.0, 0) is None
    assert align_factor(0.5, 5) is None


# ── Persistenz / Ingest ───────────────────────────────────────────────────

def test_ingest_job_sample_schreibt_tabelle():
    n = ingest_job_sample(1, {"asr:ps-pk-onnx": 30_000.0, "vad": 1_000.0}, 600.0)
    assert n == 2
    learner = load_learner()
    assert learner.sample_count("asr:ps-pk-onnx") == 1
    assert learner.sample_count("vad") == 1


def test_ingest_kumuliert_ueber_jobs():
    for i in range(3):
        ingest_job_sample(i, {"asr:ps-pk-onnx": 30_000.0}, 600.0)
    learner = load_learner()
    assert learner.sample_count("asr:ps-pk-onnx") == 3


def test_ingest_ohne_dauer_verwirft():
    n = ingest_job_sample(1, {"asr:ps-pk-onnx": 30_000.0}, None)
    assert n == 0
    assert load_learner().keys() == []


def test_ingest_align_sample():
    assert ingest_align_sample(1, 5, 2_500.0) is True
    learner = load_learner()
    assert learner.sample_count("align") == 1
    # n=1 < N_MIN → Fallback; der gelernte Wert 500 folgt ab 10 Stichproben
    assert learner.estimate("align", fallback=250.0).factor == pytest.approx(250.0)


def test_align_gelernt_nach_10_stichproben():
    for i in range(10):
        ingest_align_sample(i, 5, 2_500.0)
    learner = load_learner()
    est = learner.estimate("align", fallback=250.0)
    assert est is not None and est.n == 10
    assert est.factor == pytest.approx(500.0)  # ms/Gruppe


def test_reset_einzeln_und_alle():
    ingest_job_sample(1, {"asr:ps-pk-onnx": 30_000.0}, 600.0)
    ingest_align_sample(1, 5, 2_500.0)
    assert reset_estimates("asr:ps-pk-onnx") == 1
    assert load_learner().keys() == ["align"]
    assert reset_estimates() == 1
    assert load_learner().keys() == []


def test_state_roundtrip_deterministisch():
    ingest_job_sample(1, {"asr:ps-pk-onnx": 30_000.0}, 600.0)
    l1 = load_learner()
    l2 = load_learner()
    assert l1.to_state() == l2.to_state()


def test_digest_invalidiert_asr_key():
    ingest_job_sample(1, {"asr:ps-pk-onnx": 30_000.0}, 600.0,
                      digest="img-a")
    ingest_job_sample(2, {"asr:ps-pk-onnx": 30_000.0}, 600.0,
                      digest="img-b")  # Image-Wechsel → Historie leer
    learner = load_learner()
    assert learner.sample_count("asr:ps-pk-onnx") == 1
    # Nicht-ASR-Keys ignorieren den Digest
    ingest_job_sample(3, {"vad": 1_000.0}, 600.0, digest="img-a")
    ingest_job_sample(4, {"vad": 1_000.0}, 600.0, digest="img-b")
    learner2 = load_learner()
    assert learner2.sample_count("vad") == 2


def test_learner_integration_pure():
    """learner_store + RtfLearner: Schätzung nach 10 Stichproben."""
    for i in range(10):
        ingest_job_sample(i, {"asr:ps-pk-onnx": 30_000.0}, 600.0)
    learner = load_learner()
    est = learner.estimate("asr:ps-pk-onnx", fallback=0.071)
    assert est is not None and est.n == 10
    assert est.factor == pytest.approx(0.05)
