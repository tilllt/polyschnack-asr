"""HTTP-Client für den Diarization-Service (diar:5096, CrispASR — Option B).

Die pyannote-Pipeline wurde durch den CrispASR-Server ersetzt:
``POST /v1/audio/transcriptions`` mit ``diarize=true`` und
``response_format=diarized_json`` liefert Speaker-Segmente direkt —
kein pyannote, kein torch in der Webapp (schlankes Image).

Fehlerklassen bleiben erhalten (:class:`DiarizationError` mit
maschinenlesbarem ``code``), neu hinzugekommen: ``service-unreachable``.
CrispASR normalisiert Speaker auf A, B, C … — wird hier auf das
SPEAKER_XX-Format unserer UI/Exporte gemappt.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

from .config import settings

log = logging.getLogger(__name__)


class DiarizationError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(f"diarization/{code}: {message}")
        self.code = code
        self.message = message


def _detect_device() -> str:
    """Die Webapp hat kein torch mehr — das Gerät meldet der diar-Service."""
    return "remote"


def _normalise_speaker(label: str) -> str:
    """CrispASR liefert A, B, C … — auf SPEAKER_00/01/… normalisieren.

    Bereits normalisierte Labels (SPEAKER_xx) und leere Werte bleiben
    stabil; unbekannte Zeichen fallen auf SPEAKER_00 zurück.
    """
    if not label:
        return "SPEAKER_00"
    if label.startswith("SPEAKER_"):
        return label
    code = ord(label[0].upper())
    if ord("A") <= code <= ord("Z"):
        return f"SPEAKER_{code - ord('A'):02d}"
    return "SPEAKER_00"


def diarize(
    audio_path: str,
    num_speakers: Optional[int] = None,
    min_duration_off: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Ruft den CrispASR-diar-Service und liefert {start, end, speaker}-Segmente.

    Optionales Tuning (UI: „Sprecheranzahl"): ``num_speakers`` wird als
    ``diarize_max_speakers`` übertragen. ``min_duration_off`` hat in
    CrispASR keine direkte Entsprechung und wird bewusst nicht übertragen.

    Raises :class:`DiarizationError` (service-unreachable / Proxy-Fehler) —
    nie eine stille leere Liste bei Service-Problemen.
    """
    url = f"{settings.DIAR_URL.rstrip('/')}/v1/audio/transcriptions"
    with open(audio_path, "rb") as f:
        audio_bytes = f.read()

    data: Dict[str, Any] = {
        "response_format": "diarized_json",
        "diarize": "true",
        "diarize_method": settings.DIARIZE_METHOD,
    }
    if num_speakers is not None:
        data["diarize_max_speakers"] = str(num_speakers)

    try:
        with httpx.Client(timeout=1800) as client:
            resp = client.post(
                url,
                files={"file": (os.path.basename(audio_path), audio_bytes, "audio/wav")},
                data=data,
            )
    except httpx.HTTPError as exc:
        log.warning("diarize: diar-Service nicht erreichbar (%s)", exc)
        raise DiarizationError(
            "service-unreachable",
            "Der Diarization-Service ist nicht erreichbar. Bitte den "
            "Administrator informieren (Container 'diar' prüfen).",
        ) from exc

    if resp.status_code != 200:
        detail = {}
        try:
            detail = resp.json().get("detail", {}) or {}
        except Exception:
            pass
        code = detail.get("code") if isinstance(detail, dict) else None
        message = detail.get("message") if isinstance(detail, dict) else None
        if code and message:
            raise DiarizationError(code, message)
        raise DiarizationError(
            "service-error",
            f"Diar-Service antwortete mit HTTP {resp.status_code}.",
        )

    segments: List[Dict[str, Any]] = []
    for seg in resp.json().get("segments") or []:
        segments.append({
            "start": float(seg["start"]),
            "end": float(seg["end"]),
            "speaker": _normalise_speaker(str(seg.get("speaker", "A"))),
        })
    return segments
