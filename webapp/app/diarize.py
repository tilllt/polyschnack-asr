"""HTTP-Client für den Diarization-Service (crispr-diar:5098, CrispASR — Option B).

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
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import threading
from typing import Callable

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
    """CrispASR-Label auf SPEAKER_xx normalisieren.

    Versteht Buchstaben (A→SPEAKER_00, Z→SPEAKER_25), bereits
    normalisierte SPEAKER_xx und die rohen CrispASR-Formate
    „(speaker 0)"/„speaker 3"/„12" (Change 126: fielen vorher still auf
    SPEAKER_00 zurück). Leere/unbekannte Werte → SPEAKER_00.
    """
    if not label:
        return "SPEAKER_00"
    s = str(label).strip()
    if s.startswith("SPEAKER_"):
        return s
    # Rohe CrispASR-Formate mit Zahl: „(speaker 0)", „speaker 3", „12"
    import re as _re

    m = _re.search(r"(\d{1,2})", s)
    if m:
        n = int(m.group(1))
        return f"SPEAKER_{n:02d}"
    code = ord(label[0].upper())
    if ord("A") <= code <= ord("Z"):
        return f"SPEAKER_{code - ord('A'):02d}"
    return "SPEAKER_00"


#: Whitelist der CrispASR-Diarization-Methoden (Server-Feld diarize_method).
#: Unbekannte Werte werden bewusst abgelehnt (ValueError) statt still auf
#: den Default zu fallen — ein Tippfehler darf nicht lautlos pyannote sein.
#: Methoden-Übersicht (CrispASR docs/cli.md):
#:   pyannote   mono — pyannote-seg-3.0-GGUF, läuft global über die volle
#:              Audio; mit --diarize-embedder auto (TitaNet) = Sherpa-
#:              Äquivalent nativ (global stabile Speaker-IDs)
#:   foxnose    mono, empfohlen — WeSpeaker-Embeddings + Clustering
#:   vad-turns  mono — pausenbasierte Turn-Erkennung (kein Modell)
#:   energy     NUR Stereo (Kanal-Vergleich) — auf Mono wirkungslos!
#:   xcorr      NUR Stereo (Kreuzkorrelation) — auf Mono wirkungslos!
#:   (sherpa/ecapa nicht gelistet: brauchen externes sherpa-onnx-Binary,
#:    das im Container fehlt — pyannote+Embedder deckt das nativ ab)
DIARIZE_METHODS = (
    "pyannote", "foxnose", "energy", "xcorr", "vad-turns",
)


def _post_diarize(
    audio_path: str,
    num_speakers: Optional[int],
    method: Optional[str],
    on_progress: Optional[Callable[[int], None]] = None,
) -> "httpx.Response":
    """Baut den Request und liefert die rohe httpx-Antwort (auch bei != 200).

    Gemeinsame Basis für :func:`diarize`. Der Dateiname wird IMMER auf .wav
    gezwungen (CrispASR dekodiert anhand der Dateiendung, nicht des
    Content-Types — Live-Befund 2026-08-16).
    """
    if method is not None and method not in DIARIZE_METHODS:
        raise ValueError(f"unbekannte diarize_method {method!r} — erlaubt: {', '.join(DIARIZE_METHODS)}")
    url = f"{settings.DIAR_URL.rstrip('/')}/v1/audio/transcriptions"
    with open(audio_path, "rb") as f:
        audio_bytes = f.read()
    # Storage ist nativ (MP3/OGG/…) — der CrispASR-diar-Service bekommt eine
    # 16-kHz-mono-WAV on-the-fly (gleiche Policy wie bei den ASR-Backends).
    if Path(audio_path).suffix.lower() != ".wav":
        # EIN Punkt! (.. wäre Parent von app → ImportError bei jedem
        # Nicht-WAV-Upload, verschluckt von service.py except Exception →
        # 0 Speaker trotz Status done. Live-Befund 2026-08-16.)
        from .audio_utils import convert_to_wav_16k_mono

        audio_bytes, _, _ = convert_to_wav_16k_mono(audio_bytes, Path(audio_path).name)

    data: Dict[str, Any] = {
        "response_format": "diarized_json",
        "diarize": "true",
        "diarize_method": method or settings.DIARIZE_METHOD,
        # Change 126: diarize_embedder erzwingt serverseitig das GLOBALE
        # Speaker-Clustering. Ohne diesen Wert lädt der Server nie einen
        # Embedder (Re-Clustering-Pfad verlangt nicht-leeren Wert) und die
        # Labels bleiben chunk-lokal → alles fällt auf ein Label
        # (Live-Befund 2026-08-25: 26/26 SPEAKER_00 bei 75-min-Meeting).
        "diarize_embedder": (
            settings.DIARIZE_FOXNOSE_EMBEDDER
            if (method or settings.DIARIZE_METHOD) == "foxnose"
            else settings.DIARIZE_EMBEDDER
        ),
        # Fix 2026-08-15: parakeet (Full-Attention-FastConformer) bekommt ohne
        # chunk_seconds den ganzen Clip — bei langem Audio greift das
        # Server-Memory-Cap und die Transkription bricht nach ~165 s ab
        # (CrispASR-Doku: „one coherent segment (or the silence-split
        # longform above the memory cap)"). Explizites Chunking aktiviert die
        # parakeet-interne Segmentierung über die volle Länge (Issue #257).
        "chunk_seconds": str(settings.DIARIZE_CHUNK_SECONDS),
    }
    if num_speakers is not None:
        data["diarize_max_speakers"] = str(num_speakers)

    progress_stop: Optional[threading.Event] = None
    if on_progress is not None:
        # Change 150: CrispASR-Server liefert GET /progress {"busy", "progress"}
        # (0..100) — Daemon-Thread pollt, während der POST läuft. Die Webapp
        # zeigt damit ECHTEN Server-Fortschritt (kein Raten).
        progress_stop = threading.Event()

        def _poll_progress() -> None:
            prog_url = f"{settings.DIAR_URL.rstrip('/')}/progress"
            while not progress_stop.is_set():
                try:
                    with httpx.Client(timeout=5) as pc:
                        r = pc.get(prog_url, timeout=3)
                    if r.status_code == 200:
                        d = r.json()
                        if (
                            d.get("busy")
                            and isinstance(d.get("progress"), int)
                            and d["progress"] >= 0
                        ):
                            on_progress(int(d["progress"]))
                except Exception:
                    pass
                progress_stop.wait(2.0)

        threading.Thread(target=_poll_progress, daemon=True).start()

    try:
        with httpx.Client(timeout=1800) as client:
            # Dateiname IMMER auf .wav zwingen: der CrispASR-Server dekodiert
            # anhand der Dateiendung, nicht des Content-Types. Bei MP3-Uploads
            # kam sonst der Originalname (xxx.mp3) mit WAV-Inhalt an → Audio
            # kaputt → Transkription lief, aber 0 Speaker-Labels (Live-Befund
            # 2026-08-16: WAV-Upload=SPEAKER_00, MP3-Upload=None). Gleiches
            # Muster wie aligner_client.py ("audio.wav").
            wav_name = os.path.splitext(os.path.basename(audio_path))[0] + ".wav"
            resp = client.post(
                url,
                files={"file": (wav_name, audio_bytes, "audio/wav")},
                data=data,
            )
    except httpx.HTTPError as exc:
        log.warning("diarize: diar-Service nicht erreichbar (%s)", exc)
        if progress_stop is not None:
            progress_stop.set()
        raise DiarizationError(
            "service-unreachable",
            "Der Diarization-Service ist nicht erreichbar. Bitte den "
            "Administrator informieren (Container 'diar' prüfen).",
        ) from exc
    if progress_stop is not None:
        progress_stop.set()
    return resp


def diarize(
    audio_path: str,
    num_speakers: Optional[int] = None,
    min_duration_off: Optional[float] = None,
    method: Optional[str] = None,
    on_progress: Optional[Callable[[int], None]] = None,
) -> List[Dict[str, Any]]:
    """Ruft den CrispASR-diar-Service und liefert {start, end, speaker}-Segmente.

    Optionales Tuning (UI: „Sprecheranzahl"): ``num_speakers`` wird als
    ``diarize_max_speakers`` übertragen. ``min_duration_off`` hat in
    CrispASR keine direkte Entsprechung und wird bewusst nicht übertragen.
    ``method`` (pyannote|foxnose|energy|xcorr|vad-turns) überschreibt die
    Server-Methode pro Request; unbekannte Werte → ValueError (kein stiller
    Fallback auf den Default).

    Raises :class:`DiarizationError` (service-unreachable / Proxy-Fehler) —
    nie eine stille leere Liste bei Service-Problemen.
    """
    resp = _post_diarize(audio_path, num_speakers, method, on_progress)

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
