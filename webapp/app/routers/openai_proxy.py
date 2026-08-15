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

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse
from sqlmodel import Session, select

from ..db import get_session
from ..identity import Identity
from ..asr_client import get_client

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v1")


def _require_api_key(
    request: Request,
    session: Session = Depends(get_session),
):
    """NUR echte API-Keys (Bearer) — anon-Sessions sind hier NICHT erlaubt.

    Review 2026-08-15 (P0.2): Der Proxy ist offenes Compute für anonyme
    Besucher, solange current_identity auf ensure_anonymous_user zurückfällt.
    Ein OpenAI-kompatibler Endpoint gehört in die Hände von Key-Besitzern.
    """
    from ..models import ApiKey, User, hash_token

    auth = request.headers.get("Authorization", "") if hasattr(request, "headers") else ""
    if not auth.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="API key required (Authorization: Bearer <key> — Settings → API-Keys)",
        )
    token = auth[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="invalid API key")
    key = session.exec(
        select(ApiKey).where(ApiKey.token_hash == hash_token(token))
    ).first()
    if not key:
        raise HTTPException(status_code=401, detail="invalid API key")
    if key.expires_at is not None:
        exp = key.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp <= datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="API key expired")
    user = session.get(User, key.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid API key")
    key.last_used_at = datetime.now(timezone.utc)
    session.add(key)
    session.commit()
    return Identity(user, key.level)

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
    _identity=Depends(_require_api_key),
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
    # Review 2026-08-15 (P0.2): client.transcribe ist SYNCHRON (httpx mit
    # Timeout bis 3600 s). Im async-Handler würde ein langer Call den
    # Event-Loop einfrieren — jeder andere Request wartet. asyncio.to_thread
    # hält den Loop frei; der Adapter-Timeout bleibt als Rest-Schutz.
    try:
        client = get_client(target)

        def _do_transcribe():
            return client.transcribe(raw, filename, mime)

        result = await asyncio.to_thread(_do_transcribe)
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
