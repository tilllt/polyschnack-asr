"""ETA-Schätzung aus Audio-Dauer × RTF (Change 082).

RTF-Werte: Benchmark 22.08. (Change-080-Testset, RTX 3090/3060).
Anti-Fake-Regel: KEINE ETA ohne bekannte Rate — None statt geratenem Wert.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

#: Gemessene ASR-RTF (Real-Time-Factor) je Backend (Benchmark 22.08.).
ASR_RTF: dict[str, float] = {
    "ps-pk-onnx": 0.071,
    "crispr-pk-cpp": 0.056,
    "crispr-qwen3": 0.081,
    "crispr-moonshine-de": 0.073,
    "crispr-canary": 0.067,
    "crispr-whisper-large-v3": 0.199,
    # crispr-whisper-turbo: nie gemessen (vast-Pull-Stall) → bewusst KEIN
    # Eintrag: unbekanntes Backend ⇒ keine ETA (Anti-Fake-Regel).
}

#: Diarization-RTF je Methode — konservativ geschätzt (Phase 2 kalibriert).
DIAR_RTF: dict[str, float] = {
    "energy": 0.02,
    "foxnose": 0.2,
    "pyannote": 0.4,
}

#: Pauschale Overheads (Anteil an der Audio-Dauer), nur wenn aktiviert.
VAD_OVERHEAD = 0.03
ENHANCE_OVERHEAD = 0.10
NOISE_REDUCE_OVERHEAD = 0.05

#: Ehrliche Spanne um den Schätzwert (±30 %, mind. 5 s).
SPREAD = 0.30
MIN_SPREAD_S = 5.0


def elapsed_since(started_at: Optional[datetime]) -> float:
    """Sekunden seit *started_at* (naiv = UTC tolerant); 0 bei None/Zukunft."""
    if started_at is None:
        return 0.0
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - started_at).total_seconds())


def estimate_eta_s(
    duration_s: Optional[float],
    backend: Optional[str],
    *,
    enable_vad: bool = False,
    enable_diarize: bool = False,
    diarize_method: Optional[str] = None,
    enable_noise_reduce: bool = False,
    enable_enhance: str = "off",
    elapsed_s: float = 0.0,
) -> Optional[tuple[int, int, int]]:
    """Geschätzte Restdauer → (rest_s, rest_low_s, rest_high_s) | None.

    None, wenn: keine Dauer, unbekanntes Backend (keine Rate) oder nichts
    mehr übrig (< 1 s Rest).
    """
    if not duration_s or duration_s <= 0:
        return None
    asr_rtf = ASR_RTF.get(backend or "")
    if asr_rtf is None:
        return None
    factor = asr_rtf
    if enable_diarize:
        factor += DIAR_RTF.get(diarize_method or "pyannote", 0.4)
    if enable_vad:
        factor += VAD_OVERHEAD
    if enable_noise_reduce:
        factor += NOISE_REDUCE_OVERHEAD
    if enable_enhance and enable_enhance != "off":
        factor += ENHANCE_OVERHEAD
    rest = max(0.0, duration_s * factor - max(0.0, elapsed_s))
    if rest < 1.0:
        return None
    low = max(MIN_SPREAD_S, rest * (1.0 - SPREAD))
    high = max(rest, rest * (1.0 + SPREAD))
    return int(rest), int(low), int(high)
