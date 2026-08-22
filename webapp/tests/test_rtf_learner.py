"""Tests für rtf_learner.py (Change 085, Phase 0)."""
import pytest

from app.rtf_learner import N_MIN, RtfLearner, Estimate, _percentile, _trimmed_mean


def seed(learner: RtfLearner, key: str, vals, digest=None):
    for v in vals:
        learner.ingest(key, v, digest=digest)
    return learner


# ── Pure Helfer ──────────────────────────────────────────────────────────

def test_trimmed_mean_removes_outliers():
    vals = [1.0] * 9 + [100.0]  # 10 Werte, ein Ausreißer
    m = _trimmed_mean(vals, trim=0.10)
    assert m == pytest.approx(1.0)  # getrimmt: Ausreißer fliegt raus


def test_trimmed_mean_small_sample_untouched():
    assert _trimmed_mean([0.5, 1.5]) == pytest.approx(1.0)
    assert _trimmed_mean([]) == 0.0


def test_percentile_interpolation():
    vals = [10.0, 20.0, 30.0, 40.0]
    assert _percentile(vals, 0.0) == 10.0
    assert _percentile(vals, 1.0) == 40.0
    assert _percentile(vals, 0.5) == pytest.approx(25.0)
    assert _percentile([7.0], 0.9) == 7.0
    assert _percentile([], 0.5) == 0.0


# ── Schätzlogik ──────────────────────────────────────────────────────────

def test_unknown_key_without_fallback_is_none():
    l = RtfLearner()
    assert l.estimate("asr:gibtsnicht") is None


def test_unknown_key_with_fallback_uses_fallback_and_wide_spread():
    l = RtfLearner()
    e = l.estimate("asr:neu", fallback=0.1)
    assert e is not None
    assert e.n == 0
    assert e.factor == pytest.approx(0.1)
    assert e.low == pytest.approx(0.05)   # ±50 %
    assert e.high == pytest.approx(0.15)


def test_learns_after_n_min_samples():
    l = RtfLearner()
    vals = [0.070, 0.072, 0.069, 0.071, 0.070, 0.073, 0.068, 0.071, 0.070, 0.072]
    seed(l, "asr:ps-pk-onnx", vals)
    e = l.estimate("asr:ps-pk-onnx")
    assert e is not None
    assert e.n == 10
    # Trimmed-Mean: je 1 Randwert entfernt → Mittelwert der mittleren 8
    trimmed = sorted(vals)[1:-1]
    assert e.factor == pytest.approx(sum(trimmed) / len(trimmed))
    assert e.low <= e.factor <= e.high


def test_outlier_does_not_dominate_learned_value():
    l = RtfLearner()
    seed(l, "diar:pyannote", [0.40, 0.41, 0.39, 0.40, 0.42, 0.38, 0.41, 0.40, 0.39, 0.41, 9.99])
    e = l.estimate("diar:pyannote")
    assert e is not None
    assert e.factor < 1.0  # Ausreißer 9.99 fliegt durchs Trimmen raus


def test_fallback_only_until_n_min():
    l = RtfLearner()
    for i in range(N := N_MIN - 1):
        l.ingest("enhance:light", 0.10)
    e = l.estimate("enhance:light", fallback=0.10)
    assert e.n == N                    # noch Fallback-Zweig
    assert e.low == pytest.approx(0.05)
    l.ingest("enhance:light", 0.10)
    e2 = l.estimate("enhance:light", fallback=0.10)
    assert e2.n == N_MIN               # jetzt gelernt
    assert e2.low > 0.05               # enge Spanne aus den Daten


# ── Invalidierung / Verwaltung ───────────────────────────────────────────

def test_digest_change_resets_history():
    l = RtfLearner()
    seed(l, "asr:pk-cpp", [0.05] * 20, digest="img-a")
    assert l.sample_count("asr:pk-cpp") == 20
    seed(l, "asr:pk-cpp", [0.10] * 20, digest="img-b")  # Backend-Update
    assert l.sample_count("asr:pk-cpp") == 20           # Historie geleert, nur neue
    e = l.estimate("asr:pk-cpp")
    assert e is not None and e.factor == pytest.approx(0.10)


def test_digest_same_keeps_history():
    l = RtfLearner()
    seed(l, "asr:x", [0.05] * 20, digest="img-a")
    seed(l, "asr:x", [0.06] * 10, digest="img-a")
    assert l.sample_count("asr:x") == 30


def test_reset_single_and_all():
    l = RtfLearner()
    seed(l, "a", [1.0] * 20)
    seed(l, "b", [2.0] * 20)
    l.reset("a")
    assert l.sample_count("a") == 0 and l.sample_count("b") == 20
    l.reset()
    assert l.keys() == []


def test_rolling_history_capped():
    l = RtfLearner(max_samples=5)
    seed(l, "k", list(range(10)))
    assert l.sample_count("k") == 5
    e = l.estimate("k", fallback=1.0)  # n=5 < N_MIN → Fallback-Zweig
    assert e is not None and e.n == 5


def test_determinism():
    l1, l2 = RtfLearner(), RtfLearner()
    vals = [0.1, 0.2, 0.15, 0.12, 0.13, 0.11, 0.14, 0.12, 0.13, 0.115, 0.16]
    seed(l1, "k", vals)
    seed(l2, "k", vals)
    assert l1.estimate("k") == l2.estimate("k")


# ── Persistenz ───────────────────────────────────────────────────────────

def test_state_roundtrip():
    l = RtfLearner()
    seed(l, "asr:onnx", [0.07, 0.08, 0.075], digest="d1")
    state = l.to_state()
    l2 = RtfLearner()
    l2.from_state(state)
    assert l2.sample_count("asr:onnx") == 3
    assert l2.estimate("asr:onnx", fallback=0.07) == l.estimate("asr:onnx", fallback=0.07)
    assert l2.keys() == ["asr:onnx"]


def test_from_state_none_ok():
    RtfLearner().from_state(None)
    RtfLearner().from_state({})
