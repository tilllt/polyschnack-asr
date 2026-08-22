"""rtf_learner.py — selbstlernende ETA-Faktoren je (Phase, Variante) (Change 085).

Lernt aus Betriebs-Stichproben pro Schlüssel (z. B. ``asr:ps-pk-onnx``,
``diar:pyannote``, ``enhance:light``, ``align``) einen Geschwindigkeits-
Faktor (Skalar, meist ``ms/1000 / Bezugsgröße``). Pure Logik ohne DB — die
Persistenz (rtf_estimates-Tabelle) macht der Aufrufer via ``to_state``/
``from_state``.

Regeln (Anti-Fake, Change 082 + User-Vorgabe 22.08.):
- n >= N_MIN (10): Trimmed-Mean (10 % getrimmt) + Perzentil-Spanne (p10/p90)
- n < N_MIN: Fallback-Wert mit breiter Spanne (±50 %); kein Fallback -> None
- unbekannter Schlüssel ohne Fallback -> None (nie raten)
- Digest-Wechsel (Backend-Update) invalidiert die gelernte Historie
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, asdict
from typing import Deque, Dict, List, Optional

N_MIN = 10          # Stichproben, ab denen gelernt wird
MAX_SAMPLES = 50    # Historie je Schlüssel (rollend)
TRIM = 0.10         # getrimmter Anteil je Seite (Trimmed-Mean)
FALLBACK_SPREAD = 0.50  # breite Spanne bei < N_MIN


@dataclass(frozen=True)
class Estimate:
    """Geschätzter Faktor + ehrliche Spanne + Stichprobengröße."""
    factor: float
    low: float
    high: float
    n: int


def _trimmed_mean(vals: List[float], trim: float = TRIM) -> float:
    """Mittelwert nach beidseitigem Trimmen; trim=0 bei zu kleinen Stichproben."""
    if not vals:
        return 0.0
    s = sorted(vals)
    if len(s) >= 5 and trim > 0:
        k = max(1, int(round(trim * len(s))))
        s = s[k:-k] if len(s) > 2 * k else s
    return sum(s) / len(s)


def _percentile(vals: List[float], q: float) -> float:
    """Lineare Perzentil-Interpolation (q in [0, 1])."""
    if not vals:
        return 0.0
    s = sorted(vals)
    if len(s) == 1:
        return s[0]
    pos = q * (len(s) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    frac = pos - lo
    return s[lo] * (1 - frac) + s[hi] * frac


class RtfLearner:
    """Rollender, deterministischer Faktor-Schätzer je Schlüssel."""

    def __init__(self, *, n_min: int = N_MIN, max_samples: int = MAX_SAMPLES):
        self.n_min = n_min
        self.max_samples = max_samples
        self._history: Dict[str, Deque[float]] = {}
        self._digest: Dict[str, Optional[str]] = {}

    # ── Eingabe ────────────────────────────────────────────────────────
    def ingest(self, phase_key: str, factor: float, *, digest: Optional[str] = None) -> None:
        """Neue Stichprobe; Digest-Wechsel leert die Historie (Invalidierung)."""
        if digest is not None and self._digest.get(phase_key) not in (None, digest):
            self._history[phase_key] = deque(maxlen=self.max_samples)
        self._digest[phase_key] = digest
        h = self._history.setdefault(phase_key, deque(maxlen=self.max_samples))
        h.append(float(factor))

    # ── Schätzung ──────────────────────────────────────────────────────
    def estimate(self, phase_key: str, fallback: Optional[float] = None) -> Optional[Estimate]:
        """Gelernte Schätzung; Fallback bei < n_min; None ohne alles (Anti-Fake)."""
        vals = list(self._history.get(phase_key, ()))
        if len(vals) >= self.n_min:
            factor = _trimmed_mean(vals)
            low = _percentile(vals, 0.10)
            high = _percentile(vals, 0.90)
            return Estimate(round(factor, 6), round(low, 6), round(high, 6), len(vals))
        if fallback is None:
            return None
        return Estimate(
            round(fallback, 6),
            round(fallback * (1 - FALLBACK_SPREAD), 6),
            round(fallback * (1 + FALLBACK_SPREAD), 6),
            len(vals),
        )

    def sample_count(self, phase_key: str) -> int:
        return len(self._history.get(phase_key, ()))

    # ── Verwaltung ─────────────────────────────────────────────────────
    def reset(self, phase_key: Optional[str] = None) -> None:
        if phase_key is None:
            self._history.clear()
            self._digest.clear()
        else:
            self._history.pop(phase_key, None)
            self._digest.pop(phase_key, None)

    # ── Persistenz (DB-Schicht ruft das auf) ───────────────────────────
    def to_state(self) -> dict:
        return {
            "history": {k: list(v) for k, v in self._history.items()},
            "digest": {k: v for k, v in self._digest.items() if v is not None},
        }

    def from_state(self, state: Optional[dict]) -> None:
        if not state:
            return
        for k, vals in (state.get("history") or {}).items():
            self._history[k] = deque(vals, maxlen=self.max_samples)
        for k, v in (state.get("digest") or {}).items():
            self._digest[k] = v

    def keys(self) -> List[str]:
        return sorted(set(self._history) | set(self._digest))
