"""Minimal pyannote.audio diarization wrapper.

Requires HF_TOKEN env var (accept terms at
https://huggingface.co/pyannote/speaker-diarization-3.1 and
https://huggingface.co/pyannote/segmentation-3.0).

Ladefehler werden NICHT mehr still verschluckt: statt einer leeren Liste
wirft :func:`diarize` eine :class:`DiarizationError` mit präziser Ursache
(no-token, gated, unauthorized, not-found, …), damit der Aufrufer die
Aufnahme als fehlgeschlagen markieren und den Admin-Hinweis ausgeben kann.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

_pipeline = None


class DiarizationError(RuntimeError):
    """Diarization nicht verfügbar — mit maschinenlesbarem ``code`` und
    menschenlesbarer ``message`` (inkl. Admin-Hinweis)."""

    def __init__(self, code: str, message: str):
        super().__init__(f"diarization/{code}: {message}")
        self.code = code
        self.message = message


def _classify_load_error(exc: Exception) -> tuple[str, str]:
    """Mappt eine from_pretrained-Exception auf (code, message).

    codes: no-token | unauthorized | gated | not-found | load-failed
    """
    # huggingface_hub HTTPStatusError trägt .response.status_code
    status = getattr(getattr(exc, "response", None), "status_code", None)
    text = str(exc).lower()
    admin_hint = (
        " Bitte den Administrator informieren, damit er die "
        "Nutzungsbedingungen auf HuggingFace akzeptiert."
    )
    if status == 401 or "401" in text or "invalid token" in text:
        return "unauthorized", (
            "Das HuggingFace-Token ist ungültig oder abgelaufen "
            "(HTTP 401). Bitte den Administrator informieren."
        )
    if status == 403 or "gated" in text or "restricted" in text \
            or "access" in text or "403" in text:
        return "gated", (
            "Das Diarization-Modell ist auf HuggingFace lizenzgeschützt "
            "(gated) und wurde für dieses Token noch nicht freigeschaltet."
            + admin_hint
        )
    if status == 404 or "404" in text or "not found" in text:
        return "not-found", (
            "Das Diarization-Modell existiert auf HuggingFace nicht (HTTP "
            "404) — Modell-ID in der Pipeline-Konfiguration prüfen."
        )
    return "load-failed", f"Diarization-Modell konnte nicht geladen werden: {exc}"


def _load_pipeline():
    global _pipeline
    if _pipeline is not None:
        return _pipeline
    token = os.getenv("HF_TOKEN")
    if not token:
        raise DiarizationError(
            "no-token",
            "HF_TOKEN ist nicht gesetzt — Diarization ist ohne Token nicht "
            "nutzbar. Bitte den Administrator informieren.",
        )
    try:
        from pyannote.audio import Pipeline

        _pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            token=token,
        )
    except DiarizationError:
        raise
    except Exception as exc:
        code, message = _classify_load_error(exc)
        log.exception("diarize: pipeline load failed on %s: %s", exc, exc)
        raise DiarizationError(code, message) from exc
    log.info("pyannote diarization pipeline loaded")
    return _pipeline


def _extract_segments(result) -> List[Dict[str, Any]]:
    """Extrahiert {start, end, speaker}-Segmente aus dem Pipeline-Ergebnis.

    Abwärtskompatibel:
    - pyannote.audio 4.x: Ergebnis ist ein ``DiarizeOutput``-Dataclass mit
      ``speaker_diarization`` (Annotation) bzw. ``serialize()``.
    - pyannote.audio 3.x: Ergebnis ist direkt eine ``Annotation`` mit
      ``itertracks(yield_label=True)``.
    """
    # Fall 1: pyannote 4.x DiarizeOutput (hat serialize())
    serializer = getattr(result, "serialize", None)
    if callable(serializer):
        try:
            data = serializer()
            diar = data.get("diarization") or []
            return [{"start": float(s["start"]), "end": float(s["end"]),
                     "speaker": s["speaker"]} for s in diar]
        except Exception:
            log.exception("diarize: DiarizeOutput.serialize() failed")
            return []

    # Fall 2: DiarizeOutput ohne serialize — direkte Annotation-Attribute
    annotation = getattr(result, "speaker_diarization", result)
    itertracks = getattr(annotation, "itertracks", None)
    if itertracks is None:
        log.warning("diarize: unbekanntes Pipeline-Ergebnis-Format (%s)",
                    type(result).__name__)
        return []

    segments: List[Dict[str, Any]] = []
    for turn, _, speaker in itertracks(yield_label=True):
        segments.append({
            "start": round(turn.start, 2),
            "end": round(turn.end, 2),
            "speaker": speaker,
        })
    segments.sort(key=lambda s: s["start"])
    return segments


def diarize(
    audio_path: str,
    num_speakers: Optional[int] = None,
    min_duration_off: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Run speaker diarization on *audio_path*.

    Optional tuning (UI: „Sprecheranzahl" + „Sensitivität"):
    - ``num_speakers``: min=max vorgeben (bekannte Sprecherzahl)
    - ``min_duration_off``: minimale Pause zwischen Sprecherwechseln
      (höher = weniger Wechsel/Flicker). None → Pipeline-Default.

    Returns a list of ``{"start": float, "end": float, "speaker": str}`` dicts.

    Raises :class:`DiarizationError` when the pipeline cannot be loaded
    (missing token, gated repo, …) — no silent empty list for config errors.
    """
    pipeline = _load_pipeline()

    kwargs: Dict[str, Any] = {}
    if num_speakers is not None:
        kwargs["min_speakers"] = num_speakers
        kwargs["max_speakers"] = num_speakers
    if min_duration_off is not None:
        kwargs["min_duration_off"] = min_duration_off

    log.info("diarize: running pyannote pipeline on %s %s", audio_path,
             kwargs or "(defaults)")
    try:
        result = pipeline(audio_path, **kwargs)
    except DiarizationError:
        raise
    except Exception as exc:
        log.exception("diarize: pipeline() threw on %s: %s", audio_path, exc)
        raise DiarizationError("run-failed", f"Diarization-Lauf fehlgeschlagen: {exc}") from exc

    segments = _extract_segments(result)
    speaker_set = set(s["speaker"] for s in segments)
    log.info("diarize: %d segments, %d speakers (%s)",
             len(segments), len(speaker_set),
             ", ".join(sorted(speaker_set)) if speaker_set else "none")
    return segments
