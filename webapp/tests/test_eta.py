"""Change 082: ETA aus Audio-Dauer × RTF (app/eta)."""
from datetime import datetime, timedelta, timezone

from app.eta import elapsed_since, estimate_eta_s
from app.rtf_learner import RtfLearner


def test_pk_cpp_eta_aus_dauer():
    eta = estimate_eta_s(600.0, "crispr-pk-cpp")
    assert eta is not None
    rest, low, high = eta
    # 600 s × RTF 0.056 = 33.6 s
    assert 30 <= rest <= 37
    assert low <= rest <= high
    assert low >= 5


def test_unbekanntes_backend_keine_eta():
    # whisper-turbo: nie gemessen → bewusst keine ETA (Anti-Fake-Regel)
    assert estimate_eta_s(600.0, "crispr-whisper-turbo") is None
    assert estimate_eta_s(600.0, "gibts-nicht") is None
    assert estimate_eta_s(600.0, None) is None


def test_ohne_dauer_keine_eta():
    assert estimate_eta_s(None, "ps-pk-onnx") is None
    assert estimate_eta_s(0, "ps-pk-onnx") is None
    assert estimate_eta_s(-1, "ps-pk-onnx") is None


def test_diarization_verlaengert_eta_nach_methode():
    ohne = estimate_eta_s(600.0, "ps-pk-onnx")
    energy = estimate_eta_s(600.0, "ps-pk-onnx", enable_diarize=True, diarize_method="energy")
    pyannote = estimate_eta_s(600.0, "ps-pk-onnx", enable_diarize=True, diarize_method="pyannote")
    assert ohne is not None and energy is not None and pyannote is not None
    assert pyannote[0] > energy[0] > ohne[0]


def test_elapsed_reduziert_rest():
    frisch = estimate_eta_s(600.0, "ps-pk-onnx")
    spaet = estimate_eta_s(600.0, "ps-pk-onnx", elapsed_s=30.0)
    assert frisch is not None and spaet is not None
    assert spaet[0] < frisch[0]
    assert spaet[0] == max(0, frisch[0] - 30)


def test_elapsed_ueber_total_keine_eta():
    assert estimate_eta_s(600.0, "ps-pk-onnx", elapsed_s=99999.0) is None


def test_flags_addieren_overhead():
    basis = estimate_eta_s(600.0, "ps-pk-onnx")
    mit = estimate_eta_s(
        600.0, "ps-pk-onnx",
        enable_vad=True, enable_noise_reduce=True, enable_enhance="light",
    )
    assert basis is not None and mit is not None
    assert mit[0] > basis[0]


def test_elapsed_since_naiv_wird_als_utc_gelesen():
    aware = datetime.now(timezone.utc) - timedelta(seconds=10)
    naive = datetime.utcnow() - timedelta(seconds=10)
    for t in (aware, naive):
        assert 8 <= elapsed_since(t) <= 12


def test_elapsed_since_none_oder_zukunft_null():
    assert elapsed_since(None) == 0.0
    zukunft = datetime.now(timezone.utc) + timedelta(hours=1)
    assert elapsed_since(zukunft) == 0.0


# ── Change 085: Learner-Pfad ──────────────────────────────────────────────

def test_learner_leer_nutzt_fallback_mit_breiter_spanne():
    l = RtfLearner()
    eta = estimate_eta_s(600.0, "ps-pk-onnx", learner=l)
    assert eta is not None
    rest, low, high = eta
    assert rest == 42  # 600 × 0.071 = 42.6
    # Fallback-Spanne ±50 % statt ±30 % (noch keine Daten gelernt)
    assert low < 30
    assert high > 55


def test_learner_gelernte_faktoren_ersetzen_fallback():
    l = RtfLearner()
    for _ in range(10):
        l.ingest("asr:ps-pk-onnx", 0.05)
    eta = estimate_eta_s(600.0, "ps-pk-onnx", learner=l)
    assert eta is not None
    rest, low, high = eta
    assert 28 <= rest <= 32  # 600 × 0.05 = 30
    # identische Stichproben → enge Spanne (nicht der ±50 %-Fallback)
    assert low >= 25 and high <= 35


def test_learner_unbekannte_phase_keine_eta():
    # Backend ohne Fallback UND ohne gelernte Daten → None (Anti-Fake)
    l = RtfLearner()
    assert estimate_eta_s(600.0, "crispr-whisper-turbo", learner=l) is None


def test_learner_diar_phase_gelernt():
    l = RtfLearner()
    for _ in range(10):
        l.ingest("asr:ps-pk-onnx", 0.05)
        l.ingest("diar:energy", 0.01)
    ohne = estimate_eta_s(600.0, "ps-pk-onnx", learner=l)
    mit = estimate_eta_s(600.0, "ps-pk-onnx", learner=l,
                         enable_diarize=True, diarize_method="energy")
    assert ohne is not None and mit is not None
    assert mit[0] > ohne[0]  # Diar-Phase addiert


def test_include_align_verlaengert_eta():
    ohne = estimate_eta_s(600.0, "ps-pk-onnx")
    mit = estimate_eta_s(600.0, "ps-pk-onnx", include_align=True)
    assert ohne is not None and mit is not None
    # 600 s / 120 s-Gruppe = 5 Gruppen × 250 ms = 1.25 s extra
    assert mit[0] > ohne[0]


def test_punctuation_verlaengert_eta():
    ohne = estimate_eta_s(600.0, "ps-pk-onnx")
    mit = estimate_eta_s(600.0, "ps-pk-onnx", enable_punctuation=True)
    assert ohne is not None and mit is not None
    assert mit[0] > ohne[0]
