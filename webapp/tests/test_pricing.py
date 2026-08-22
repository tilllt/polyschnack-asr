"""Change 086: pricing.py — Kostenschicht (pure)."""
import pytest

from app.pricing import (
    ALIGN_COST_PER_MINUTE_EUR,
    LLM_COST_PER_MINUTE_EUR,
    backend_cost_per_minute,
    calculate_job_cost,
    reserve_cents,
)


def test_null_saetze_null_kosten():
    assert calculate_job_cost({"asr:ps-pk-onnx": 30_000.0}, 600.0,
                              "ps-pk-onnx", backend_cost_per_minute_eur=0.0) == 0
    assert calculate_job_cost(None, None, "x", backend_cost_per_minute_eur=0.1) == 0


def test_asr_phase_kostet_nach_satz():
    # 30 s ASR @ 0.10 EUR/min = 0.05 EUR = 5 Cent
    cost = calculate_job_cost({"asr:ps-pk-onnx": 30_000.0}, 600.0,
                              "ps-pk-onnx", backend_cost_per_minute_eur=0.10)
    assert cost == 5


def test_alle_gpu_phasen_zaehlen():
    phases = {"asr:ps-pk-onnx": 30_000.0, "vad": 2_000.0,
              "enhance:light": 3_000.0, "diar:energy": 1_000.0}
    cost = calculate_job_cost(phases, 600.0, "ps-pk-onnx",
                              backend_cost_per_minute_eur=0.10)
    # 36 s gesamt @ 0.10/min = 6 Cent
    assert cost == 6


def test_llm_und_align_anteile():
    cost = calculate_job_cost(
        {"asr:ps-pk-onnx": 30_000.0, "punc_truecase": 60_000.0},
        600.0, "ps-pk-onnx",
        backend_cost_per_minute_eur=0.10,
        llm_cost_per_minute_eur=LLM_COST_PER_MINUTE_EUR,
        align_ms=30_000.0,
        align_cost_per_minute_eur=ALIGN_COST_PER_MINUTE_EUR,
    )
    # ASR 5 Cent + LLM 60 s @ 0.02/min = 2 Cent + Align 30 s @ 0.002/min
    # = 0.001 EUR → 1 Cent (min. 1 bei Aufwand)
    assert cost == 8


def test_min_1_cent_bei_aufwand():
    # winziger Aufwand, winziger Satz → trotzdem 1 Cent (ceil)
    cost = calculate_job_cost({"asr:x": 1_000.0}, 600.0, "x",
                              backend_cost_per_minute_eur=0.001)
    assert cost >= 1


def test_altdaten_ohne_phasen_fallback_dauer():
    # 600 s @ 0.06/min = 0.6 EUR = 60 Cent (10 min × 0.06)
    cost = calculate_job_cost(None, 600.0, "x",
                              backend_cost_per_minute_eur=0.06)
    assert cost == 60


def test_phase_ohne_ms_ignoriert():
    # kein Aufwand, keine Dauer → 0
    assert calculate_job_cost({}, None, "x",
                              backend_cost_per_minute_eur=0.1) == 0
    # {} + duration = Altdaten-Fallback (bewusst): pauschale ASR-Zeit
    assert calculate_job_cost({}, 600.0, "x",
                              backend_cost_per_minute_eur=0.1) == 100


def test_reserve_obergrenze():
    # 600 s × Faktor 2.0 = 20 min @ 0.10/min = 2.00 EUR = 200 Cent
    assert reserve_cents(600.0, 2.0, 0.10) == 200


def test_reserve_ungueltig_null():
    assert reserve_cents(None, 2.0, 0.10) == 0
    assert reserve_cents(600.0, 0.0, 0.10) == 0
    assert reserve_cents(600.0, 2.0, 0.0) == 0


def test_backend_cost_from_yaml():
    # backends.yaml: alle Sätze aktuell 0.0 → 0; unbekannt → 0
    assert backend_cost_per_minute("ps-pk-onnx") == 0.0
    assert backend_cost_per_minute("gibts-nicht") == 0.0
    assert backend_cost_per_minute(None) == 0.0
