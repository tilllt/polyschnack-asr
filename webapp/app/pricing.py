"""pricing.py — Kostenschicht für virtuelle Credits (Change 086).

Reine Funktionen (keine DB): aus gemessenen Phasenzeiten (Change 085)
und Kostensätzen wird der Preis eines Jobs in Cent berechnet.

Schichten-Trennung (Design 085): der rtf_learner lernt ZEIT-Faktoren,
pricing.py liefert PREISE. Sätze kommen aus ``backends.yaml``
(``cost_per_minute_eur``) + Modul-Konstanten für LLM/Align.

Regeln:
- Nie negativ; bei messbarem Aufwand mindestens 1 Cent.
- Kostensätze 0.0 → 0 Cent (lokale Box / noch nicht bepreiste Backends).
"""
from __future__ import annotations

import math
from typing import Dict, Optional

#: LLM-Post-Processing (Punctuation/Enhance/Template) — EUR pro Minute.
LLM_COST_PER_MINUTE_EUR = 0.02
#: Forced-Alignment (läuft lokal auf der Box) — EUR pro Minute
#: (Strom + Abschreibung, konservativ).
ALIGN_COST_PER_MINUTE_EUR = 0.002


def _cents_from_minutes(minutes: float, eur_per_minute: float) -> int:
    """Cent aus Minuten × Satz — gerundet auf ganze Cent (nie negativ)."""
    if not minutes or minutes <= 0 or not eur_per_minute or eur_per_minute <= 0:
        return 0
    return max(1, math.ceil(minutes * eur_per_minute * 100.0))


def calculate_job_cost(
    phase_times_ms: Optional[Dict[str, float]],
    duration_s: Optional[float],
    backend: Optional[str],
    *,
    backend_cost_per_minute_eur: Optional[float] = None,
    llm_seconds: float = 0.0,
    align_ms: float = 0.0,
    llm_cost_per_minute_eur: float = LLM_COST_PER_MINUTE_EUR,
    align_cost_per_minute_eur: float = ALIGN_COST_PER_MINUTE_EUR,
) -> int:
    """Endabrechnung eines Jobs in Cent (0 = nichts bepreist/gemessen).

    GPU-Phasen (asr/diar/enhance/vad) laufen mit dem Backend-Satz; die
    LLM-Phase mit dem LLM-Satz; Align separat (lokale Box). ``duration_s``
    wird nur als Fallback für die ASR-Phase genutzt, wenn keine
    Phasenmessung vorliegt (Altdaten): duration × Satz/60.
    """
    phases = phase_times_ms or {}
    if not phases and not duration_s:
        return 0

    backend_rate = backend_cost_per_minute_eur
    if backend_rate is None:
        # Ohne expliziten Satz: 0 (backends.yaml liefert die Sätze; die
        # Webapp reicht sie von dort durch — nie hier hart kodieren).
        backend_rate = 0.0

    total = 0.0  # Cent als Float — einmaliges Ceil am Ende (kein Überbuchen)
    if phases:
        for key, ms in phases.items():
            minutes = (float(ms) / 1000.0) / 60.0
            if key.startswith("asr:") or key.startswith("diar:") \
                    or key.startswith("enhance:") or key == "vad":
                total += minutes * backend_rate * 100.0
            elif key == "punc_truecase":
                total += minutes * llm_cost_per_minute_eur * 100.0
            # noise_reduce läuft im ASR-Call → Backend-Satz (kein eigener Key)
            # align läuft im Hintergrund-Worker → separat (align_ms)
    elif duration_s and duration_s > 0:
        # Altdaten ohne Phasenmessung: pauschal ASR mit Backend-Satz.
        total += duration_s / 60.0 * backend_rate * 100.0

    if llm_seconds and llm_seconds > 0:
        total += llm_seconds / 60.0 * llm_cost_per_minute_eur * 100.0
    if align_ms and align_ms > 0:
        total += (float(align_ms) / 1000.0) / 60.0 * align_cost_per_minute_eur * 100.0
    if total <= 0:
        return 0
    return max(1, math.ceil(total))


def backend_cost_per_minute(backend: Optional[str]) -> float:
    """Kostensatz aus backends.yaml (Single Source of Truth); 0.0 bei unbekannt."""
    try:
        from .service_registry import get_service
        svc = get_service(backend or "")
        if svc is not None:
            return float(svc.get("cost_per_minute_eur") or 0.0)
    except Exception:
        pass
    return 0.0


def reserve_cents(
    duration_s: Optional[float],
    estimated_factor: float,
    backend_cost_per_minute_eur: float,
) -> int:
    """Vorschuss in Cent beim Job-Start (Reserve-System, Change 086).

    Obergrenze statt Mittelwert: ``estimated_factor`` sollte die p90-Spanne
    der Schätzung sein (Fallback ±50 % über dem Fallback-Faktor) — die
    Reserve deckt den schlechteren Fall ab, das Delta wird bei Abschluss
    ausgeglichen.
    """
    if not duration_s or duration_s <= 0 or not estimated_factor \
            or estimated_factor <= 0 or not backend_cost_per_minute_eur:
        return 0
    minutes = duration_s * estimated_factor / 60.0
    return max(0, math.ceil(minutes * backend_cost_per_minute_eur * 100.0))


# --- Zugangskontrolle für kostenpflichtige Pfade (Change 080/081, B9/A12/A13) ---
# Diese drei Funktionen lebten ursprünglich in pricing.py und wurden von
# Change 086 bewusst übernommen (Signatur-Kompatibilität): anonymer Zugang
# darf weder kostenpflichtige Backends noch LLM-Verarbeitung nutzen.

def is_paid_backend(name: str) -> bool:
    """True, wenn das Backend einen Kostensatz > 0 hat (backends.yaml)."""
    return backend_cost_per_minute(name) > 0


def paid_route_for(user) -> bool:
    """True, wenn dieser User kostenpflichtige Verarbeitung nutzen darf.

    ``user`` ist ein User-Objekt; None (kein Login) oder kind='anonymous'
    → False.
    """
    if user is None:
        return False
    return getattr(user, "kind", "oidc") != "anonymous"


def ensure_free_only(user, backend: Optional[str] = None,
                     want_llm: bool = False, llm_mode: bool = False) -> None:
    """Enforcer für alle paid-Pfade: Backend-Wahl (B9), LLM-Enhance (A13),
    LLM-Punctuation (A12). Wirft 403, wenn ein anonymer User einen
    kostenpflichtigen Pfad wählt."""
    if paid_route_for(user):
        return
    if (backend and is_paid_backend(backend)) or want_llm or llm_mode:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=403,
            detail="kostenpflichtige Endpunkte sind für anonyme Nutzung gesperrt",
        )
