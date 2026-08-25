"""ETA-Schätzung aus Audio-Dauer × RTF (Change 082) + rtf_learner (Change 085).

RTF-Werte: Benchmark 22.08. (Change-080-Testset, RTX 3090/3060).
Anti-Fake-Regel: KEINE ETA ohne bekannte Rate — None statt geratenem Wert.

Change 085 (Phase 0): Optional kann ein :class:`RtfLearner` übergeben werden.
Dann gilt je aktiver Phase: gelernte Schätzung > Fallback (±50 %) > None.
Ist irgendeine aktive Phase nicht schätzbar → None (Gesamtschätzung nur,
wenn alle aktiven Phasen schätzbar sind). ``noise_reduce`` ist keine
messbare Phase (läuft im ASR-Call) und bleibt ein konstanter Zuschlag.
``align`` läuft post-done im Hintergrund-Worker: eigener Faktor in
ms/Gruppe (skaliert mit Gruppenanzahl, nicht Audio-Dauer).
"""
from __future__ import annotations

from datetime import datetime, timezone
from math import ceil
from typing import Optional

from .rtf_learner import FALLBACK_SPREAD

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

#: Diarization-RTF je Methode — Change 127 (2026-08-25) an gemessenen
#: Läufen kalibriert (scripts/diarize_local.sh, 220-s-Ausschnitt, CPU-CLI:
#: pyannote 143 s / foxnose 144 s → je 0.65). Prod-Server/CUDA ohne
#: Modell-Load-Overhead ist effektiv schneller — der ETA-Learner lernt
#: die echten Prod-Zeiten ab n ≥ 10 Stichproben; die Fallback-Spanne
#: (±50 %) deckt die Unsicherheit des Kaltstarts ab.
DIAR_RTF: dict[str, float] = {
    "energy": 0.02,
    "foxnose": 0.65,
    "pyannote": 0.65,
}

#: Pauschale Overheads (Anteil an der Audio-Dauer), nur wenn aktiviert.
VAD_OVERHEAD = 0.03
ENHANCE_OVERHEAD = 0.10
NOISE_REDUCE_OVERHEAD = 0.05
# Change 106: Source Separation (crispr-sep) — GPU RTF ~0.1-0.2, CPU deutlich
# höher; konservativer Zuschlag, Messwerte folgen mit dem Live-Betrieb.
SEP_OVERHEAD = 0.25
#: LLM-Post-Processing (Punctuation/Truecase) — konservativ, wird gelernt.
PUNCT_OVERHEAD = 0.04

#: Align-Fallback: ms pro Align-Gruppe (Change 078: Gruppen ≤ 120 s).
#: Muss mit service.MAX_ALIGN_GROUP_S Schritt halten (Duplikat vermeidet
#: einen Zyklus service ↔ eta).
ALIGN_GROUP_S = 120.0
ALIGN_MS_PER_GROUP_FALLBACK = 250.0

#: Ehrliche Spanne um den Schätzwert (±30 %, mind. 5 s) — nur der
#: Fallback-Pfad ohne Learner; mit Learner kommen die echten Perzentile.
SPREAD = 0.30
MIN_SPREAD_S = 5.0


def elapsed_since(started_at: Optional[datetime]) -> float:
    """Sekunden seit *started_at* (naiv = UTC tolerant); 0 bei None/Zukunft."""
    if started_at is None:
        return 0.0
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - started_at).total_seconds())


def _estimate_eta_s(
    duration_s: Optional[float],
    backend: Optional[str],
    *,
    enable_vad: bool = False,
    enable_diarize: bool = False,
    diarize_method: Optional[str] = None,
    enable_noise_reduce: bool = False,
    enable_enhance: str = "off",
    separate_backend: str = "none",
    enable_punctuation: bool = False,
    elapsed_s: float = 0.0,
    learner=None,
    include_align: bool = False,
) -> Optional[tuple[float, float, float]]:
    """Kern: liefert (factor, low, high) als Anteile der Audio-Dauer | None."""
    if not duration_s or duration_s <= 0:
        return None

    asr_rtf = ASR_RTF.get(backend or "")
    if asr_rtf is None:
        return None

    # Messbare Phasen: (Key, statischer Fallback). Nicht messbar:
    # noise_reduce (läuft im ASR-Call) — konstanter Zuschlag unten.
    phases: list[tuple[str, float]] = [("asr:" + (backend or ""), asr_rtf)]
    if enable_diarize:
        method = diarize_method or "pyannote"
        phases.append(("diar:" + method, DIAR_RTF.get(method, 0.4)))
    if enable_vad:
        phases.append(("vad", VAD_OVERHEAD))
    if enable_enhance and enable_enhance != "off":
        phases.append(("enhance:" + enable_enhance, ENHANCE_OVERHEAD))
    if separate_backend and separate_backend != "none":
        phases.append(("separate:" + separate_backend, SEP_OVERHEAD))
    if enable_punctuation:
        phases.append(("punc_truecase", PUNCT_OVERHEAD))
    if include_align:
        phases.append(("align", ALIGN_MS_PER_GROUP_FALLBACK / 1000.0 * _align_groups(duration_s)))

    if learner is None:
        # Bisheriges Verhalten (Change 082): statische Faktoren, ±30 %-Spanne.
        factor = asr_rtf
        if enable_diarize:
            factor += DIAR_RTF.get(diarize_method or "pyannote", 0.4)
        if enable_vad:
            factor += VAD_OVERHEAD
        if enable_noise_reduce:
            factor += NOISE_REDUCE_OVERHEAD
        if enable_enhance and enable_enhance != "off":
            factor += ENHANCE_OVERHEAD
        if separate_backend and separate_backend != "none":
            factor += SEP_OVERHEAD
        if enable_punctuation:
            factor += PUNCT_OVERHEAD
        if include_align:
            factor += ALIGN_MS_PER_GROUP_FALLBACK / 1000.0 * _align_groups(duration_s)
        rest = max(0.0, duration_s * factor - max(0.0, elapsed_s))
        if rest < 1.0:
            return None
        return rest, rest * (1.0 - SPREAD), rest * (1.0 + SPREAD)

    # Learner-Pfad (Change 085): je Phase gelernt > Fallback > None.
    factor = low = high = 0.0
    for key, fallback in phases:
        est = learner.estimate(key, fallback=fallback)
        if est is None:
            return None  # aktive Phase nicht schätzbar → keine Gesamt-ETA
        factor += est.factor
        low += est.low
        high += est.high
    if enable_noise_reduce:
        # Konstanter Zuschlag (nicht messbar) auf alle drei Werte.
        factor += NOISE_REDUCE_OVERHEAD
        low += NOISE_REDUCE_OVERHEAD
        high += NOISE_REDUCE_OVERHEAD
    if separate_backend and separate_backend != "none":
        factor += SEP_OVERHEAD
        low += SEP_OVERHEAD
        high += SEP_OVERHEAD

    rest = max(0.0, duration_s * factor - max(0.0, elapsed_s))
    if rest < 1.0:
        return None
    # Relative Faktor-Spanne auf den Rest skalieren (ehrliche Perzentile).
    rel_low = (low / factor) if factor > 0 else (1.0 - SPREAD)
    rel_high = (high / factor) if factor > 0 else (1.0 + SPREAD)
    rest_low = max(MIN_SPREAD_S, rest * rel_low)
    rest_high = max(rest, rest * rel_high)
    return rest, rest_low, rest_high


def _align_groups(duration_s: float) -> int:
    """Erwartete Align-Gruppenzahl: ceil(Dauer / 120 s-Gruppe)."""
    return max(1, ceil(float(duration_s) / ALIGN_GROUP_S))


def _estimate_phase_eta_s(
    duration_s: Optional[float],
    key: str,
    fallback: Optional[float],
    elapsed_s: float,
    learner=None,
) -> Optional[tuple[int, int, int]]:
    """Change 127: gemeinsamer Kern für Background-Phasen-ETAs (Diar/Align).

    Erwartete Gesamtdauer = Dauer × Faktor(key) — gelernt (Learner) oder
    *fallback* (±50 % Spanne, konsistent zum RtfLearner). None bei
    fehlender Dauer oder unbekannter Rate (nie raten).
    """
    if not duration_s or duration_s <= 0:
        return None
    if learner is None:
        if fallback is None or fallback <= 0:
            return None
        factor = low = high = float(fallback)
        low *= 1.0 - FALLBACK_SPREAD
        high *= 1.0 + FALLBACK_SPREAD
    else:
        est = learner.estimate(key, fallback=fallback)
        if est is None:
            return None
        factor, low, high = est.factor, est.low, est.high
    rest = max(0.0, duration_s * factor - max(0.0, elapsed_s))
    if rest < 1.0:
        return None
    rel_low = (low / factor) if factor > 0 else (1.0 - FALLBACK_SPREAD)
    rel_high = (high / factor) if factor > 0 else (1.0 + FALLBACK_SPREAD)
    rest_low = max(MIN_SPREAD_S, rest * rel_low)
    rest_high = max(rest, rest * rel_high)
    return int(rest), int(rest_low), int(rest_high)


def estimate_diar_eta_s(
    duration_s: Optional[float],
    diarize_method: Optional[str] = None,
    *,
    elapsed_s: float = 0.0,
    learner=None,
) -> Optional[tuple[int, int, int]]:
    """Change 127: Rest-ETA für eine laufende Rediarize (nur Diar-Phase).

    Dauer × RTF(diar:<methode>) — gelernt (getrennt pro Methode) oder
    DIAR_RTF-Fallback.
    """
    method = diarize_method or "pyannote"
    return _estimate_phase_eta_s(
        duration_s,
        "diar:" + method,
        DIAR_RTF.get(method),
        elapsed_s,
        learner,
    )


def estimate_align_eta_s(
    duration_s: Optional[float],
    *,
    elapsed_s: float = 0.0,
    learner=None,
) -> Optional[tuple[int, int, int]]:
    """Change 127: Rest-ETA für ein laufendes Background-Alignment.

    Dauer × Faktor(align); Faktor = ms/Gruppe × Gruppenanzahl
    (Fallback ALIGN_MS_PER_GROUP_FALLBACK), konsistent zum
    include_align-Pfad der Transcribe-ETA.
    """
    return _estimate_phase_eta_s(
        duration_s,
        "align",
        ALIGN_MS_PER_GROUP_FALLBACK / 1000.0 * _align_groups(duration_s or 0.0),
        elapsed_s,
        learner,
    )


def estimate_eta_s(
    duration_s: Optional[float],
    backend: Optional[str],
    *,
    enable_vad: bool = False,
    enable_diarize: bool = False,
    diarize_method: Optional[str] = None,
    enable_noise_reduce: bool = False,
    enable_enhance: str = "off",
    separate_backend: str = "none",
    enable_punctuation: bool = False,
    elapsed_s: float = 0.0,
    learner=None,
    include_align: bool = False,
) -> Optional[tuple[int, int, int]]:
    """Geschätzte Restdauer → (rest_s, rest_low_s, rest_high_s) | None.

    None, wenn: keine Dauer, unbekanntes Backend (keine Rate), eine aktive
    Phase nicht schätzbar (Learner-Pfad) oder nichts mehr übrig (< 1 s Rest).
    """
    core = _estimate_eta_s(
        duration_s, backend,
        enable_vad=enable_vad,
        enable_diarize=enable_diarize,
        diarize_method=diarize_method,
        enable_noise_reduce=enable_noise_reduce,
        enable_enhance=enable_enhance,
        separate_backend=separate_backend,
        enable_punctuation=enable_punctuation,
        elapsed_s=elapsed_s,
        learner=learner,
        include_align=include_align,
    )
    if core is None:
        return None
    rest, rest_low, rest_high = core
    return int(rest), int(rest_low), int(rest_high)
