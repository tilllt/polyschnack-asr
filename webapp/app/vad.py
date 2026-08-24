"""Silero VAD pre-processing for the webapp backend.

Uses ONNX Runtime directly (no PyTorch — Change 060: das PyPI-Paket
silero-vad zieht torch+torchaudio transitiv in das Webapp-Image, ~2,5 GB
Ballast). Das Modell ``silero_vad.onnx`` (~2 MB, MIT) wird einmalig nach
``DATA_DIR/models/`` geladen und per onnxruntime-Session inferiert.

Exposes:

- ``trim_silence(audio_bytes) -> bytes`` — trims leading/trailing silence
- ``trim_silence_with_offset(audio_bytes) -> (bytes, offset_s)``
- ``detect_speech_regions(audio_bytes) -> list[dict]`` — VAD segments
"""
from __future__ import annotations

import io
import logging
import subprocess
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .config import settings

TARGET_SR = 16_000
WINDOW_SAMPLES = 512  # Silero: 512 Samples @ 16 kHz = 32 ms pro Frame
log = logging.getLogger(__name__)

MODEL_FILENAME = "silero_vad.onnx"
MODEL_URLS = [
    # GitHub raw (snakers4/silero-vad) — das HF-Repo existiert nicht
    # (HF-Pfad liefert 401). ~2,3 MB, MIT.
    "https://raw.githubusercontent.com/snakers4/silero-vad/master/src/silero_vad/data/silero_vad.onnx",
]

_session = None  # onnxruntime.InferenceSession (lazy)
_session_checked = False


def model_path() -> Path:
    """Cache-Pfad des ONNX-Modells (gemeinsames Modelle-Verzeichnis)."""
    return settings.DATA_DIR / "models" / MODEL_FILENAME


def _ensure_model(timeout: float = 30.0) -> Optional[Path]:
    """Download ``silero_vad.onnx`` einmalig nach ``DATA_DIR/models/``.

    Returns Pfad oder None bei Fehlschlag (VAD bleibt dann deaktiviert —
    gleiches Verhalten wie vor Change 060, nur ohne pip-Install).
    """
    path = model_path()
    if path.exists() and path.stat().st_size > 100_000:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    import httpx

    tmp = path.with_suffix(".onnx.tmp")
    for url in MODEL_URLS:
        try:
            log.info("Silero VAD: lade Modell von %s", url)
            r = httpx.get(url, timeout=timeout, follow_redirects=True)
            r.raise_for_status()
            if len(r.content) < 100_000:
                log.warning("Silero VAD: Download zu klein (%d B) — übersprungen", len(r.content))
                continue
            tmp.write_bytes(r.content)
            tmp.rename(path)
            log.info("Silero VAD: Modell gecacht unter %s", path)
            return path
        except Exception as exc:  # noqa: BLE001 — Download-Fehler sind nicht fatal
            log.warning("Silero VAD: Download von %s fehlgeschlagen: %s", url, exc)
    return None


def _get_session():
    """Lazy onnxruntime-Session (CPU). None wenn Modell nicht verfügbar."""
    global _session, _session_checked
    if _session_checked:
        return _session
    _session_checked = True
    try:
        import onnxruntime as ort

        path = _ensure_model()
        if path is None:
            return None
        _session = ort.InferenceSession(
            str(path), providers=["CPUExecutionProvider"]
        )
        log.info("Silero VAD: ONNX-Session bereit (%s)", path)
    except Exception:  # noqa: BLE001
        log.warning("Silero VAD unavailable — VAD preprocessing disabled", exc_info=True)
        _session = None
    return _session


def vad_available() -> bool:
    """True wenn die VAD-Session ladbar ist (für /api/models/status)."""
    return _get_session() is not None


def speech_probs(wav: np.ndarray, session) -> np.ndarray:
    """Frame-Wahrscheinlichkeiten [0..1] für 512er-Chunks @ 16 kHz.

    Stateful-Forward (Silero v6-ONNX): das Modell hat LSTM-State
    (Inputs ``input``, ``state`` [2,1,128], ``sr``), der über das ganze
    Audio fortgeführt wird — identische Semantik wie das frühere
    silero-vad-6.x-Paket (Change 060: gleiches Verhalten, ohne torch).
    Wichtig: pro Chunk werden die letzten 64 Samples des vorherigen
    Chunks als Kontext vorangestellt (Input-Länge 512+64=576) — ohne
    den Kontext liefert das Modell keine brauchbaren Probs
    (verifiziert 2026-08-21 gegen die offizielle utils_vad.py).
    """
    num_samples = wav.size
    n_chunks = (num_samples - WINDOW_SAMPLES) // WINDOW_SAMPLES + 1
    probs = np.empty(n_chunks, dtype=np.float32)
    state = np.zeros((2, 1, 128), dtype=np.float32)
    sr = np.array(TARGET_SR, dtype=np.int64)
    context = np.zeros(64, dtype=np.float32)  # Kontext: letzte 64 Samples
    for i in range(n_chunks):
        chunk = wav[i * WINDOW_SAMPLES:(i + 1) * WINDOW_SAMPLES]
        x = np.concatenate([context, chunk]).reshape(1, WINDOW_SAMPLES + 64)
        x = np.ascontiguousarray(x, dtype=np.float32)
        out, state = session.run(None, {"input": x, "state": state, "sr": sr})
        probs[i] = float(np.asarray(out).reshape(-1)[0])
        context = x[0, -64:]
    return probs


def regions_from_probs(
    probs: np.ndarray,
    num_samples: int,
    sampling_rate: int = TARGET_SR,
    threshold: float = 0.5,
    min_speech_ms: int = 250,
    min_silence_ms: int = 400,
    speech_pad_ms: int = 120,
) -> List[Dict[str, Any]]:
    """Regionen aus Frame-Wahrscheinlichkeiten (silero-Semantik).

    Reine Funktion (unit-testbar ohne Modell). Rückgabe:
    ``[{"start": s, "end": e}, ...]`` in Sekunden. Stille-Lücken >=
    min_silence_ms beenden eine Region; kurze Regionen (< min_speech_ms)
    werden verworfen; jede Region wird um speech_pad_ms erweitert und auf
    [0, num_samples] geklemmt.
    """
    window = WINDOW_SAMPLES
    min_speech = int(sampling_rate * min_speech_ms / 1000)
    min_silence = int(sampling_rate * min_silence_ms / 1000)
    pad = int(sampling_rate * speech_pad_ms / 1000)

    regions: List[Dict[str, int]] = []
    current: Optional[Dict[str, int]] = None
    silence = 0
    for i, prob in enumerate(probs):
        start = i * window
        end = start + window
        if prob >= threshold:
            silence = 0
            if current is None:
                current = {"start": start, "end": end}
            else:
                current["end"] = end
        else:
            silence += window
            if current is not None and silence >= min_silence:
                if current["end"] - current["start"] > min_speech:
                    regions.append(current)
                current = None
    if current is not None and current["end"] - current["start"] > min_speech:
        regions.append(current)

    out: List[Dict[str, Any]] = []
    for r in regions:
        start = max(0, r["start"] - pad)
        end = min(num_samples, r["end"] + pad)
        if end > start:
            out.append({"start": start / sampling_rate, "end": end / sampling_rate})
    return out


def _decode_to_wav(audio_bytes: bytes) -> np.ndarray:
    """Decode any audio to mono 16 kHz float32 [-1, 1] via ffmpeg."""
    cmd = [
        "ffmpeg", "-nostdin", "-loglevel", "error",
        "-i", "pipe:0",
        "-ac", "1", "-ar", str(TARGET_SR),
        "-f", "s16le", "pipe:1",
    ]
    p = subprocess.run(cmd, input=audio_bytes, capture_output=True, check=False)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg decode failed: {p.stderr.decode(errors='ignore')[:200]}")
    return np.frombuffer(p.stdout, dtype="<i2").astype(np.float32) / 32767.0


def detect_speech_regions(
    audio_bytes: bytes,
    threshold: float = 0.5,
    min_silence_ms: int = 400,
    speech_pad_ms: int = 120,
) -> List[Dict[str, Any]]:
    """Run VAD and return speech region dicts [{start, end}, ...] in seconds."""
    session = _get_session()
    if session is None:
        return []

    try:
        wav = _decode_to_wav(audio_bytes)
    except Exception:
        log.exception("audio decode failed in VAD")
        return []

    try:
        probs = speech_probs(wav, session)
        return regions_from_probs(
            probs, wav.size,
            threshold=threshold,
            min_silence_ms=min_silence_ms,
            speech_pad_ms=speech_pad_ms,
        )
    except Exception:
        log.exception("VAD inference failed")
        return []


def trim_silence(
    audio_bytes: bytes,
    threshold: float = 0.5,
    min_silence_ms: int = 400,
    speech_pad_ms: int = 120,
) -> bytes:
    """Remove leading/trailing silence. Returns trimmed WAV bytes."""
    return trim_silence_with_offset(
        audio_bytes, threshold, min_silence_ms, speech_pad_ms
    )[0]


def squash_silence_with_mapping(
    audio_bytes: bytes,
    threshold: float = 0.5,
    min_silence_ms: int = 400,
    speech_pad_ms: int = 120,
) -> Tuple[bytes, List[Tuple[float, float, float]]]:
    """Change 114: entfernt ALLE Stille (auch zwischen Speech-Regionen).

    Schneidet jede Speech-Region (mit Pad) aus dem Original und
    konkateniert sie. Rückgabe: (squashed_wav, mapping) mit
    mapping = [(alt_start_s, alt_end_s, new_start_s), ...] — ein
    Eintrag pro Region. Damit lassen sich Timestamps von der neuen
    (kürzeren) Zeitachse auf die Original-Zeitachse abbilden und
    umgekehrt.

    Fallback: keine Speech-Region oder VAD nicht verfügbar →
    (Original-Bytes unverändert, []) — nie ein Abbruch.
    """
    regions = detect_speech_regions(audio_bytes, threshold, min_silence_ms, speech_pad_ms)
    if not regions:
        return audio_bytes, []

    wav = _decode_to_wav(audio_bytes)
    total = wav.size
    # Nichts zu tun, wenn eine einzige Region das ganze Audio abdeckt.
    if len(regions) == 1:
        first = int(regions[0]["start"] * TARGET_SR)
        last = int(regions[0]["end"] * TARGET_SR)
        if first <= 0 and last >= total:
            return audio_bytes, []

    chunks: List[np.ndarray] = []
    mapping: List[Tuple[float, float, float]] = []
    new_cursor = 0.0
    for r in regions:
        start = max(0, int(r["start"] * TARGET_SR))
        end = min(total, int(r["end"] * TARGET_SR))
        if end <= start:
            continue
        chunk = wav[start:end]
        chunks.append(chunk)
        mapping.append((start / TARGET_SR, end / TARGET_SR, new_cursor))
        new_cursor += chunk.size / TARGET_SR

    if not chunks:
        return audio_bytes, []

    squashed = np.concatenate(chunks)
    s16 = (squashed * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TARGET_SR)
        w.writeframes(s16)
    return buf.getvalue(), mapping


def trim_silence_with_offset(
    audio_bytes: bytes,
    threshold: float = 0.5,
    min_silence_ms: int = 400,
    speech_pad_ms: int = 120,
) -> Tuple[bytes, float]:
    """Remove leading/trailing silence and return (trimmed_wav, offset_s).

    offset_s = Sekunden, die am ANFANG entfernt wurden (0.0 wenn nichts
    getrimmt). Wichtig für die Timestamp-Kompensation: ASR/Aligner laufen
    auf dem getrimmten Audio — die Wort-Zeiten müssen danach um offset_s
    nach hinten geschoben werden, damit sie zur Originaldatei passen, die
    das Playback nutzt. (2026-08-14, User-Befund „Klick spielt falschen Ton")
    """
    regions = detect_speech_regions(audio_bytes, threshold, min_silence_ms, speech_pad_ms)
    if not regions:
        return audio_bytes, 0.0

    wav = _decode_to_wav(audio_bytes)
    total = wav.size

    first_start = int(regions[0]["start"] * TARGET_SR)
    last_end = int(regions[-1]["end"] * TARGET_SR)

    if first_start <= 0 and last_end >= total:
        return audio_bytes, 0.0

    trimmed = wav[first_start:last_end]
    s16 = (trimmed * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TARGET_SR)
        w.writeframes(s16)
    return buf.getvalue(), regions[0]["start"]
