"""OpenAI-kompatibler Transkriptions-Proxy (Backend-Hopping, 2026-08-15).

POST /v1/audio/transcriptions
    → nimmt multipart (file, model, response_format, …) wie OpenAI
    → mappt ``model`` auf ein Backend aus backends.yaml
    → leitet an den passenden Adapter weiter (get_client)
    → liefert das Ergebnis im OpenAI-Format zurück (json/text/verbose_json/
      srt/vtt)

Auth: API-Key (Bearer) — identisch zu den /api/keys aus den Settings.
Damit ist PolySchnack als Router zu allen Backends nutzbar: EIN Endpoint,
ein Key, jede OpenAI-kompatible Client-Lib.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse

from ..db import get_session
from ..identity import current_identity
from ..asr_client import get_client
from sqlmodel import Session

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v1")


def _require_identity(
    request: Request,
    session: Session = Depends(get_session),
):
    """API-Key/Session-Auth (wie /api/keys): 401 ohne gültigen Key."""
    return current_identity(request, session)

#: Modell → Backend-Mapping. Basis: backends.yaml. Zusätzlich erlaubt die
#: Env-Variable PS_MODEL_BACKENDS eine JSON-Map zur Laufzeit zu überschreiben:
#:   {"parakeet-tdt-0.6b-v3": "ps-pk-onnx", "qwen3-asr-0.6b": "crispr-qwen3"}
_DEFAULT_MODEL_BACKENDS: Dict[str, str] = {
    # ONNX/Parakeet
    "parakeet-tdt-0.6b-v3": "ps-pk-onnx",
    "istupakov/parakeet-tdt-0.6b-v3-onnx": "ps-pk-onnx",
    "grikdotnet/parakeet-tdt-0.6b-fp16": "ps-pk-onnx",
    # C++-Backends
    "parakeet-cpp": "crispr-pk-cpp",
    "qwen3-asr-0.6b": "crispr-qwen3",
    "qwen3": "crispr-qwen3",
    "moonshine-de": "crispr-moonshine-de",
    "ark": "crispr-ark",
    "canary": "crispr-canary",
    "canary-1b-v2": "crispr-canary",
}

#: Alias: ein explizites ``backend``-Form-Feld überschreibt das Modell-Mapping.
_ALLOWED_BACKENDS = {
    "ps-pk-onnx", "crispr-pk-cpp", "crispr-qwen3", "crispr-moonshine-de",
    "crispr-ark", "crispr-canary", "crispr-diar",
}

_FORMATS = {"json", "text", "verbose_json", "srt", "vtt"}


def _model_backends() -> Dict[str, str]:
    raw = os.getenv("PS_MODEL_BACKENDS", "")
    if not raw:
        return dict(_DEFAULT_MODEL_BACKENDS)
    import json

    try:
        extra = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("PS_MODEL_BACKENDS ist kein gültiges JSON — ignoriert")
        return dict(_DEFAULT_MODEL_BACKENDS)
    merged = dict(_DEFAULT_MODEL_BACKENDS)
    merged.update(extra)
    return merged


@router.post("/audio/transcriptions")
async def create_transcription(
    file: UploadFile = File(...),
    model: Optional[str] = Form(None),
    backend: Optional[str] = Form(None),
    language: Optional[str] = Form(None),
    response_format: Optional[str] = Form("json"),
    timestamp_granularities: Optional[str] = Form(None),
    temperature: Optional[float] = Form(None),
    prompt: Optional[str] = Form(None),
    _identity=Depends(_require_identity),
) -> Any:
    """OpenAI-kompatible Transkription — routet ans Backend laut ``model``.

    Nutzbar mit dem OpenAI SDK: ``OpenAI(base_url="https://…", api_key="<Key>")``.
    """
    if response_format not in _FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"invalid response_format '{response_format}' (json/text/verbose_json/srt/vtt)",
        )

    # ---- Backend-Auswahl: explizites Feld > Modell-Mapping > Default ----
    if backend is not None:
        if backend not in _ALLOWED_BACKENDS:
            raise HTTPException(status_code=400, detail=f"unknown backend: {backend}")
        target = backend
    else:
        mapping = _model_backends()
        target = mapping.get(model or "") if model else None
        if model and not target:
            # Unbekanntes Modell → kein stiller Fallback auf Default,
            # sondern klarer Fehler (der Client soll das Mapping kennen).
            raise HTTPException(
                status_code=400,
                detail=f"unknown model '{model}' — verfügbare: {', '.join(sorted(mapping))}",
            )
        if not target:
            target = os.getenv("ASR_BACKEND", "ps-pk-onnx")

    # ---- Audio einlesen (mit Größen-Limit) ----
    from ..config import settings as _s

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty file")
    if len(raw) > _s.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"file too large (max {_s.MAX_UPLOAD_SIZE_MB} MB)",
        )
    filename = file.filename or "audio.bin"
    mime = file.content_type or "application/octet-stream"
    await file.close()

    # ---- An den Adapter weiterleiten ----
    try:
        client = get_client(target)
        result = client.transcribe(raw, filename, mime)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — Proxy muss Fehler sauber melden
        log.exception("proxy transcription failed (backend=%s)", target)
        raise HTTPException(status_code=502, detail=f"backend '{target}' failed: {exc}")

    # ---- OpenAI-Format aus dem canonical Ergebnis bauen ----
    from ..service import to_srt, to_vtt

    text = str(result.get("text", "")).strip()
    segments = result.get("segments") or []
    duration = result.get("duration")

    if response_format == "text":
        return PlainTextResponse(text)
    if response_format == "srt":
        return PlainTextResponse(to_srt(segments))
    if response_format == "vtt":
        return PlainTextResponse(to_vtt(segments))
    if response_format == "verbose_json":
        return {
            "text": text,
            "language": result.get("language") or language or "unknown",
            "duration": duration,
            "segments": segments,
        }
    return {"text": text}
