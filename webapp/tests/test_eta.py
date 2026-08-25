"""Change 082: ETA aus Audio-Dauer × RTF (app/eta)."""
from datetime import datetime, timedelta, timezone

from app.eta import elapsed_since, estimate_align_eta_s, estimate_diar_eta_s, estimate_eta_s
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


# ── Change 127: Rediarize-ETA (nur Diar-Phase, methoden-getrennt) ────────

def test_diar_eta_fallback_pyannote():
    """600 s Audio × DIAR_RTF-Fallback → Rest = Dauer × RTF; Spanne breit."""
    from app.eta import DIAR_RTF

    rtf = DIAR_RTF["pyannote"]
    eta = estimate_diar_eta_s(600.0, "pyannote")
    assert eta is not None
    rest, low, high = eta
    assert rest == round(600.0 * rtf)
    assert low < rest < high


def test_diar_eta_elapsed_wird_abgezogen():
    from app.eta import DIAR_RTF

    rtf = DIAR_RTF["pyannote"]
    rest = estimate_diar_eta_s(600.0, "pyannote", elapsed_s=120.0)
    assert rest is not None and rest[0] == round(600.0 * rtf) - 120


def test_diar_eta_none_ohne_dauer():
    assert estimate_diar_eta_s(None, "pyannote") is None
    assert estimate_diar_eta_s(0.0, "pyannote") is None


def test_diar_eta_lernt_methoden_getrennt():
    """Change 127: foxnose/pyannote werden getrennt gelernt — die ETA
    muss den gelernten Wert der jeweils aktiven Methode nutzen."""
    learner = RtfLearner(n_min=1)
    for _ in range(10):
        learner.ingest("diar:foxnose", 0.5)
        learner.ingest("diar:pyannote", 2.0)
    rest_f = estimate_diar_eta_s(600.0, "foxnose", learner=learner)
    rest_p = estimate_diar_eta_s(600.0, "pyannote", learner=learner)
    assert rest_f is not None and rest_f[0] == 300   # 600 × 0.5
    assert rest_p is not None and rest_p[0] == 1200  # 600 × 2.0


# ── Change 127: Align-ETA (Background-Alignment, gleiches Muster) ───────

def test_align_eta_fallback():
    """600 s Audio → 5 Gruppen à 120 s; Fallback 250 ms/Gruppe →
    Faktor 1.25 → Rest 750 s; Spanne breit."""
    from app.eta import ALIGN_MS_PER_GROUP_FALLBACK

    eta = estimate_align_eta_s(600.0)
    assert eta is not None
    rest, low, high = eta
    assert rest == round(600.0 * (ALIGN_MS_PER_GROUP_FALLBACK / 1000.0) * 5)
    assert low < rest < high


def test_align_eta_elapsed_wird_abgezogen():
    from app.eta import ALIGN_MS_PER_GROUP_FALLBACK

    f = (ALIGN_MS_PER_GROUP_FALLBACK / 1000.0) * 5  # 600 s → 5 Gruppen
    rest = estimate_align_eta_s(600.0, elapsed_s=100.0)
    assert rest is not None and rest[0] == round(600.0 * f) - 100


def test_align_eta_none_ohne_dauer():
    assert estimate_align_eta_s(None) is None
    assert estimate_align_eta_s(0.0) is None
