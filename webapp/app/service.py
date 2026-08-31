"""Orchestration layer — coordinates file I/O, ASR calls, and DB writes.

``process_recording`` is the background function scheduled by the upload
endpoint.  Subtitle/text export helpers are also housed here.
"""
from __future__ import annotations

import logging
import math
import os
import subprocess as sp
import re
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from sqlmodel import Session, select

from . import asr_client, crud
from .asr_client import get_client
from .audio_utils import convert_to_wav_16k_mono
from .config import settings
from .crud import get_or_create_user, get_user, set_progress
from .db import engine
from .diarize import DiarizationError
import os

# Heavy optional deps (onnxruntime/pyannote/torch) are imported lazily inside
# the functions so the module imports fast and the CI test job stays light.

# Change 124: Cancel-Registry für den Background-Alignment-Worker (Change 045).
# Der Worker läuft NACH „done" ohne Queue-Job (job=None) → _cancelled() ist
# dort wirkungslos. Cancel setzt die rec_id in dieses Set; der Worker prüft es
# vor jeder Align-Gruppe und bricht mit alignment="skipped" ab.
_BG_ALIGN_CANCEL: set[int] = set()
_align_lock = threading.Lock()


def _align_cancelled(rec_id: int) -> bool:
    with _align_lock:
        return rec_id in _BG_ALIGN_CANCEL


def cancel_background_align(rec_id: int) -> None:
    """Change 124: laufendes/pendendes Background-Alignment abbrechen."""
    with _align_lock:
        _BG_ALIGN_CANCEL.add(rec_id)
    try:
        _AlignmentCache.delete(rec_id)
    except Exception:
        pass


def _abort_if_cancelled(job, rec_id: int) -> bool:
    """Change 124: Cancel/Timeout NACH einer blockierenden Phase prüfen
    (z.B. Diarization-Call). True, wenn abgebrochen wurde (failed gesetzt)."""
    if _cancelled(job, rec_id):
        _abort_recording(rec_id, "Abgebrochen (User-Cancel)")
        return True
    return False


def _trim_silence(audio_bytes: bytes) -> Tuple[bytes, float]:
    """VAD-Trim: entfernt führende/trailing Stille.

    Returns (getrimmte_bytes, offset_s) — offset_s sind die am Anfang
    entfernten Sekunden (0.0 ohne Trim). Der Offset ist nötig, um die
    Timestamps am Ende auf die Original-Zeitbasis zu schieben (das
    Playback nutzt die Originaldatei). (2026-08-14)
    """
    from .vad import trim_silence_with_offset
    return trim_silence_with_offset(audio_bytes)


def _run_vad_mode(run) -> str:
    """Change 114: effektiver VAD-Modus eines Runs (Legacy-Fallback).

    enable_vad=True ohne vad_mode (alte Runs) → "edges". Fehlende
    Spalte (None/"") fällt auf den bool zurück. None-Run → "off".
    """
    if run is None:
        return "off"
    mode = getattr(run, "vad_mode", None) or ""
    if mode in ("off", "edges", "all"):
        return mode
    return "edges" if run.enable_vad else "off"


def _probe_audio_duration(audio_bytes: bytes) -> Optional[float]:
    """Change 146: Dauer der VERARBEITETEN Audio-Bytes via ffprobe
    (Segment-Zeiten beziehen sich auf dieses Audio, nicht auf das
    Original). None bei Fehlern — der Aufrufer lässt den Check aus."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tf:
            tf.write(audio_bytes)
            probe = tf.name
        try:
            r = sp.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=nk=1:nw=1", probe],
                capture_output=True, timeout=30,
            )
            return float(r.stdout.decode().strip())
        finally:
            os.unlink(probe)
    except Exception:
        return None


# Change 147: TTS-Marker für deterministische Vollständigkeits-Erkennung
# (User-Idee 2026-08-28). Ein eindeutiger Marker (Ziffernfolge, einmalig
# als WAV generiert) wird ans Audio-Ende gehängt — nur ab 5 min Audio
# (Triage: kurze Aufnahmen bleiben unberührt). Transkribiert die ASR den
# Marker, existieren Segmente NACH der echten Audiodauer → die Erkennung
# ist ZEIT-basiert (kein Abspann-Risiko, kein Sprach-Raten). Fehlt der
# Marker (Stream abgerissen), wird der Job ehrlich als failed markiert.
_TRANSCRIPT_MARKER_PATH = os.path.join(os.path.dirname(__file__), "transcript_marker.wav")
_TRANSCRIPT_MARKER_S = 8.1   # bekannte Marker-Dauer (16 kHz mono s16)
_TRANSCRIPT_MIN_S = 300.0    # Marker nur ab 5 min Audio
_MARKER_TAIL_S = 15.0        # Toleranz: letztes Segment darf ≤15 s vor dem
                             # (markerverlängerten) Audio-Ende enden


def _append_transcript_marker(audio_bytes: bytes) -> bytes:
    """Change 147: Hängt den TTS-Marker (Ziffernfolge 7-4-2-8-1-6-0-3-9)
    ans Audio-Ende und konvertiert zu 16 kHz mono WAV (concat via ffmpeg).
    Liefert das Audio unverändert, wenn der Marker fehlt oder ffmpeg
    scheitert — dann greift keine Vollständigkeits-Erkennung (kein
    falsches failed).
    Change 154: concat OHNE aresample/pan-Filterkette — die erzeugte WAV
    konnte der ONNX-ASR nicht transkribieren (leere Segmente ab 5 min,
    Produktions-Befund 2026-08-29). Sample-Rate/Kanäle stattdessen als
    Output-Flags; ffmpeg konvertiert gemischte Inputs automatisch."""
    if not audio_bytes or not os.path.exists(_TRANSCRIPT_MARKER_PATH):
        return audio_bytes
    try:
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tf:
            tf.write(audio_bytes)
            path = tf.name
        out_path = tempfile.mktemp(suffix=".wav")
        try:
            # Change 154: Output als Temp-DATEI statt pipe:1 — ffmpeg schreibt
            # bei pipe:1 eine unbekannte Größe (0x7FFFFFFF) in den WAV-Header,
            # die der ONNX-ASR nicht verarbeiten kann (leere Segmente ab 5 min,
            # Produktions-Befund 2026-08-29). Bei Datei-Output patcht ffmpeg
            # die echte Größe; -ar/-ac konvertieren gemischte Inputs.
            r = sp.run(
                ["ffmpeg", "-hide_banner", "-i", path, "-i", _TRANSCRIPT_MARKER_PATH,
                 "-filter_complex", "concat=n=2:v=0:a=1[aout]",
                 "-map", "[aout]", "-ar", "16000", "-ac", "1",
                 "-acodec", "pcm_s16le", "-f", "wav", out_path],
                capture_output=True, timeout=180,
            )
            if r.returncode == 0:
                with open(out_path, "rb") as f:
                    out = f.read()
            else:
                out = b""
        finally:
            os.unlink(path)
            if os.path.exists(out_path):
                os.unlink(out_path)
        if r.returncode == 0 and out:
            return out
        log.warning("Change 147: ffmpeg-Marker-Anhang fehlgeschlagen (rc=%s)", r.returncode)
    except Exception:
        log.exception("Change 147: Marker-Anhang fehlgeschlagen")
    return audio_bytes


def _marker_ratio(text: str) -> float:
    """Anteil der Ziffern-/Zahlwort-Tokens am Segment-Text (0..1)."""
    tokens = [t for t in re.split(r"\s+", str(text)) if t.strip()]
    if not tokens:
        return 0.0
    hits = 0
    for t in tokens:
        core = t.strip(".,;:!?\"'()[]-–—")
        if core.isdigit():
            hits += 1
        elif core.lower() in _MARKER_WORDS:
            hits += 1
    return hits / len(tokens)


_MARKER_WORDS = {
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "null", "eins", "zwei", "drei", "vier", "fünf", "fuenf", "sechs", "sieben",
    "acht", "neun", "um", "dois", "tres", "quatro", "cinco", "seis", "sete",
    "oito", "nove",
}


def _strip_transcript_marker(
    segments: List[Dict[str, Any]], text: str, audio_total_s: Optional[float],
) -> Tuple[List[Dict[str, Any]], str, bool]:
    """Change 147: Entfernt Marker-Segmente (zeitbasiert: Segmente nach
    der echten Audiodauer ODER überwiegend aus Ziffern) und meldet, ob
    der Marker transkribiert wurde. Rückgabe (segments, text, found).
    found=True → die ASR hat das Audio-Ende erreicht (vollständig)."""
    if not segments:
        return segments, text, False
    clean = list(segments)
    removed = 0
    while clean and removed < 4:
        last = clean[-1]
        last_start = float(last.get("start") or 0)
        is_tail = (
            audio_total_s is not None
            and last_start >= audio_total_s - _TRANSCRIPT_MARKER_S - 1.0
        )
        if is_tail or _marker_ratio(last.get("text") or "") >= 0.5:
            clean.pop()
            removed += 1
        else:
            break
    if not removed:
        return segments, text, False
    new_text = " ".join(str(s.get("text") or "").strip() for s in clean).strip()
    return clean, new_text, True


def _transcript_complete(
    segments: List[Dict[str, Any]], audio_total_s: Optional[float],
) -> bool:
    """Change 147: Hat die ASR das Audio-Ende erreicht? Das letzte Segment
    darf höchstens _MARKER_TAIL_S vor dem (markerverlängerten) Ende enden.
    Keine Aussage möglich → True (nie ein falsches failed)."""
    if not segments or not audio_total_s:
        return True
    last_end = max(float(s.get("end") or 0) for s in segments)
    return last_end >= audio_total_s - _MARKER_TAIL_S


def _apply_vad(audio_bytes: bytes, mode: str) -> Tuple[bytes, Optional[Dict[str, Any]]]:
    """Change 114: VAD-Preprocessing nach Modus (off|edges|all).

    Rückgabe (audio_bytes, vad_meta):
      "off"    → (unverändert, None)
      "edges"  → (getrimmt, {"type": "shift", "offset_s": x})
      "all"    → (gesquasht, {"type": "map", "mapping": [[alt_start, alt_end, new_start], …]})
    Ehrlicher Fallback: Modell fehlt/kein Speech/Fehler → unverändert +
    None (nie ein Abbruch, wie bisher beim Trim).
    """
    if mode == "edges":
        try:
            trimmed, offset = _trim_silence(audio_bytes)
            if offset > 0:
                return trimmed, {"type": "shift", "offset_s": offset}
            return audio_bytes, None
        except Exception as exc:
            log.warning("vad: edges fehlgeschlagen — weiter mit Original: %s", exc)
            return audio_bytes, None
    if mode == "all":
        try:
            from .vad import squash_silence_with_mapping
            squashed, mapping = squash_silence_with_mapping(audio_bytes)
            if mapping:
                return squashed, {"type": "map",
                                  "mapping": [[a, b, c] for a, b, c in mapping]}
            return audio_bytes, None
        except Exception as exc:
            log.warning("vad: all fehlgeschlagen — weiter mit Original: %s", exc)
            return audio_bytes, None
    return audio_bytes, None


def _map_time(t: float, mapping: List[List[float]]) -> float:
    """Original-Zeit → Zeit auf der gesquashten Achse (Change 114).

    Zeitpunkte in entfernten Lücken existieren im squashten Audio nicht
    mehr → deterministisches Clamping: vor der ersten Region → 0.0, in
    einer Lücke → Ende der VORHERIGEN Region, nach der letzten Region →
    Ende der letzten Region.
    """
    for i, (alt_start, alt_end, new_start) in enumerate(mapping):
        if alt_start <= t <= alt_end:
            return new_start + (t - alt_start)
        if i < len(mapping) - 1 and alt_end < t < mapping[i + 1][0]:
            # Lücke zwischen Region i und i+1 → Ende von Region i
            return new_start + (alt_end - alt_start)
    if t < mapping[0][0]:
        return 0.0
    return mapping[-1][2] + (mapping[-1][1] - mapping[-1][0])


def _unmap_time(t: float, mapping: List[List[float]]) -> float:
    """Zeit auf der gesquashten Achse → Original-Zeit (Change 114).

    Fugen (zwischen konkatenierten Regionen) haben kein Original-Pendant
    → deterministisches Clamping auf das Ende der VORHERIGEN Region
    (konsistent mit dem Lücken-Clamping von _map_time).
    """
    for i, (alt_start, alt_end, new_start) in enumerate(mapping):
        dur = alt_end - alt_start
        if new_start <= t <= new_start + dur:
            return alt_start + (t - new_start)
        if i < len(mapping) - 1 and new_start + dur < t < mapping[i + 1][2]:
            return alt_end  # Fuge zwischen Region i und i+1
    if not mapping:
        return t
    if t < mapping[0][2]:
        return mapping[0][0]
    return mapping[-1][1]


def _remap_segments(segments: list, mapping: List[List[float]], inverse: bool = False) -> None:
    """Schiebt alle Timestamps durch das Squash-Mapping (in-place).

    inverse=False (forward): Original → gesquashte Achse.
    inverse=True: gesquashte → Original-Achse. Behandelt start/end UND
    start_ms/end_ms, Segment- und Wort-Ebene. (Change 114)
    """
    fn = _unmap_time if inverse else _map_time

    def _one(d: dict) -> None:
        if d.get("start") is not None:
            d["start"] = fn(float(d["start"]), mapping)
        elif d.get("start_ms") is not None:
            d["start_ms"] = fn(float(d["start_ms"]) / 1000.0, mapping) * 1000.0
        if d.get("end") is not None:
            d["end"] = fn(float(d["end"]), mapping)
        elif d.get("end_ms") is not None:
            d["end_ms"] = fn(float(d["end_ms"]) / 1000.0, mapping) * 1000.0

    for seg in segments:
        _one(seg)
        for w in seg.get("words") or []:
            _one(w)


def _shift_or_remap(segments: list, vad_meta: Optional[Dict[str, Any]]) -> None:
    """Timestamps von verarbeiteter Achse zurück auf Original (nach Job/Align)."""
    if not vad_meta:
        return
    if vad_meta.get("type") == "shift":
        _shift_segments(segments, float(vad_meta.get("offset_s", 0.0)))
    elif vad_meta.get("type") == "map":
        _remap_segments(segments, vad_meta.get("mapping", []), inverse=False)


def _unshift_or_unmap(segments: list, vad_meta: Optional[Dict[str, Any]]) -> None:
    """Timestamps von Original auf die verarbeitete Achse (vor Align/Diar)."""
    if not vad_meta:
        return
    if vad_meta.get("type") == "shift":
        _shift_segments(segments, -float(vad_meta.get("offset_s", 0.0)))
    elif vad_meta.get("type") == "map":
        _remap_segments(segments, vad_meta.get("mapping", []), inverse=True)


def _run_diarization(audio_path: str, num_speakers: Optional[int] = None,
                     min_duration_off: Optional[float] = None,
                     method: Optional[str] = None,
                     on_progress: Optional[Callable[[int], None]] = None) -> list:
    from .diarize import diarize
    segs = diarize(audio_path, num_speakers=num_speakers,
                   min_duration_off=min_duration_off, method=method,
                   on_progress=on_progress)
    # Change 126: Qualitäts-Warnung — bei langem Audio (> 10 min) und nur
    # EINEM erkannten Speaker ist fast sicher das serverseitige Clustering
    # ausgefallen (Embedder fehlt → chunk-lokale Labels, alles fällt auf ein
    # Label). Kein stiller Fail: die Warnung macht den Zustand sichtbar.
    if segs:
        try:
            max_end = max(float(s.get("end") or 0.0) for s in segs)
        except (TypeError, ValueError):
            max_end = 0.0
        speakers = {s.get("speaker") for s in segs}
        if max_end > 600 and len(speakers) <= 1:
            log.warning(
                "Diarization lieferte nur 1 Speaker bei %.0f min Audio "
                "(%d Segmente) — Embedder/globales Clustering serverseitig "
                "prüfen (diarize_embedder)",
                max_end / 60, len(segs),
            )
    return segs


def _report_diar_progress(rec_id: int, pct: int) -> None:
    """Change 150: echter CrispASR-/progress-Wert (0..100) in die DB schreiben.

    Läuft im Poller-Thread → EIGENE Session (die Aufrufer-Session ist nicht
    thread-safe). Die Phase bleibt bei 96 (Heartbeat-Konvention), die NOTE
    trägt den echten Prozentwert („diarization 42%") für das Frontend.
    """
    try:
        with Session(engine) as s:
            # Change 151: pct ist phasen-lokal (0..100 der Diarization) —
            # der echte Server-/progress-Wert, kein globales Mapping.
            set_progress(s, rec_id, pct, note=f"diarization {pct}%")
    except Exception:
        log.exception("diar-progress: set_progress fehlgeschlagen (rec_id=%s)", rec_id)


def _word_overlap(w: Dict[str, Any], d_start: float, d_end: float) -> float:
    """Zeitliche Überlappung eines Worts mit einem Diarization-Segment.

    Positive Überlappung = Wort und Segment teilen sich Zeitfenster.
    0.0 = keine Überlappung (Wort komplett außerhalb).
    """
    w_start = w.get("start") if w.get("start") is not None else 0.0
    w_end = w.get("end") if w.get("end") is not None else w_start
    s = max(w_start, d_start)
    e = min(w_end, d_end)
    return max(0.0, e - s)


def _normalize_ts(value, unit: str = "s") -> Optional[float]:
    """Timestamp in Sekunden normalisieren (s/ms-Support)."""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v / 1000.0 if unit in ("ms", "milliseconds") else v


def _pick_ts(d: dict) -> tuple:
    """Liest start/end (Sekunden) oder start_ms/end_ms; (None, None) wenn fehlt."""
    s = _normalize_ts(d.get("start"), "s")
    if s is None:
        s = _normalize_ts(d.get("start_ms"), "ms")
    e = _normalize_ts(d.get("end"), "s")
    if e is None:
        e = _normalize_ts(d.get("end_ms"), "ms")
    return s, e


def _shift_segments(segments: list, offset_s: float) -> None:
    """Schiebt alle Segment-/Wort-Timestamps um offset_s Sekunden nach vorn.

    VAD-Trim-Kompensation: ASR/Aligner liefen auf dem getrimmten Audio, das
    Playback nutzt die Originaldatei → ohne Verschiebung spielt ein Klick
    auf ein Wort den Ton einer früheren Stelle ab. Behandelt start/end UND
    start_ms/end_ms. (2026-08-14)
    """
    def _shift_one(d: dict) -> None:
        if d.get("start") is not None:
            d["start"] = float(d["start"]) + offset_s
        elif d.get("start_ms") is not None:
            d["start_ms"] = float(d["start_ms"]) + offset_s * 1000.0
        if d.get("end") is not None:
            d["end"] = float(d["end"]) + offset_s
        elif d.get("end_ms") is not None:
            d["end_ms"] = float(d["end_ms"]) + offset_s * 1000.0

    for seg in segments:
        _shift_one(seg)
        for w in seg.get("words") or []:
            _shift_one(w)


def dedupe_repeated_word_runs(segments: list, text: Optional[str] = None,
                              min_run: int = 2,
                              time_tol_s: float = 1.0,
                              duration_anomaly_s: float = 2.5) -> tuple:
    """Entfernt Chunk-Overlap-Dopplungen präventiv aus ASR-Segmenten.

    Change 161 (2026-08-30): ps-pk-onnx verarbeitet lange Audios in
    120-s-Chunks; an Chunk-Grenzen wird dieselbe Wortfolge doppelt
    transkribiert. Live-Befund Recording 8976aa1b (8:40): „Im anliegenden
    Ort Im anliegenden Ort erzählt man sich…" — die erste Kopie hat Zeiten
    in der Stille (kein akustisches Signal), die zweite die echten Zeiten.
    Bisher wurde der doppelte Text 1:1 übernommen und erst post-hoc
    repariert; dieser Fix stoppt die Entstehung an der Eingangsstufe.

    Erkennung (deterministisch, auf dem globalen Wort-Stream):
    - zwei DIREKT aufeinanderfolgende Wortfolgen mit identischem Text
      (n >= min_run Wörter)
    - (1) zeitlicher Chunk-Overlap: die zweite Kopie beginnt innerhalb der
      ersten oder unmittelbar danach (start_2 < end_1 + time_tol_s) —
      echte rhetorische Wiederholungen sind zeitlich getrennt und bleiben
      erhalten
    - (2) Change 167 — Dauer-Signatur aus dem Parakeet-Alignment: genau
      EINE Kopie enthält ein Wort mit Dauer > duration_anomaly_s (Default
      2,5 s). Echte Sprache hat Wort-Dauern von ~0,3–0,9 s; ein 3–6-s-Wort
      ist die Stille-Halluzination am Chunk-Rand (der Decoder streckt die
      Wörter über die Lücke). Die gestreckte Kopie wird entfernt —
      unabhängig davon, ob sie die erste oder zweite ist. Echte
      rhetorische Wiederholungen haben in beiden Kopien normale Dauern →
      unberührt.
    - ohne Wort-Zeiten (Fallback): identische benachbarte Folge mit
      n >= 3 (Sicherheitsmarge gegen „ja ja"-Fälle)

    Entfernt wird die Overlap-/Stille-Kopie (Wörter + Segment-Text); der
    Gesamttext wird aus den Segment-Texten neu gebaut.

    Returns: (segments, text) — bereinigte Listen; unverändert, wenn keine
    Dopplung gefunden wurde.
    """
    # Globaler Wort-Stream mit Segment-/Wort-Referenz: (word, start, end, seg_idx, word_key)
    stream: List[tuple] = []
    for si, seg in enumerate(segments):
        seg_words = seg.get("words") or []
        if seg_words:
            for wi, w in enumerate(seg_words):
                ws, we = _pick_ts(w)
                stream.append((str(w.get("word") or ""), ws, we, si, ("w", wi)))
        else:
            for wi, w in enumerate((seg.get("text") or "").split()):
                stream.append((w, None, None, si, ("t", wi)))
    if len(stream) < min_run * 2:
        return segments, text if text is not None else " ".join(
            (s.get("text") or "").strip() for s in segments
        ).strip()

    removed: set = set()  # seg_idx → Wort-Keys der ZU ENTFERNENDEN Kopie
    i = 0
    while i < len(stream) - min_run:
        n = 0
        remove_second = True  # Change 167: bei Dauer-Signatur auch Kopie 1 möglich
        max_cand = min(30, (len(stream) - i) // 2)
        for cand in range(max_cand, min_run - 1, -1):
            a = [w[0] for w in stream[i:i + cand]]
            b = [w[0] for w in stream[i + cand:i + 2 * cand]]
            if a != b:
                continue
            # Zeit-Check nur wenn BEIDE Folgen durchgehend Zeiten haben
            ts_a = [w[2] for w in stream[i:i + cand]]
            ts_b = [w[1] for w in stream[i + cand:i + 2 * cand]]
            if all(t is not None for t in ts_a) and all(t is not None for t in ts_b):
                # (1) Chunk-Overlap: zweite Kopie beginnt innerhalb/nach Ende
                # der ersten
                if ts_b[0] < ts_a[-1] + time_tol_s:
                    n = cand
                    remove_second = True
                    break
                # (2) Change 167: Dauer-Signatur — genau EINE Kopie enthält
                # ein Wort mit unnatürlich langer Dauer (Stille-Halluzination
                # am Chunk-Rand, Wörter über die Lücke gestreckt). Die
                # gestreckte Kopie fällt — egal ob erste oder zweite.
                durs_a = [w[2] - w[1] for w in stream[i:i + cand]]
                durs_b = [w[2] - w[1] for w in stream[i + cand:i + 2 * cand]]
                anom_a = max(durs_a) > duration_anomaly_s
                anom_b = max(durs_b) > duration_anomaly_s
                if anom_a != anom_b:
                    n = cand
                    remove_second = anom_b
                    break
            elif cand >= 3:
                # Fallback ohne verwertbare Zeiten (Sicherheitsmarge)
                n = cand
                remove_second = True
                break
        if n:
            if remove_second:
                for w in stream[i + n:i + 2 * n]:
                    removed.add((w[3], w[4]))
            else:
                for w in stream[i:i + n]:
                    removed.add((w[3], w[4]))
            i += n  # behaltene Kopie überspringen, dahinter weitersuchen
        else:
            i += 1

    if not removed:
        return segments, text

    # Segmente neu bauen: Wörter der zweiten Kopie entfernen, Text = join(words)
    by_seg: dict = {}
    for si, key in removed:
        by_seg.setdefault(si, set()).add(key)
    out: List[dict] = []
    for si, seg in enumerate(segments):
        ns = dict(seg)
        keys = by_seg.get(si)
        seg_words = seg.get("words") or []
        if seg_words:
            kept = [w for wi, w in enumerate(seg_words) if keys is None or ("w", wi) not in keys]
            ns["words"] = kept
            ns["text"] = " ".join(str(w.get("word") or "") for w in kept)
        else:
            kept = [w for wi, w in enumerate((seg.get("text") or "").split())
                    if keys is None or ("t", wi) not in keys]
            ns["text"] = " ".join(kept)
        out.append(ns)
    text = " ".join((s.get("text") or "").strip() for s in out).strip()
    log.warning(
        "Change 161: Chunk-Overlap-Dopplung entfernt (rec=%d segs=%d wortpaare=%d)",
        -1, len(out), len(removed),
    )
    return out, text


def _build_word_stream(segments: list, total_duration: Optional[float]) -> Optional[list]:
    """Einheitlicher Wort-Stream [{word,start,end}] in Sekunden.

    Kaskade: (1) vorhandene Wort-TS, (2) Uniform-Verteilung pro Segment
    (gleiche Formel wie asr_client._parse_result — siehe dort Zeile ~133),
    (3) keine Zeitinformation → None (kein Text-Mapping möglich).
    """
    words: List[Dict[str, Any]] = []
    any_ts = False
    for seg in segments:
        s, e = _pick_ts(seg)
        if s is not None and e is not None:
            any_ts = True
        seg_words = seg.get("words") or []
        if seg_words and all(_pick_ts(w)[0] is not None for w in seg_words):
            for w in seg_words:
                ws, we = _pick_ts(w)
                words.append({"word": w.get("word", ""), "start": ws, "end": we})
        else:
            # Uniform-Verteilung des Segment-Texts (Fallback wie _parse_result)
            text_words = (seg.get("text") or "").split()
            dur = max((e or 0) - (s or 0), 0.1)
            w_dur = dur / max(len(text_words), 1)
            for i, w in enumerate(text_words):
                words.append({"word": w, "start": (s or 0) + i * w_dur,
                              "end": (s or 0) + (i + 1) * w_dur})
            if s is not None:
                any_ts = True
    words = [w for w in words if w.get("start") is not None]
    words.sort(key=lambda w: w.get("start") or 0)
    return words if (words and any_ts) else None


def _merge_diarization(segments: list, diar: list,
                       word_stream: Optional[list] = None,
                       total_duration: Optional[float] = None,
                       full_text: Optional[str] = None) -> list:
    """Ersetzt die ASR-Segmentierung durch die Diarization-Segmentierung.

    Jedes Diarization-Segment (start/end/speaker) wird ein Anzeige-Segment;
    der Text pro Segment wird aus den Wort-Zeitstempeln der ASR-Segmente
    zusammengesetzt. Segmente ohne zugehörige Wörter (Pausen) entfallen.

    Flicker-Schutz: pyannote liefert oft viele winzige Segmente mit demselben
    Sprecher (nur wenige 100 ms auseinander). Diese werden zu einem Segment
    zusammengefasst, damit Wörter nicht einzeln in Spalten zerhauen werden
    (Karaoke-Bug). Echte Sprecherwechsel bleiben erhalten.

    Wort-Zuordnung (Overlap statt strikter start-Fenster): Ein Wort gehört zu
    dem Segment, mit dem es die GRÖSSTE zeitliche Überlappung hat. Bei
    Gleichstand gewinnt das spätere Segment (der neue Sprecher). Wörter ohne
    jede Überlappung (Lücken) gehen ans nächste Segment mit start >= w.end.
    Das behebt den Bug, dass das erste Wort eines neuen Sprechers (beginnt
    minimal vor der pyannote-Grenze) dem letzten Segment des VORIGEN
    Sprechers zugeordnet wurde.

    ``word_stream`` (optional): vorbereiteter Wort-Stream in Sekunden — wenn
    None, wird er aus ``segments`` gebaut (Backend-Agnostik). Liefert auch
    das gar keine Zeitinformation, wird ``full_text`` PROPORTIONAL zur
    Segmentdauer aufgeteilt und als ``estimated`` markiert (Status B) —
    damit gibt es immer eine Speaker-Aufteilung.
    """
    # Wort-Stream ermitteln: explizit übergeben oder aus segments bauen.
    if word_stream is None:
        word_stream = _build_word_stream(segments, total_duration)

    # Status B — gar keine Timestamps: proportional aufteilen (geschätzt)
    if not word_stream:
        if not full_text:
            return []
        words_all = full_text.split()
        total_dur = float(total_duration or 1.0)
        out: List[Dict[str, Any]] = []
        w_idx = 0
        for d in sorted(diar, key=lambda x: x.get("start") or 0):
            d_start = d.get("start", 0)
            d_end = d.get("end", d_start)
            dur = max(d_end - d_start, 0.0)
            n = int(round(len(words_all) * dur / total_dur))
            chunk = words_all[w_idx:w_idx + n]
            w_idx += n
            if not chunk:
                continue
            out.append({
                "start": round(d_start, 2),
                "end": round(d_end, 2),
                "text": " ".join(chunk),
                "words": [{"word": w} for w in chunk],
                "speaker": d.get("speaker", "SPEAKER_00"),
                "estimated": True,
            })
        return out

    # Alle Wörter aus dem Stream (bereits in Sekunden normalisiert)
    words = sorted(word_stream, key=lambda w: w.get("start") or 0)

    # Flicker-Segmente desselben Sprechers zusammenfassen (Lücke < 0.5 s)
    _FLICKER_GAP_S = 0.5
    smoothed: List[Dict[str, Any]] = []
    for d in sorted(diar, key=lambda x: x.get("start") or 0):
        if smoothed and d.get("speaker") == smoothed[-1]["speaker"]:
            gap = (d.get("start") or 0) - smoothed[-1]["end"]
            if -0.05 <= gap < _FLICKER_GAP_S:
                smoothed[-1]["end"] = max(smoothed[-1]["end"], d.get("end") or 0)
                continue
        smoothed.append(dict(d))

    # Wort→Segment-Zuordnung per Overlap: jedes Wort gehört zum Segment mit
    # der größten zeitlichen Überlappung. Gleichstand → späteres Segment.
    # Kein Overlap (Lücke) → nächstes Segment mit start >= w.end.
    by_seg: List[List[Dict[str, Any]]] = [[] for _ in smoothed]
    for w in words:
        w_start = w.get("start") if w.get("start") is not None else 0.0
        w_end = w.get("end") if w.get("end") is not None else w_start
        best_i, best_ov = -1, 0.0
        for i, d in enumerate(smoothed):
            d_start = d.get("start", 0)
            d_end = d.get("end", d_start)
            ov = _word_overlap(w, d_start, d_end)
            if ov > best_ov or (ov == best_ov and best_i != -1 and i > best_i):
                best_ov, best_i = ov, i
        if best_i >= 0 and best_ov > 0:
            by_seg[best_i].append(w)
        else:
            # Lücke: nächstes Segment, das nach dem Wortende beginnt
            nxt = next(
                (i for i, d in enumerate(smoothed)
                 if (d.get("start") or 0) >= w_end),
                None,
            )
            if nxt is not None:
                by_seg[nxt].append(w)

    merged: List[Dict[str, Any]] = []
    for i, d in enumerate(smoothed):
        seg_words = by_seg[i]
        if not seg_words:
            continue  # Pause ohne Sprache — kein leeres Segment
        d_start = d.get("start", 0)
        d_end = d.get("end", d_start)
        text = " ".join(w.get("word", "") for w in seg_words).strip()
        merged.append({
            "start": round(d_start, 2),
            "end": round(d_end, 2),
            "text": text,
            "words": seg_words,
            "speaker": d.get("speaker", "SPEAKER_00"),
        })

    # Härtung (2026-08-15): Wörter, die in KEIN Diarization-Segment fielen
    # (Service deckte nur einen Teil ab / Lücken im Mapping), hängen am
    # letzten Segment an — sonst verschwindet Transkriptions-Text aus der
    # Segment-Liste (Karaoke/Anzeige), obwohl der Gesamttext vollständig ist.
    if words and merged:
        mapped_ids = {id(w) for seg_words in by_seg for w in seg_words}
        leftover = [w for w in words if id(w) not in mapped_ids]
        if leftover:
            last = merged[-1]
            last["end"] = round(max(
                (w.get("end") or w.get("start") or 0) for w in leftover
            ), 2)
            last["text"] = (last.get("text") or "") + " " + " ".join(
                w.get("word", "") for w in leftover
            )
            last["words"] = (last.get("words") or []) + leftover
    return merged


def _compute_peaks(audio_bytes: bytes) -> list:
    from .peaks import compute_peaks
    return compute_peaks(audio_bytes)


def _compute_peaks_path(path) -> list:
    """Peaks direkt von der Datei (ffmpeg liest -i <pfad> statt pipe:0).

    Für große Audiodateien — die Bytes-Variante lädt das komplette Audio in
    den RAM und blockiert beim stdin.write (Deadlock, OOM-Kill bei 357-MB-
    Files, s. peaks.compute_peaks_path). Der Background-Thread (schedule_
    peaks) nutzt deshalb den Pfad-Weg.
    """
    from .peaks import compute_peaks_path
    return compute_peaks_path(path)

# Change 114: VAD ist User-Option (vad_mode im Run) — kein Env-Gate mehr.
# Früher: _VAD_TRIM = os.getenv("VAD_TRIM_SILENCE", "false") blockierte VAD
# ohne Env-Variable; die Bedingungen hießen `if _VAD_TRIM and …`.
_ENHANCE_LEVEL = os.getenv("ENHANCE_LEVEL", "off")  # off, light, medium, aggressive

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Audio enhancement pre-processing
# ---------------------------------------------------------------------------


def enhance_audio(audio_bytes: bytes, level: str = "light") -> bytes:
    """Apply ffmpeg audio filters to improve ASR accuracy.

    All filters run on a 16 kHz mono WAV stream regardless of input format.
    Returns enhanced WAV bytes (or original if level is ``"off"``).

    Levels:
    - ``light``:     highpass + lowpass bandpass (speech range)
    - ``medium``:    bandpass + mild afftdn (adaptive denoising) + loudnorm
    - ``aggressive``: bandpass + strong afftdn + loudnorm + compand
    """
    if level == "off":
        return audio_bytes

    filters: Dict[str, str] = {
        "light": (
            "highpass=f=80,lowpass=f=4000"
        ),
        "medium": (
            "highpass=f=80,lowpass=f=4000,"
            "afftdn=nr=12:nt=w,"
            "loudnorm=I=-16:TP=-1.5:LRA=11"
        ),
        "aggressive": (
            "highpass=f=80,lowpass=f=4000,"
            "afftdn=nr=25:nt=w,"
            "loudnorm=I=-16:TP=-1.5:LRA=11,"
            "compand=attacks=0.01:decays=0.05:"
            "points=-80,-80|-30,-15|-10,-1|0,0|20,20:"
            "gain=2:volume=on"
        ),
    }

    chain = filters.get(level)
    if not chain:
        log.warning("enhance_audio: unknown level %r, falling back to light", level)
        chain = filters["light"]

    try:
        proc = sp.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-i", "pipe:0",          # read from stdin
                "-af", chain,
                "-ar", "16000",          # 16 kHz
                "-ac", "1",              # mono
                "-f", "wav",             # WAV output
                "pipe:1",                # write to stdout
            ],
            input=audio_bytes,
            capture_output=True,
            timeout=120,
        )
    except sp.TimeoutExpired:
        log.warning("enhance_audio: ffmpeg timed out after 120s, returning original")
        return audio_bytes
    except FileNotFoundError:
        log.warning("enhance_audio: ffmpeg not found, returning original")
        return audio_bytes

    if proc.returncode != 0:
        log.warning("enhance_audio: ffmpeg exit=%d, returning original; stderr=%s",
                     proc.returncode, proc.stderr[:200].decode(errors="replace"))
        return audio_bytes

    enhanced = proc.stdout
    if not enhanced:
        log.warning("enhance_audio: ffmpeg produced no output, returning original")
        return audio_bytes

    return enhanced


# ---------------------------------------------------------------------------
# Background processing
# ---------------------------------------------------------------------------


def run_punctuation(text: str, mode: str) -> str:
    """Interpunktion (Task A12) — LLM-Backend via LiteLLM-Proxy (paid) oder
    offline fullstop (local). ``off`` → unverändert.

    Der LLM-Call läuft über den bestehenden OpenAI-kompatiblen Endpunkt
    (``llm.chat``) — keine neuen Downloads. Bei Fehlern (kein Endpunkt,
    Timeout, API-Error) wird der Text UNVERÄNDERT zurückgegeben (nie crashen
    einer Aufnahme wegen optionaler Post-Processing).
    """
    if mode in (None, "", "off"):
        return text
    if mode == "local":
        # Offline fullstop-Punctuator ist nicht Teil der Webapp (Mem-Limit) —
        # optionaler Compose-Service (Profil "punct", siehe Plan Task 3).
        log.warning("run_punctuation: mode 'local' nicht verfügbar — Text unverändert")
        return text
    if mode != "llm":
        log.warning("run_punctuation: unbekannter Modus %r — Text unverändert", mode)
        return text

    # LLM-Modus: deutschen Prompt über den konfigurierten Endpunkt.
    try:
        from . import llm as llm_mod

        result = llm_mod.chat(
            "Du bist ein deutscher Transkriptions-Postprozessor. "
            "Setze Satzzeichen und Großschreibung in den deutschen Text ein. "
            "Ändere KEINE Wörter und füge nichts hinzu.",
            text,
            max_tokens=4000,
        )
        result = (result or "").strip()
        return result if result else text
    except Exception as exc:
        log.warning("run_punctuation: LLM-Call fehlgeschlagen (%s) — Text unverändert", exc)
        return text


def run_llm_enhance(text: str, segments: List[Dict[str, Any]]):
    """LLM-Optimierung (Task A13) — Korrekturen über den LiteLLM-Endpunkt.

    Verbessert den Gesamttext (Rechtschreibung, Floskeln, falsche Wörter),
    ohne Segment-/Wort-Struktur zu brechen: Der optimierte Text wird
    proportional auf die bestehenden Segmente verteilt (Wort-Zahl bleibt
    möglichst stabil, Timestamps bleiben unangetastet — Karaoke-fähig).

    Bei Fehlern oder fehlender Konfiguration: unverändert zurückgeben
    (nie crashen einer Aufnahme wegen optionaler Post-Processing).
    """
    if not text:
        return text, segments
    try:
        from . import llm as llm_mod

        result = llm_mod.chat(
            "Du bist ein deutscher Transkriptions-Korrektor. Verbessere "
            "Rechtschreibfehler und Floskeln im Transkript. Ändere den Inhalt "
            "nicht, füge nichts hinzu, antworte nur mit dem korrigierten Text.",
            text,
            max_tokens=8000,
        )
        result = (result or "").strip()
        if not result:
            return text, segments
    except Exception as exc:
        log.warning("run_llm_enhance: LLM-Call fehlgeschlagen (%s) — unverändert", exc)
        return text, segments

    # Optimierten Text proportional auf die bestehenden Segmente verteilen:
    # jedes Segment bekommt Wörter im Verhältnis seiner bisherigen Wortzahl.
    if not segments:
        return result, segments
    old_words = sum(len((s.get("text") or "").split()) for s in segments)
    if old_words <= 0:
        return result, segments
    new_words = result.split()
    out: List[Dict[str, Any]] = []
    w_idx = 0
    for s in segments:
        n_old = max(len((s.get("text") or "").split()), 1)
        n_new = max(int(round(len(new_words) * n_old / old_words)), 1)
        chunk = new_words[w_idx:w_idx + n_new]
        w_idx += n_new
        ns = dict(s)
        ns["text"] = " ".join(chunk)
        out.append(ns)
    # Rest (Rundungsdifferenz) ans letzte Segment anhängen
    if w_idx < len(new_words):
        out[-1]["text"] = (out[-1]["text"] + " " + " ".join(new_words[w_idx:])).strip()
    return " ".join(ns["text"] for ns in out), out


# ============================================================
# Forced Alignment (Karaoke-Word-Sync) — optionaler Post-Schritt
# ============================================================
# Change 078 (2026-08-21): 380 → 120 s. Gemessen an einer historischen
# Aufnahme (234 s, User-Befund 68026-moissi-hamlet): bei 227-s-Einzel-
# Request nur 30 % Wort-Abdeckung (Aligner komprimiert die Zuordnung),
# bei 80-s-Chunks 99,8 %. 120 s = ASR-Chunk-Länge, guter Kompromiss.
MAX_ALIGN_GROUP_S = 120.0  # Sicherheitsmarge unter dem 400-s-Modell-Limit


def _split_long_segment(
    seg: Dict[str, Any], max_s: float = MAX_ALIGN_GROUP_S
) -> List[tuple]:
    """Change 078: Ein EINZELNES Segment länger als max_s in Zeit-Chunks teilen.

    User-Vorgabe (2026-08-21): GUI-Segmente und Align-Chunks sind
    entkoppelt — der Aligner bekommt technisch optimierte Chunks (Text
    proportional mitschneiden), die Wort-Timestamps werden danach über
    apply_aligned_words wieder den ORIGINAL-Segmenten zugeordnet.

    Text-Aufteilung: die Wortfolge (seg.words-Reihenfolge bzw.
    seg.text.split()) gleichmäßig über die Chunks — NICHT anhand der
    alten Wortzeiten (die sind bei langen Aufnahmen das Problem).
    """
    start = float(seg.get("start") or 0.0)
    end = float(seg.get("end") or start)
    dur = end - start
    if dur <= max_s:
        return [(start, end, seg.get("text") or "")]
    n = max(2, math.ceil(dur / max_s))
    # Wortfolge: bevorzugt seg.words (Reihenfolge = Textfolge), sonst Text-Wörter.
    raw_words = seg.get("words") or []
    if raw_words:
        words = [str(w.get("word") or "") for w in raw_words]
    else:
        words = (seg.get("text") or "").split()
    chunk_dur = dur / n
    out: List[tuple] = []
    for c in range(n):
        c_start = start + c * chunk_dur
        c_end = start + (c + 1) * chunk_dur if c + 1 < n else end
        lo = round(len(words) * c / n)
        hi = round(len(words) * (c + 1) / n)
        out.append((c_start, c_end, " ".join(words[lo:hi])))
    return out


def build_align_groups(segments: List[Dict[str, Any]], max_s: float = MAX_ALIGN_GROUP_S) -> List[tuple]:
    """Bündelt aufeinanderfolgende Segmente zu Align-Gruppen ≤ max_s.

    Returns: Liste von (start, end, text) in globalen Sekunden. Lücken
    (Pausen) zwischen Segmenten zählen zur Spanne — der Audio-Ausschnitt
    enthält sie, der Aligner verteilt die Wörter korrekt darüber.
    Change 078: Einzelne Segmente LÄNGER als max_s werden intern in
    gleich große Chunks geteilt (_split_long_segment) — die Align-
    Gruppen sind dann kleiner als das GUI-Segment; die Wörter landen
    über apply_aligned_words trotzdem wieder im Original-Segment.
    """
    groups: List[tuple] = []
    cur: Optional[list] = None
    for s in segments:
        start, end = s.get("start"), s.get("end")
        if start is None or end is None:
            continue
        # Change 078: langes Einzel-Segment → technische Chunks.
        if (float(end) - float(start)) > max_s:
            if cur is not None:
                groups.append((cur[0], cur[1], " ".join(cur[2])))
                cur = None
            groups.extend(_split_long_segment(s, max_s))
            continue
        if cur is None:
            cur = [start, end, [s.get("text") or ""]]
        else:
            span = max(cur[1], end) - cur[0]
            if span > max_s:
                groups.append((cur[0], cur[1], " ".join(cur[2])))
                cur = [start, end, [s.get("text") or ""]]
            else:
                cur[1] = max(cur[1], end)
                cur[2].append(s.get("text") or "")
    if cur is not None:
        groups.append((cur[0], cur[1], " ".join(cur[2])))
    return groups


def apply_aligned_words(segments: List[Dict[str, Any]], words: List[Dict[str, Any]],
                        group_start: float) -> List[Dict[str, Any]]:
    """Weist alignierte Wörter (relativ zu group_start) den Segmenten zu.

    Ein Wort gehört zum Segment, in dessen Zeitbereich sein Start fällt.
    Nur Segmente mit Treffern bekommen words — Segmente ohne Treffer
    behalten ihre Backend-Timestamps.
    """
    by_time = sorted(words, key=lambda w: w.get("start") or 0.0)
    # Change 152 (User-Befund 2026-08-28): Der Aligner liefert für die
    # meisten Wörter end=start (Dauer 0) oder unplausibel kurze Werte
    # (≤ 50 ms) — dadurch wird das Wort auf der Timeline nie markiert.
    # Dauer aus dem Start des Folgeworts ableiten — aber NIE über eine
    # Stille-Lücke hinweg: nur wenn die Lücke klein ist (≤ 0.5 s), wird
    # sie als Wortdauer übernommen; bei langer Stille (Satz-Ende) endet
    # das Wort nach einer harten Maximaldauer von 1 s. Das letzte Wort
    # der Datei bekommt ebenfalls diese Maximaldauer.
    cap = 1.0
    for i in range(len(by_time) - 1):
        w = by_time[i]
        ws = float(w.get("start") or 0.0)
        we = float(w.get("end") or ws)
        if we - ws <= 0.05:
            nxt = float(by_time[i + 1].get("start") or ws)
            if nxt - ws <= 0.5:
                by_time[i] = {**w, "end": nxt}
            else:
                by_time[i] = {**w, "end": ws + cap}
    if by_time:
        w = by_time[-1]
        ws = float(w.get("start") or 0.0)
        we = float(w.get("end") or ws)
        if we - ws <= 0.05:
            by_time[-1] = {**w, "end": ws + cap}
    out: List[Dict[str, Any]] = []
    wi = 0
    for s in segments:
        ns = dict(s)
        s0, s1 = s.get("start", 0.0), s.get("end")
        seg_words: List[Dict[str, Any]] = []
        for w in by_time[wi:]:
            ws = (w.get("start") or 0.0) + group_start
            we = (w.get("end") or ws) + group_start
            if s1 is not None and ws >= s1:
                break
            if ws >= s0 - 1e-3:
                item: Dict[str, Any] = {"word": w.get("word") or "", "start": ws, "end": we}
                if w.get("confidence") is not None:
                    item["confidence"] = w.get("confidence")
                seg_words.append(item)
        if seg_words:
            ns["words"] = seg_words
        out.append(ns)
        wi += len(seg_words)
    return out


def restore_override_words(
    old_segments: List[Dict[str, Any]],
    new_segments: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Change 137: Manuell korrigierte Wort-Timings (override=true) nach
    einem Align-Lauf wiederherstellen.

    Der Forced-Aligner ersetzt ALLE Word-Timestamps (apply_aligned_words).
    Wörter, die der User im Timing-Tab manuell korrigiert hat (override),
    behalten ihre ``start``/``end`` — der Override-Schutz (User-Entscheid
    2026-08-28). Zuordnung per Index je Segment: der alignte Text entspricht
    dem Segment-Text (Overrides ändern den Text nicht). Weicht die Wortzahl
    ab (Text wurde geändert), wird der Override verworfen. Wo ein Override
    wiederhergestellt wurde, folgen die Segment-Grenzen wieder dem ersten/
    letzten Wort (ein korrigiertes Rand-Wort ändert die Grenzen mit).
    """
    out: List[Dict[str, Any]] = []
    for i, ns in enumerate(new_segments):
        ns = dict(ns)
        if i < len(old_segments):
            old_words = old_segments[i].get("words") or []
            new_words = ns.get("words") or []
            if old_words and len(old_words) == len(new_words):
                restored = False
                for j, ow in enumerate(old_words):
                    if ow.get("override"):
                        new_words[j] = {
                            **new_words[j],
                            "start": float(ow["start"]),
                            "end": float(ow["end"]),
                            "override": True,
                        }
                        restored = True
                if restored:
                    ns["words"] = new_words
                    ns["start"] = float(new_words[0]["start"])
                    ns["end"] = float(new_words[-1]["end"])
        out.append(ns)
    return out


def _run_align_phase(rec_id: int, segments: List[Dict[str, Any]], audio_bytes: bytes,
                     audio_name: str, language: Optional[str], job=None,
                     background: bool = False) -> List[Dict[str, Any]]:
    """Forced-Alignment-Phase: ersetzt Word-Timestamps durch akustisch
    verifizierte Grenzen (crispr-align). Failt der Aligner (Container down,
    Chunk > 400 s), bleiben die Backend-Timestamps — nie ein Job-Fail.

    Live-Feedback (2026-08-15): Jeder align()-Call blockiert bis zu 15 min
    (ein ggml-Forward-Pass). Ohne Zwischen-Updates zeigt die UI stundenlang
    „96 %, ETA 1 s" — Fake-Progress. Deshalb läuft während jedes Calls ein
    Heartbeat-Thread, der /status des Aligners pollt (alle 3 s) und echte
    Lebenszeichen schreibt: „alignment 3/12 — aktiv seit 42 s" + ggml-%
    (falls die CLI es ausgibt). Nie erfundene Werte: ohne Status-Infos
    bleibt die letzte echte Gruppe stehen.

    ``background`` (Change 045): True = Worker-Lauf nach „done" — KEINE
    progress_pct-Schreibzugriffe (der Job ist fertig, 96 % wäre Fake) und
    kein Heartbeat auf progress. Der Worker pflegt stattdessen das
    ``alignment``-Feld des Recordings.
    """
    from .aligner_client import AlignerClient
    from .models import Recording as _Rec

    client = AlignerClient()
    if not client.health():
        log.info("align: crispr-align nicht erreichbar (rec_id=%s) — Backend-Timestamps behalten", rec_id)
        return segments

    if not background:
        with Session(engine) as session:
            set_progress(session, rec_id, 0, note="alignment")

    tmp_audio = ""
    aligned_any = False
    # Change 078: alignierte Wörter ALLER Gruppen global sammeln (mit
    # Gruppen-Offset) und NACH der Schleife einmal zuordnen. Grund: Ein
    # in mehrere Chunks geteiltes Segment bekommt Wörter aus MEHREREN
    # Gruppen — die alte Pro-Gruppe-Anwendung (apply_aligned_words je
    # Gruppe) hätte die words des Segments mit der letzten Gruppe
    # überschrieben.
    all_aligned_words: List[Dict[str, Any]] = []
    try:
        # Zeitbasis: die VERARBEITETE Audio (nach VAD-Trim/Enhance/Konvertierung)
        # — die Segment-Zeiten beziehen sich auf sie.
        with tempfile.NamedTemporaryFile(suffix=Path(audio_name).suffix or ".bin", delete=False) as tfh:
            tmp_audio = tfh.name
            tfh.write(audio_bytes)

        _t_align0 = time.perf_counter()
        groups = build_align_groups(segments)
        for gi, (g_start, g_end, g_text) in enumerate(groups):
            # Change 124: BG-Align (job=None) ist gegen _cancelled immun —
            # zusätzlich die Cancel-Registry prüfen. Kein _abort_recording:
            # der Job ist längst done, nur die Align-Ergebnisse entfallen.
            if background and _align_cancelled(rec_id):
                log.info("bg-align: Cancel für rec_id=%s — Ergebnis verworfen", rec_id)
                return segments
            # Cancel/Timeout zwischen den Gruppen prüfen — nicht erst nach
            # dem letzten align()-Call (der bis zu 15 min blockieren kann).
            if _cancelled(job, rec_id):
                _abort_recording(rec_id, "Abgebrochen (User-Cancel)")
                return segments
            try:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tfh2:
                    chunk_wav = tfh2.name
                sp.run(
                    ["ffmpeg", "-y", "-v", "error", "-ss", f"{g_start:.3f}",
                     "-to", f"{g_end:.3f}", "-i", tmp_audio,
                     "-ar", "16000", "-ac", "1", "-f", "wav", chunk_wav],
                    check=True, capture_output=True, timeout=120,
                )
                try:
                    with open(chunk_wav, "rb") as fh:
                        chunk_bytes = fh.read()
                finally:
                    os.unlink(chunk_wav)

                # ---- Heartbeat-Poller für DIESEN align()-Call ----
                # align() blockiert; der Thread meldet echte Lebenszeichen
                # vom Aligner (/status) an die DB → UI zeigt Live-Fortschritt.
                # (background=True: kein progress-Schreiben — Job ist done.)
                stop = threading.Event()

                def _heartbeat():
                    while not stop.is_set():
                        st = client.status()
                        if st.get("active"):
                            elapsed = st.get("elapsed_s")
                            pct = st.get("progress_pct")
                            last = (st.get("last_line") or "").strip()
                            parts = [f"Gruppe {gi + 1}/{len(groups)}"]
                            if elapsed is not None:
                                parts.append(f"aktiv seit {int(elapsed)}s")
                            if pct is not None:
                                parts.append(f"CLI {pct}%")
                            if last:
                                parts.append(f"· {last[:60]}")
                            note = "alignment " + " — ".join(parts)
                            if background:
                                with Session(engine) as s2:
                                    rec_b = s2.get(_Rec, rec_id)
                                    if rec_b is not None:
                                        rec_b.alignment = "running"
                                        rec_b.progress_note = None
                                        s2.add(rec_b)
                                        s2.commit()
                            else:
                                with Session(engine) as s2:
                                    set_progress(
                                        s2, rec_id,
                                        int((gi + 1) / len(groups) * 100),  # Change 151
                                        note=note,
                                    )
                        stop.wait(3.0)

                hb = threading.Thread(target=_heartbeat, daemon=True, name=f"align-hb-{gi}")  # thread:ok Aligner-Status-Poller (Zweck)
                hb.start()
                try:
                    # Rest-Budget: verbleibende Job-Zeit — ein hängender
                    # align()-Call bricht spätestens hier ab (Queue frei).
                    budget = 900.0
                    if job is not None:
                        max_s = getattr(job, "_max_processing_s", None)
                        if max_s:
                            budget = max(30.0, min(900.0, max_s - job.running_s))
                    words = client.align(chunk_bytes, g_text, lang=language or "de",
                                         timeout_s=budget)
                except RuntimeError as exc_rt:
                    # Cancel/Timeout: nicht als Gruppenfehler schlucken,
                    # sondern den Job sauber beenden (Queue freigeben).
                    if _cancelled(job, rec_id):
                        _abort_recording(rec_id, "Abgebrochen (User-Cancel)")
                        return segments
                    raise
                finally:
                    stop.set()
                    hb.join(timeout=1.0)

                if words:
                    # Change 078: Wörter GLOBAL sammeln (Offset + g_start),
                    # nicht pro Gruppe anwenden — ein in mehrere Chunks
                    # geteiltes Segment bekommt Wörter aus MEHREREN
                    # Gruppen; die Zuordnung passiert NACH der Schleife
                    # einmal über apply_aligned_words(…, group_start=0).
                    for w in words:
                        item = dict(w)
                        ws = float(item.get("start") or 0.0) + g_start
                        we = float(item.get("end") or ws) + g_start
                        item["start"], item["end"] = ws, we
                        all_aligned_words.append(item)
                    aligned_any = True
                    log.info("align: rec_id=%s Gruppe %d/%d (%ds–%ds) → %d Wörter",
                             rec_id, gi + 1, len(groups), g_start, g_end, len(words))
                # Echter Gruppenfortschritt (96–99): die Phase kann bei langen
                # Audios 10–25 min dauern — kein starrer 96-Hinweis. Der note
                # traegt den Gruppen-Zaehler, die UI zeigt "Alignment…".
                # (background=True: Job ist done — kein progress-Schreiben.)
                if not background:
                    with Session(engine) as session:
                        set_progress(
                            session, rec_id,
                            96 + int((gi + 1) / len(groups) * 3.99),
                            note=f"alignment {gi + 1}/{len(groups)}",
                        )
            except Exception as exc_g:
                log.warning("align: Gruppe %d/%d übersprungen (rec_id=%s): %s",
                            gi + 1, len(groups), rec_id, exc_g)
    except Exception as exc_a:
        log.warning("align: Phase übersprungen (rec_id=%s): %s", rec_id, exc_a)
    finally:
        if tmp_audio and os.path.exists(tmp_audio):
            os.unlink(tmp_audio)
        if not background:
            with Session(engine) as session:
                rec2 = session.get(_Rec, rec_id)
                if rec2 is not None:
                    # Loop-Max ist 99 — kein Rueckwaerts-Sprung auf 97 (die UI
                    # wuerde sonst minutenlang auf 97% stehenbleiben).
                    rec2.progress_pct = 99
                    rec2.progress_note = None
                    session.add(rec2)
                    session.commit()

    # Change 078: EINMAL alle gesammelten (globalen) Wörter den
    # ORIGINAL-Segmenten zuordnen — GUI-Segmentgrenzen bleiben exakt,
    # egal wie viele technische Align-Chunks nötig waren.
    if all_aligned_words:
        # Change 137: Baseline VOR dem Anwenden merken — nach dem Align
        # werden manuell korrigierte Wörter (override=true) wiederhergestellt
        # (Re-Align überschreibt sie nicht, User-Entscheid 2026-08-28).
        baseline_segments = segments
        segments = apply_aligned_words(segments, all_aligned_words, 0.0)
        segments = restore_override_words(baseline_segments, segments)
        # Change 140 (Wurzel-Fix): Text/Wort-Invariante erzwingen — die
        # Aligner-Wörter werden per LCS an den Segment-Text angeglichen
        # (nichts wird verschluckt, keine Fremdwörter; unveränderte Wörter
        # behalten ihre Zeiten). User-Befund ec98bfdf: 8/28 Segmente
        # desynct → Export/Anzeige unvollständig.
        from .routers.segments import reconcile_words_to_text

        segments = reconcile_words_to_text(segments)
        aligned_any = True

    if aligned_any:
        log.info("align: Word-Timestamps für rec_id=%s ersetzt", rec_id)
        # Change 085: Align-Stichprobe (ms/Gruppe) für den ETA-Learner —
        # Bezugsgröße ist die Gruppenzahl, nicht die Audio-Dauer.
        try:
            from . import learner_store
            learner_store.ingest_align_sample(
                rec_id, len(groups), (time.perf_counter() - _t_align0) * 1000
            )
        except Exception:
            log.warning("align: rtf sample ingest failed for rec_id=%s", rec_id,
                        exc_info=True)
    return segments


# ---------------------------------------------------------------------------
# Change 045: Hintergrund-Alignment (präzises Alignment nach "done")
# ---------------------------------------------------------------------------
# Der User sieht die Transkription sofort mit Backend-/linear verteilten
# Word-Timestamps; der Aligner-Worker verfeinert sie anschließend. Cache
# hält die VERARBEITETEN Audio-Bytes (nach VAD-Trim/Enhance/Konvertierung)
# — dieselbe Zeitbasis wie die Segment-Zeiten im Job. Versions-Guard:
# überschreibt nie Segmente, die seit dem Job-Ende geändert wurden
# (Edit/Re-Transcribe/Re-Align).

class _AlignmentCache:
    """Temporäre Ablage der verarbeiteten Audio-Bytes je Recording.

    Datei: {DATA_DIR}/.align-cache/<rec_id>.wav (+ <rec_id>.json mit
    trim_offset_s). Geschrieben im Job-Fluss an der Stelle des früheren
    synchronen Align-Aufrufs — die Bytes sind also EXAKT die, die der
    Aligner synchron bekommen hätte (nach VAD-Trim/Enhance/Konvertierung,
    gleiche Zeitbasis wie die Segment-Zeiten). Gelesen vom
    Hintergrund-Worker, danach gelöscht. Fehlt die Datei (Restart,
    Cache-Cleanup), überspringt der Worker still.
    """

    _DIR = Path(os.getenv("DATA_DIR", "/data")) / ".align-cache"

    @classmethod
    def _ensure_dir(cls) -> None:
        cls._DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def path(cls, rec_id: int) -> Path:
        return cls._DIR / f"{rec_id}.wav"

    @classmethod
    def meta_path(cls, rec_id: int) -> Path:
        return cls._DIR / f"{rec_id}.json"

    @classmethod
    def write(cls, rec_id: int, audio_bytes: bytes,
              vad_meta: Optional[Union[Dict[str, Any], float]] = None) -> None:
        """vad_meta (Change 114): dict {"type": "shift"|"map", …} ODER float
        (Alt-Format trim_offset_s). meta.json trägt beides kompatibel."""
        try:
            import json as _json

            cls._ensure_dir()
            cls.path(rec_id).write_bytes(audio_bytes)
            meta: Dict[str, Any] = {}
            if isinstance(vad_meta, dict):
                meta["vad"] = vad_meta
            elif vad_meta:  # Alt-Aufrufer: float trim_offset_s
                meta["trim_offset_s"] = float(vad_meta)
            cls.meta_path(rec_id).write_text(_json.dumps(meta))
        except Exception as exc:
            log.warning("align-cache: write failed rec_id=%s: %s", rec_id, exc)

    @classmethod
    def read(cls, rec_id: int) -> Optional[bytes]:
        p = cls.path(rec_id)
        try:
            if p.is_file():
                return p.read_bytes()
        except Exception as exc:
            log.warning("align-cache: read failed rec_id=%s: %s", rec_id, exc)
        return None

    @classmethod
    def read_meta(cls, rec_id: int) -> float:
        """trim_offset_s des Jobs (0.0 wenn unbekannt/fehlt) — Alt-Format."""
        try:
            import json as _json

            p = cls.meta_path(rec_id)
            if p.is_file():
                return float(_json.loads(p.read_text()).get("trim_offset_s", 0.0))
        except Exception:
            pass
        return 0.0

    @classmethod
    def read_vad_meta(cls, rec_id: int) -> Optional[Dict[str, Any]]:
        """Change 114: vad_meta des Jobs (shift/map) — None wenn Alt-Format."""
        try:
            import json as _json

            p = cls.meta_path(rec_id)
            if p.is_file():
                meta = _json.loads(p.read_text())
                vad = meta.get("vad")
                if isinstance(vad, dict):
                    return vad
                # Alt-Format: trim_offset_s float → shift-Äquivalent
                off = meta.get("trim_offset_s", 0.0)
                if off:
                    return {"type": "shift", "offset_s": float(off)}
        except Exception:
            pass
        return None

    @classmethod
    def delete(cls, rec_id: int) -> None:
        try:
            for p in (cls.path(rec_id), cls.meta_path(rec_id)):
                if p.is_file():
                    p.unlink()
        except Exception as exc:
            log.warning("align-cache: delete failed rec_id=%s: %s", rec_id, exc)


def run_align_job(rec_id: int, job: Optional[Any] = None) -> None:
    """Change 155 (Schritt 4): Queue-Dispatch-Ziel für align-Jobs."""
    separate_backend = "none"
    if job is not None and job.payload:
        separate_backend = job.payload.get("separate_backend") or "none"
    # Change 155 (Schritt 5): Job-Heartbeat über die Audio-Vorbereitung
    # (Laden/VAD/Enhance/separate) — dort tickt sonst nichts, die UI
    # würde eine falsche Stall-Warnung zeigen.
    hb_stop = _start_job_heartbeat(rec_id)
    try:
        _run_background_align(rec_id, job=job, separate_backend=separate_backend)
    finally:
        hb_stop.set()


def _run_background_align(rec_id: int, job: Optional[Any] = None,
                          separate_backend: str = "none") -> None:
    """Hintergrund-Worker (Change 045): präzises Forced-Alignment nach „done".

    Change 155 (Schritt 4): Läuft als Queue-Job (kind=align) statt nacktem
    Thread. Das Audio wird selbst vorbereitet (_prepare_align_audio —
    gleiche Zeitbasis wie die Pipeline, reproduzierbar aus den Run-Settings)
    statt aus dem RAM-Cache gelesen — damit align-Jobs nach einem
    Webapp-Neustart rehydrierbar sind.

    - Setzt ``alignment``: pending → running → done|skipped.
    - Versions-Guard: wurden die Segmente seit dem Job geändert (Edit,
      Re-Transcribe), wird das Ergebnis verworfen (nie fremde Edits
      überschreiben).
    - Fehler (Audio weg, Aligner down): ``skipped``, Backend-Timestamps
      bleiben — nie ein Job-Fail.
    """
    from .aligner_client import ALIGN_WORDS_ENABLED
    from .models import Recording as _Rec

    if not ALIGN_WORDS_ENABLED:
        return

    prepared = _prepare_align_audio(rec_id, separate_backend=separate_backend)
    if prepared is None:
        try:
            with Session(engine) as session:
                rec = session.get(_Rec, rec_id)
                if rec is not None and rec.alignment == "pending":
                    rec.alignment = "skipped"
                    session.add(rec)
                    session.commit()
        except Exception as exc:
            log.warning("bg-align: Audio fehlt, Status-Update fehlgeschlagen (rec_id=%s): %s", rec_id, exc)
        log.info("bg-align: Audio nicht verfügbar für rec_id=%s — skipped", rec_id)
        return
    audio_bytes, vad_meta_prep = prepared

    # Baseline der Segmente (für den Versions-Guard) + Job-Parameter.
    try:
        with Session(engine) as session:
            rec = session.get(_Rec, rec_id)
            if rec is None or rec.status != "done":
                _AlignmentCache.delete(rec_id)
                return
            segments: List[Dict[str, Any]] = _json_deepcopy(rec.segments or [])
            language = rec.language
            # Audio/Zeitbasis: die vorbereiteten Bytes (Trim/Enhance) gehen
            # direkt an den Aligner. Nur die Segment-Zeiten sind im Job um
            # vad_meta (shift/map, Change 114) kompensiert → vor dem Align
            # zurückrechnen, danach wieder aufschlagen (identische Zeitbasis
            # wie der synchrone Lauf).
            vad_meta = vad_meta_prep
            if vad_meta:
                _unshift_or_unmap(segments, vad_meta)
            rec.alignment = "running"
            session.add(rec)
            session.commit()
            # Change 170: Phasen-Note + phase_started_at für die UI —
            # sonst zeigen die Chips den Zustand des alten Transcribe-
            # Laufs („finalizing läuft seit 180m", Live-Befund 2026-08-31).
            # Defensiv: ein UI-Status-Update darf den Job nie brechen.
            try:
                from . import crud as _crud
                _crud.set_progress(session, rec_id, 1, "alignment")
            except Exception:
                log.warning("bg-align: status note update failed (rec_id=%s)", rec_id, exc_info=True)
    except Exception as exc:
        # Defensiv: Worker-Fehler nie als unhandled Thread-Exception enden
        # (Tests/Isolation, DB weg) — still aufräumen, Backend-Timestamps
        # bleiben (nie ein Job-Fail).
        log.warning("bg-align: Baseline-Lesen fehlgeschlagen (rec_id=%s): %s", rec_id, exc)
        _AlignmentCache.delete(rec_id)
        return

    try:
        new_segments = _run_align_phase(
            rec_id, segments, audio_bytes,
            f"{rec_id}.wav", language, job=None, background=True,
        )
        if vad_meta:
            _shift_or_remap(new_segments, vad_meta)
    except Exception as exc:
        log.warning("bg-align: rec_id=%s failed: %s", rec_id, exc)
        new_segments = None

    # Change 124: User-Cancel während des Laufs → Ergebnis verwerfen,
    # alignment=skipped (die Transkription selbst bleibt done).
    if _align_cancelled(rec_id):
        with _align_lock:
            _BG_ALIGN_CANCEL.discard(rec_id)
        try:
            with Session(engine) as session:
                rec_c = session.get(_Rec, rec_id)
                if rec_c is not None:
                    rec_c.alignment = "skipped"
                    session.add(rec_c)
                    session.commit()
        except Exception as exc:
            log.warning("bg-align: Cancel-Status-Update fehlgeschlagen (rec_id=%s): %s", rec_id, exc)
        _AlignmentCache.delete(rec_id)
        log.info("bg-align: rec_id=%s abgebrochen (User-Cancel, alignment=skipped)", rec_id)
        return

    try:
        with Session(engine) as session:
            rec = session.get(_Rec, rec_id)
            if rec is None:
                _AlignmentCache.delete(rec_id)
                return
            if new_segments is not None and _same_segments(rec.segments, segments):
                if not _same_segments(new_segments, segments):
                    # Change 101: Wörter wirklich ersetzt → done.
                    rec.segments = new_segments
                    rec.alignment = "done"
                    rec.error = None
                else:
                    # Change 101: Der Aligner hat NICHTS ersetzt — „done“
                    # wäre eine stille Lüge (User-Befund 2026-08-23:
                    # „Re-Align bringt nichts“, Karaoke rast im 80-ms-Raster
                    # der Backend-Platzhalter). Grund sichtbar machen.
                    from .aligner_client import AlignerClient as _AlignCl
                    if _AlignCl().health():
                        reason = "Aligner lieferte keine Wort-Timestamps"
                    else:
                        reason = "Aligner nicht erreichbar"
                    rec.alignment = "skipped"
                    rec.error = f"Re-Align ohne Effekt: {reason}"
                    log.warning("bg-align: rec_id=%s — %s (alignment=skipped)", rec_id, reason)
            elif new_segments is not None:
                log.info("bg-align: Segmente geändert während des Laufs (rec_id=%s) — Ergebnis verworfen", rec_id)
                rec.alignment = "skipped"
            else:
                # Change 158: Aligner-Fehler (z.B. Container down) — skipped
                # mit ehrlichem Grund statt still (symmetrisch zum
                # 0-Wörter-Fall oben). Transkription bleibt done.
                from .aligner_client import AlignerClient as _AlignCl
                if _AlignCl().health():
                    reason = "Aligner-Fehler"
                else:
                    reason = "Aligner nicht erreichbar"
                rec.alignment = "skipped"
                rec.error = f"Alignment übersprungen: {reason}"
                log.warning("bg-align: rec_id=%s — %s (alignment=skipped)", rec_id, reason)
            # Change 178+179: Nach skipped/done die Fortschritts-Metadaten
            # räumen — note/pct vom Lauf würden als Restzustand stehen
            # bleiben und die Chips einen Lauf vortäuschen (Live-Befund
            # 2026-08-31: note='alignment', pct=1 nach skipped).
            # Change 179: progress_pct ist NOT NULL (sqlite3.IntegrityError
            # beim None — Live-Befund) → 0 statt None; note darf NULL sein.
            if rec.alignment != "running":
                rec.progress_note = None
                rec.progress_pct = 0
            session.add(rec)
            session.commit()
    except Exception as exc:
        log.warning("bg-align: Write fehlgeschlagen (rec_id=%s): %s", rec_id, exc)
    _AlignmentCache.delete(rec_id)
    try:
        _align_state = rec.alignment if rec is not None else "?"
    except Exception:
        # Detached/expired nach commit — nur Logging, kein Crash im Worker.
        _align_state = "?"
    log.info("bg-align: rec_id=%s fertig (alignment=%s)", rec_id, _align_state)


def recover_stale_alignments(session: Session) -> int:
    """Change 048: Boot-Recovery — hängende Hintergrund-Alignments auflösen.

    Ein Background-Align-Worker (Change 045/046) stirbt mit dem Prozess
    (Container-Restart, Stromausfall), ohne ``alignment`` zu setzen —
    es bleibt ``pending`` (nie gestartet) oder ``running`` (mitten im
    Aligner-Call). Beim Boot kann es noch KEINE laufenden Alignments geben
    (Worker starten erst mit neuen Jobs nach dem Boot) → ``pending``/
    ``running`` ist sicher verwaist.

    Recovery: Status → ``skipped`` (Backend-Timestamps bleiben; der User
    kann das präzise Alignment über den Re-Align-Button jederzeit manuell
    nachholen) + verwaiste Cache-Dateien (``.align-cache/<rec_id>.wav`` +
    ``.json``) löschen. Idempotent; loggt die Anzahl.

    Returns: Anzahl behandelter Recordings.
    """
    from .models import Recording as _Rec

    rows = session.exec(
        select(_Rec).where(_Rec.alignment.in_(["pending", "running"]))
    ).all()
    for rec in rows:
        rec.alignment = "skipped"
        session.add(rec)
        if rec.id is not None:
            _AlignmentCache.delete(rec.id)
    if rows:
        session.commit()
        log.warning(
            "boot-recovery: %d hängende(s) Alignment(s) (pending/running) "
            "→ skipped + Cache bereinigt", len(rows),
        )
    return len(rows)


def _json_deepcopy(obj):
    import json as _json

    return _json.loads(_json.dumps(obj))


def _current_run(session, rec):
    """Change 099: aktueller Run eines Recordings (current_run_id; Fallback
    jüngster Run). None wenn keiner existiert — Aufrufer nutzen Defaults."""
    from .models import TranscriptionRun as _Run

    if rec.current_run_id:
        run = session.get(_Run, rec.current_run_id)
        if run is not None:
            return run
    return session.exec(select(_Run).where(
        _Run.rec_id == rec.id).order_by(_Run.id.desc())).first()


def _prepare_align_audio(rec_id: int,
                         separate_backend: Optional[str] = None,
                         run: Optional[Any] = None) -> Optional[Tuple[bytes, Optional[Dict[str, Any]]]]:
    """Change 155 (Schritt 4): Audio fürs Forced-Alignment vorbereiten.

    Aus ``_schedule_realign`` verschoben — die Vorverarbeitung (Audio laden,
    VAD-Trim, Enhance, Music-Removal) läuft jetzt IM Queue-Worker, damit
    align-Jobs rehydrierbar sind (kein RAM-Cache mehr nötig). Reproduziert
    die Zeitbasis der Transkriptions-Pipeline (gleiche Settings aus dem Run).

    Returns (audio_bytes, vad_meta) oder None wenn nicht möglich.
    """
    from .models import Recording as _Rec

    with Session(engine) as session:
        rec = session.get(_Rec, rec_id)
        if rec is None:
            return None
        stored = Path(rec.stored_path) if rec.stored_path else None
        if stored is None or not stored.is_file():
            log.warning("align: Audio fehlt für rec_id=%s", rec_id)
            return None
        try:
            audio_bytes = stored.read_bytes()
        except Exception as exc:
            log.warning("align: Audio nicht lesbar rec_id=%s: %s", rec_id, exc)
            return None
        vad_meta: Optional[Dict[str, Any]] = None  # Change 114
        if run is None:
            run = _current_run(session, rec)  # Change 099: Settings aus dem Run
        vad_mode = _run_vad_mode(run)  # Change 114: off|edges|all
        if vad_mode != "off":
            try:
                audio_bytes, vad_meta = _apply_vad(audio_bytes, vad_mode)
            except Exception as exc:
                log.warning("vad fehlgeschlagen (rec_id=%s): %s", rec_id, exc)
                vad_meta = None
        if run is not None and run.enable_enhance and run.enable_enhance != "off":
            try:
                audio_bytes = enhance_audio(audio_bytes, level=run.enable_enhance)
            except Exception as exc:
                log.warning("align: enhance failed rec_id=%s: %s", rec_id, exc)
        # Change 113: Music-Removal — vocals als Align-Eingabe (wie ASR-Pipeline).
        if separate_backend and separate_backend != "none":
            try:
                from .separate_client import SeparateClient
                sc = SeparateClient()
                if sc.health():
                    vocals = sc.separate(audio_bytes, backend=separate_backend)
                    if vocals:
                        log.info("align: separate rec_id=%s backend=%s → vocals als Align-Eingabe (%d→%d B)",
                                 rec_id, separate_backend, len(audio_bytes), len(vocals))
                        audio_bytes = vocals
                    else:
                        log.warning("align: separate rec_id=%s lieferte keine vocals — weiter mit Original", rec_id)
                else:
                    log.warning("align: separate crispr-sep nicht erreichbar — weiter mit Original (rec_id=%s)", rec_id)
            except Exception as exc:
                log.warning("align: separate Fehler rec_id=%s — weiter mit Original: %s", rec_id, exc)
        return audio_bytes, vad_meta


def _schedule_realign(rec_id: int, separate_backend: str = "none") -> bool:
    """Change 046: Re-Alignment auf dem aktuellen (ggf. korrigierten) Text.

    Change 155 (Schritt 4): Statt eigenem Thread wird ein ``align``-Queue-Job
    enqueued — universelles Scheduling (Priorität, Rehydration, ein
    Heartbeat-Muster). Der Worker bereitet das Audio selbst vor
    (``_prepare_align_audio``). Der User kann die Transkription weiter
    sehen/bearbeiten; die Word-Timestamps werden akustisch verifiziert,
    sobald der Worker fertig ist.

    Returns False wenn Aligner deaktiviert, Datei fehlt oder Audio nicht
    lesbar — der Aufrufer antwortet dann mit verständlichem Fehler.
    """
    from .aligner_client import ALIGN_WORDS_ENABLED
    from .models import Recording as _Rec

    if not ALIGN_WORDS_ENABLED:
        log.info("realign: ALIGN_WORDS_ENABLED=false (rec_id=%s)", rec_id)
        return False

    with Session(engine) as session:
        rec = session.get(_Rec, rec_id)
        if rec is None:
            return False
        if rec.status != "done":
            log.info("realign: rec_id=%s status=%s — nur done erlaubt", rec_id, rec.status)
            return False
        stored = Path(rec.stored_path) if rec.stored_path else None
        if stored is None or not stored.is_file():
            log.warning("realign: Audio fehlt für rec_id=%s", rec_id)
            return False
        rec.alignment = "pending"
        # Change 180: Fortschritt SOFORT setzen — ohne das zeigt die UI
        # zwischen POST und Worker-Start den Restzustand (leere note +
        # alte phase_started_at → „preparing blinkt mit 8:30", User-Befund
        # 2026-08-31).
        rec.progress_note = "alignment"
        rec.progress_pct = 0
        rec.phase_started_at = datetime.now(timezone.utc)
        user_id = rec.user_id
        backend = rec.backend or ""
        session.add(rec)
        session.commit()

    from .queue import QueueError, queue_manager

    try:
        queue_manager.enqueue(
            rec_id, user_id=user_id, backend=backend,
            kind="align", payload={"separate_backend": separate_backend},
            key=f"align-{rec_id}",
        )
    except QueueError as exc:
        log.warning("realign: enqueue fehlgeschlagen rec_id=%s: %s", rec_id, exc)
        return False
    log.info("realign: rec_id=%s align-Queue-Job enqueued", rec_id)
    return True


# ---------------------------------------------------------------------------
# Change 057 — Re-Diarize (Sprecher-Zuordnung neu berechnen)
# ---------------------------------------------------------------------------


def _schedule_rediarize(rec_id: int, opts: Optional[Dict[str, Any]] = None) -> bool:
    """Change 057: Diarization auf dem aktuellen Audio neu berechnen.

    Change 155 (Schritt 4): Statt eigenem Thread wird ein ``rediarize``-
    Queue-Job enqueued (universelles Scheduling). Der Worker bereitet das
    Audio selbst vor (lädt Datei, reproduziert VAD-Trim/Enhance — gleiche
    Zeitbasis wie beim Job). Ersetzt NUR die ``speaker``-Felder der
    Segmente — Text, Wörter, Timestamps, manuelle Aufteilung und Alignment
    bleiben unangetastet.

    Change 116: optionale Diar-Optionen (``num_speakers``,
    ``min_duration_off``, ``method``) — übersteuern die gespeicherten
    Run-Einstellungen (Change 099), wenn sie gesetzt sind.

    Returns False wenn Audio fehlt/nicht lesbar oder status != done — der
    Aufrufer antwortet dann mit verständlichem Fehler.
    """
    from .models import Recording as _Rec

    with Session(engine) as session:
        rec = session.get(_Rec, rec_id)
        if rec is None:
            return False
        if rec.status != "done":
            log.info("rediarize: rec_id=%s status=%s — nur done erlaubt", rec_id, rec.status)
            return False
        stored = Path(rec.stored_path) if rec.stored_path else None
        if stored is None or not stored.is_file():
            log.warning("rediarize: Audio fehlt für rec_id=%s", rec_id)
            return False
        rec.diar_status = "pending"
        # Change 180: Fortschritt SOFORT setzen (wie realign) — sonst
        # zeigt die UI den Restzustand mit alter phase_started_at.
        rec.progress_note = "diarization"
        rec.progress_pct = 0
        rec.phase_started_at = datetime.now(timezone.utc)
        user_id = rec.user_id
        backend = rec.backend or ""
        session.add(rec)
        session.commit()

    from .queue import QueueError, queue_manager

    try:
        queue_manager.enqueue(
            rec_id, user_id=user_id, backend=backend,
            kind="rediarize", payload=opts, key=f"rediarize-{rec_id}",
        )
    except QueueError as exc:
        log.warning("rediarize: enqueue fehlgeschlagen rec_id=%s: %s", rec_id, exc)
        return False
    log.info("rediarize: rec_id=%s rediarize-Queue-Job enqueued", rec_id)
    return True


def run_rediarize_job(rec_id: int, payload: Optional[Dict[str, Any]] = None,
                      job: Optional[Any] = None) -> None:
    """Change 155 (Schritt 4): Queue-Dispatch-Ziel für rediarize-Jobs.

    Bereitet das Audio selbst vor (lädt Datei, reproduziert VAD-Trim/
    Enhance aus den Run-Settings — gleiche Zeitbasis wie beim Transkriptions-
    Job) und übergibt es an den bisherigen Worker. Damit sind rediarize-
    Jobs nach einem Webapp-Neustart rehydrierbar (kein RAM-Cache).
    """
    from .models import Recording as _Rec

    with Session(engine) as session:
        rec = session.get(_Rec, rec_id)
        if rec is None:
            return
        if rec.status != "done":
            log.info("rediarize: rec_id=%s status=%s — nur done erlaubt", rec_id, rec.status)
            return
        stored = Path(rec.stored_path) if rec.stored_path else None
        if stored is None or not stored.is_file():
            log.warning("rediarize: Audio fehlt für rec_id=%s", rec_id)
            return
        try:
            audio_bytes = stored.read_bytes()
        except Exception as exc:
            log.warning("rediarize: Audio nicht lesbar rec_id=%s: %s", rec_id, exc)
            return
        vad_meta: Optional[Dict[str, Any]] = None  # Change 114
        run = _current_run(session, rec)  # Change 099: Settings aus dem Run
        vad_mode = _run_vad_mode(run)  # Change 114: off|edges|all
        if vad_mode != "off":
            try:
                audio_bytes, vad_meta = _apply_vad(audio_bytes, vad_mode)
            except Exception as exc:
                log.warning("vad fehlgeschlagen (rec_id=%s): %s", rec_id, exc)
                vad_meta = None
        if run is not None and run.enable_enhance and run.enable_enhance != "off":
            try:
                audio_bytes = enhance_audio(audio_bytes, level=run.enable_enhance)
            except Exception as exc:
                log.warning("rediarize: enhance failed rec_id=%s: %s", rec_id, exc)
    _run_background_rediarize(rec_id, audio_bytes, vad_meta, payload)


def _run_background_rediarize(rec_id: int, audio_bytes: bytes,
                              vad_meta: Optional[Dict[str, Any]] = None,
                              opts: Optional[Dict[str, Any]] = None) -> None:
    """Change 057: Hintergrund-Worker für Re-Diarize.

    - Führt die Diarization auf den verarbeiteten Bytes aus (Zeitbasis wie
      im Transkriptions-Job) und kompensiert den VAD-Trim-Offset.
    - Mappt die Sprecher-Intervalle über Wort-Überlappung auf die Segmente
      (gleiche Logik wie die Pipeline: ``_build_word_stream`` +
      ``_merge_diarization``).
    - Versions-Guard: wurden die Segmente seit dem Start geändert (Edit,
      Re-Transcribe), wird das Ergebnis verworfen (nie fremde Edits
      überschreiben) → ``skipped``.
    - Fehler (Diar down, leeres Ergebnis): ``failed`` mit Log — nie ein
      stilles Verschlucken.
    """
    from .diarize import DiarizationError
    from .models import Recording as _Rec

    with Session(engine) as session:
        rec = session.get(_Rec, rec_id)
        if rec is None:
            return
        segments_before = _json_deepcopy(rec.segments or [])
        text = rec.text or ""
        duration = rec.duration_s or 0.0
        run = _current_run(session, rec)  # Change 099: Optionen aus dem Run
        num_speakers = run.diarize_num_speakers if run else None
        min_duration_off = run.diarize_min_duration_off if run else None
        method = run.diarize_method if run else None
        # Change 116: explizite Optionen übersteuern die Run-Werte.
        if opts:
            if opts.get("num_speakers") is not None:
                num_speakers = opts["num_speakers"]
            if opts.get("min_duration_off") is not None:
                min_duration_off = opts["min_duration_off"]
            if opts.get("method"):
                method = opts["method"]
        rec.diar_status = "running"
        # Change 170: Phasen-Note + phase_started_at für die UI — die
        # Chips müssen „diarizing" zeigen (activePhaseIndex), nicht den
        # pct-Fallback des alten Laufs (Live-Befund 2026-08-31: blinkende
        # „finalizing"-Kachel mit „läuft seit 180m" während re-diarize).
        # Defensiv: ein UI-Status-Update darf den Job nie brechen.
        session.add(rec)
        session.commit()
        try:
            from . import crud as _crud
            _crud.set_progress(session, rec_id, 1, "diarization")
        except Exception:
            log.warning("rediarize: status note update failed (rec_id=%s)", rec_id, exc_info=True)

    # Change 115: Job-Heartbeat für die UI („aktiv seit Xs") — tickt
    # last_heartbeat_at via set_progress(note=None); die Note bleibt stehen.
    hb_job = _start_job_heartbeat(rec_id)

    try:
        _tmp_wav = None
        diar_path = None
        diar_ms = 0.0
        try:
            _tmp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            _tmp_wav.write(audio_bytes)
            _tmp_wav.close()
            diar_path = _tmp_wav.name
            _t_diar0 = time.perf_counter()
            set_progress(session, rec_id, 0, note="diarization")
            diar = _run_diarization(
                diar_path,
                num_speakers=num_speakers,
                min_duration_off=min_duration_off,
                method=method,
                on_progress=lambda pct: _report_diar_progress(rec_id, pct),
            )
            diar_ms = (time.perf_counter() - _t_diar0) * 1000
        finally:
            if _tmp_wav is not None and diar_path:
                try:
                    os.unlink(diar_path)
                except OSError:
                    pass
        if not diar:
            raise DiarizationError("empty", "Diarization lieferte keine Sprecher-Segmente")
        # VAD kompensieren (Change 114): Diar-Zeiten von der verarbeiteten auf
        # die Original-Achse bringen — Segment-Zeiten liegen auf Original-Basis.
        if vad_meta and vad_meta.get("type") == "shift":
            off = float(vad_meta["offset_s"])
            diar_comp = [
                {
                    **{k: v for k, v in d.items() if k not in ("start", "end")},
                    "start": float(d["start"]) + off,
                    "end": float(d["end"]) + off,
                }
                for d in diar
            ]
        elif vad_meta and vad_meta.get("type") == "map":
            mapping = vad_meta.get("mapping", [])
            diar_comp = [
                {
                    **{k: v for k, v in d.items() if k not in ("start", "end")},
                    "start": _map_time(float(d["start"]), mapping),
                    "end": _map_time(float(d["end"]), mapping),
                }
                for d in diar
            ]
        else:
            diar_comp = diar
        word_stream = _build_word_stream(segments_before, duration)
        merged = _merge_diarization(segments_before, diar_comp, word_stream,
                                    duration, full_text=text)
        if not merged:
            raise DiarizationError("empty", "Keine text-zugeordneten Sprecher-Segmente")
        # Change 115: RTF-Stichprobe wie im Haupt-Job (diar:<method>).
        try:
            from . import learner_store
            learner_store.ingest_job_sample(
                rec_id, {f"diar:{method or 'pyannote'}": diar_ms}, duration)
        except Exception as exc:
            log.warning("rediarize: rtf sample ingest failed for rec_id=%s: %s", rec_id, exc)
    except Exception as exc:
        log.exception("rediarize: rec_id=%s fehlgeschlagen: %s", rec_id, exc)
        with Session(engine) as session:
            rec2 = session.get(_Rec, rec_id)
            if rec2 is not None:
                rec2.diar_status = "failed"
                rec2.progress_note = None
                session.add(rec2)
                session.commit()
        hb_job.set()  # Change 115: Heartbeat stoppen
        return

    with Session(engine) as session:
        rec2 = session.get(_Rec, rec_id)
        if rec2 is None:
            hb_job.set()  # Change 115
            return
        # Versions-Guard: Segmente seit Job-Start geändert → verwerfen.
        if not _same_segments(rec2.segments or [], segments_before):
            log.info("rediarize: Segmente seit Start geändert — Ergebnis verworfen (rec_id=%s)", rec_id)
            rec2.diar_status = "skipped"
            rec2.progress_note = None
            session.add(rec2)
            session.commit()
            hb_job.set()  # Change 115
            return
        rec2.segments = merged
        rec2.diar_status = "done"
        rec2.progress_note = None
        rec2.updated_at = datetime.now(timezone.utc)
        session.add(rec2)
        session.commit()
        log.info("rediarize: rec_id=%s Sprecher-Zuordnung aktualisiert (%d Segmente)",
                 rec_id, len(merged))
    hb_job.set()  # Change 115


def _same_segments(a, b) -> bool:
    """True, wenn beide Segment-Listen identisch sind (Versions-Guard)."""
    try:
        return _json_deepcopy(a) == _json_deepcopy(b)
    except Exception:
        return False


def _cancelled(job, rec_id: int) -> bool:
    """True, wenn der Job abgebrochen werden soll (Cancel oder Timeout).

    Timeout: hängende Calls (Aligner, Backends) dürfen die Queue nie
    dauerhaft blockieren — nach max_processing_s wird abgebrochen.
    """
    if job is None:
        return False
    if getattr(job, "cancel_requested", False):
        return True
    max_s = getattr(job, "_max_processing_s", None)
    if max_s is None:
        # Fallback: Modul-Konstante (nicht perfekt, aber sicher)
        max_s = 7200
    return job.running_s > max_s


def _abort_recording(rec_id: int, message: str) -> None:
    """Job abgebrochen (Cancel/Timeout) → Status failed mit klarer Meldung.

    Die Audiodatei bleibt erhalten; der User kann Re-Transcribe nutzen.
    """
    try:
        with Session(engine) as session:
            rec = crud.get_recording(session, rec_id)
            if rec is not None:
                rec.status = "failed"
                rec.error = message
                rec.progress_pct = 100
                rec.progress_note = None
                # Change 094: auch den aktiven Run als failed markieren.
                if rec.current_run_id:
                    from .models import TranscriptionRun as _Run
                    run = session.get(_Run, rec.current_run_id)
                    if run is not None and run.status not in ("done", "failed"):
                        run.status = "failed"
                        run.error = message[:500]
                        run.finished_at = datetime.now(timezone.utc)
                        session.add(run)
                session.add(rec)
                session.commit()
    except Exception:
        log.exception("abort: Status-Update fehlgeschlagen (rec_id=%s)", rec_id)


def _start_heartbeat(rec_id: int, pct: int, note: str,
                     interval_s: float = 5.0) -> threading.Event:
    """Change 155 (Schritt 5): Delegiert an ``_start_job_heartbeat`` —
    die frühere eigene Tick-Kopie (Change 011) ist dort aufgegangen.
    Semantik unverändert: pct/note werden konstant gehalten (Phasen ohne
    messbaren Fortschritt, z. B. Sync-ASR bei 21 %, Diar bei 96 %).
    """
    return _start_job_heartbeat(rec_id, interval_s=interval_s, pct=pct, note=note)


def _start_job_heartbeat(rec_id: int, interval_s: float = 5.0,
                         pct: Optional[int] = None,
                         note: Optional[str] = None) -> threading.Event:
    """Job-weiter Heartbeat (Change 047/155): tickt last_heartbeat_at über den
    GESAMTEN Job — auch in Phasen ohne eigenen Heartbeat (preparing/vad/
    enhance/16k-Konvertierung/Streaming-ASR).

    Change 155 (Schritt 5): vereinheitlicht die frühere ``_start_heartbeat``-
    Kopie (Change 011) — dieselbe Tick-Logik, konfigurierbar über ``pct``
    (Fallback, wenn das Recording fehlt; Default 1) und ``note`` (Default
    None → Phasen-Note wird nie überschrieben; mit note=... wird sie
    konstant gehalten, z. B. „asr" bei 21 %).
    """
    stop = threading.Event()

    def _tick() -> None:
        while not stop.is_set():
            try:
                with Session(engine) as s:
                    from .models import Recording as _Rec

                    rec = s.get(_Rec, rec_id)
                    cur_pct = rec.progress_pct if rec is not None else (pct if pct is not None else 1)
                    set_progress(s, rec_id, cur_pct, note=note)
            except Exception:
                log.exception("job-heartbeat: set_progress fehlgeschlagen (rec_id=%s)", rec_id)
                return
            stop.wait(interval_s)

    t = threading.Thread(  # thread:ok Job-Heartbeat-Ticker (Event-gestoppt)
        target=_tick, daemon=True,
        name=f"job-heartbeat-{rec_id}",
    )
    t.start()
    return stop


def _backend_image_digest(backend: Optional[str]) -> Optional[str]:
    """ImageID des Backend-Containers (stabil pro Image) — Change 166.

    Liefert die Docker-ImageID (config-Digest) des Containers, dessen
    compose-Service dem Backend-Namen entspricht. Wechselt die ImageID,
    invalidiert der rtf_learner die gelernte Historie (Change-085-Regel:
    Backend-Image-Update ⇒ alte Stichproben verwerfen). None bei
    fehlendem Backend/Container oder Proxy-Fehler — dann bleibt der
    Digest-Pfad aus (keine Invalidation, kein Fehler; nie raten).
    """
    if not backend:
        return None
    try:
        from . import docker_proxy as _dp
        for c in _dp.get_docker_client().list_containers():
            if (c.get("Labels") or {}).get("com.docker.compose.service") == backend:
                return c.get("ImageID") or None
    except Exception:
        return None
    return None


def process_recording(rec_id: int, backend: Optional[str] = None, job=None) -> None:
    """Load row → read audio → call ASR → persist result.

    Designed to run in a background thread (queue worker, Task 6). The
    backend comes from the bound job; falls back to the recording's own
    ``backend`` field. All exceptions are caught so a transient failure
    cannot crash the worker; the row is updated to status='failed' with the
    error message.

    Cancel (2026-08-15): *job* ist der Queue-Job (optional). Zwischen den
    Phasen wird ``_cancelled(job, rec_id)`` geprüft — bei Abbruch wird der
    Status auf failed mit klarer Meldung gesetzt (Datei bleibt). Zusätzlich
    greift ein Job-Timeout (max_processing_s), damit ein hängender Call die
    Queue nie dauerhaft blockiert.
    """
    with Session(engine) as session:
        rec = crud.get_recording(session, rec_id)
        if rec is None:
            log.warning("process_recording: rec_id=%d not found, skipping", rec_id)
            return
        audio_path = Path(rec.stored_path)
        filename = rec.original_name
        mime = rec.mime or "application/octet-stream"
        enable_vad = False  # ersetzt durch Run-Settings (Change 099, unten)
        vad_mode = "off"  # Change 114: off|edges|all
        enable_diarize = False
        enable_streaming = False
        enable_noise_reduce = True
        enable_enhance = "off"
        separate_backend = "none"
        enable_punctuation = False
        enable_llm_enhance = False
        prompt_template_id = None
        delivery_target_id = None
        llm_endpoint_id = None
        run_diarize_num_speakers = None  # Change 099: Defaults (Run-Settings unten)
        run_diarize_min_duration_off = None
        run_diarize_method = None
        owner_id = rec.user_id
        if backend is None:
            backend = rec.backend or "ps-pk-onnx"
            # Change 082: gewähltes Backend persistieren, damit das
            # Recording-Dict es während processing führt (ETA-RTF-Wahl).
            if rec.backend != backend:
                with Session(engine) as s2:
                    r2 = s2.get(Recording, rec_id)
                    if r2 is not None:
                        r2.backend = backend
                        s2.add(r2)
                        s2.commit()

    # Change 094/099 (runs → results): Der Run ist die versionierte Quelle
    # der Settings. Upload/transcribe/retranscribe legen den Run an
    # (status=queued); hier wird der älteste queued-Run übernommen und auf
    # processing gestellt. Fallback (direkter Worker-Aufruf ohne Route):
    # neuer Run mit Defaults.
    run_id: Optional[int] = None
    run = None
    try:
        from .models import TranscriptionRun as _Run, Recording as _Rec
        from sqlmodel import select as _select
        with Session(engine) as session:
            run = session.exec(_select(_Run).where(
                _Run.rec_id == rec_id, _Run.status == "queued"
            ).order_by(_Run.id.asc())).first()
            if run is None:
                r2 = session.get(_Rec, rec_id)
                if r2 is not None and r2.current_run_id:
                    run = session.get(_Run, r2.current_run_id)
            if run is None:
                run = _Run(
                    rec_id=rec_id,
                    backend=backend or "ps-pk-onnx",
                    status="queued",
                    created_by_user_id=owner_id,
                )
                session.add(run)
            run.status = "processing"
            run.started_at = datetime.now(timezone.utc)
            run.progress_pct = rec.progress_pct
            run.phase = rec.progress_note
            if backend and not run.backend:
                run.backend = backend
            session.add(run)
            session.commit()
            session.refresh(run)
            run_id = run.id
            r2 = session.get(_Rec, rec_id)
            if r2 is not None:
                r2.current_run_id = run_id
                session.add(r2)
                session.commit()
            # Change 099: Settings INNERHALB der Session lesen — der Run
            # wäre nach Session-Ende detached (Expire-on-commit).
            enable_vad = bool(run.enable_vad)
            vad_mode = _run_vad_mode(run)  # Change 114: off|edges|all
            enable_diarize = bool(run.enable_diarize)
            enable_streaming = bool(run.enable_streaming)
            enable_noise_reduce = bool(run.enable_noise_reduce)
            enable_enhance = run.enable_enhance or "off"
            separate_backend = run.separate_backend or "none"
            enable_punctuation = bool(run.enable_punctuation)
            enable_llm_enhance = bool(run.enable_llm_enhance)
            prompt_template_id = run.prompt_template_id
            delivery_target_id = run.delivery_target_id
            llm_endpoint_id = run.llm_endpoint_id
            run_diarize_num_speakers = run.diarize_num_speakers
            run_diarize_min_duration_off = run.diarize_min_duration_off
            run_diarize_method = run.diarize_method
    except Exception:
        log.exception("Change 099: Run-Übernahme fehlgeschlagen (rec_id=%s)", rec_id)

    log.info("process_recording rec_id=%s: vad=%s diarize=%s streaming=%s noise=%s",
             rec_id, enable_vad, enable_diarize, enable_streaming, enable_noise_reduce)

    t0 = time.perf_counter()
    # Change 085: Phasen-Zeiten je Job (ms) — Stichproben für rtf_learner.
    phase_times: Dict[str, float] = {}
    status = "done"
    text: str = ""
    duration = None
    language = None
    segments: List[Dict[str, Any]] = []
    error = None
    # Change 157: Diar-Fehler degradieren statt Run abbrechen — die
    # Transkription bleibt, der Fehler wird ehrlich angezeigt.
    diar_error: Optional[str] = None
    peaks = None
    alignment_pending = False
    hb_job: Optional[threading.Event] = None

    try:
        audio_bytes = audio_path.read_bytes()
        vad_meta: Optional[Dict[str, Any]] = None  # Change 114: statt trim_offset_s

        # Change 047: Job-weiter Heartbeat — tickt last_heartbeat_at über
        # ALLE Phasen (auch preparing/vad/enhance/Konvertierung/Streaming),
        # nicht nur asr/diar/llm. Beendet im finally unten.
        hb_job = _start_job_heartbeat(rec_id)

        # Change 151: Jede Phase hat ihren EIGENEN 0..100-Balken (die Chips
        # zeigen die Abfolge). Diskrete Schritte ohne Teilfortschritt melden
        # 100, sobald sie laufen — kein global skaliertes Fake-Splitting.
        with Session(engine) as session:
            set_progress(session, rec_id, 100, note="preparing")

        # Optional VAD silence trimming (Change 114: vad_mode off|edges|all,
        # User-konfigurierbar, kein Env-Gate mehr)
        if vad_mode and vad_mode != "off":
            _t_vad0 = time.perf_counter()
            with Session(engine) as session:
                set_progress(session, rec_id, 100, note="vad")
            audio_bytes, vad_meta = _apply_vad(audio_bytes, vad_mode)
            if vad_meta:
                log.info("vad: rec_id=%s mode=%s", rec_id, vad_meta["type"])
            phase_times["vad"] = (time.perf_counter() - _t_vad0) * 1000
            if vad_meta and vad_meta.get("type") == "shift":
                log.info("VAD trim: rec_id=%s offset=%.2fs", rec_id, vad_meta["offset_s"])

        # Optional audio enhancement (ffmpeg filters before ASR)
        if enable_enhance and enable_enhance != "off":
            _t_enh0 = time.perf_counter()
            with Session(engine) as session:
                set_progress(session, rec_id, 100, note="enhance")
            log.info("Enhance: rec_id=%s level=%s", rec_id, enable_enhance)
            enhanced = enhance_audio(audio_bytes, level=enable_enhance)
            if len(enhanced) != len(audio_bytes):
                log.info("Enhance: rec_id=%s %d→%d bytes", rec_id, len(audio_bytes), len(enhanced))
            audio_bytes = enhanced
            phase_times[f"enhance:{enable_enhance}"] = (time.perf_counter() - _t_enh0) * 1000

        # Optional: Source Separation (Change 106) — vocals als ASR-Eingabe.
        # Ehrlicher Fehlerpfad: crispr-sep down / liefert nichts / Fehler →
        # weiter mit Original-Audio (Log-Warnung, kein Fake-Status).
        if separate_backend and separate_backend != "none":
            _t_sep0 = time.perf_counter()
            with Session(engine) as session:
                set_progress(session, rec_id, 100, note="separate")
            try:
                from .separate_client import SeparateClient
                sc = SeparateClient()
                if sc.health():
                    vocals = sc.separate(audio_bytes, backend=separate_backend)
                    if vocals:
                        log.info("separate: rec_id=%s backend=%s → vocals als ASR-Eingabe (%d→%d B)",
                                 rec_id, separate_backend, len(audio_bytes), len(vocals))
                        audio_bytes = vocals
                    else:
                        log.warning("separate: rec_id=%s lieferte keine vocals — weiter mit Original", rec_id)
                else:
                    log.warning("separate: crispr-sep nicht erreichbar — weiter mit Original (rec_id=%s)", rec_id)
            except Exception as exc:
                log.warning("separate: Fehler rec_id=%s — weiter mit Original: %s", rec_id, exc)
            phase_times[f"separate:{separate_backend}"] = (time.perf_counter() - _t_sep0) * 1000

        with Session(engine) as session:
            set_progress(session, rec_id, 0, note="asr")

        # Run ASR (batched sync or SSE streaming)
        _t_asr0 = time.perf_counter()
        client = get_client(backend)
        # Storage ist seit 2026-08-14 nativ (MP3/OGG/…). Backends ohne
        # Compressed-Support (CrispASR-Familie) bekommen eine 16-kHz-mono-WAV
        # on-the-fly — der Store bleibt trotzdem im Originalformat.
        if (not getattr(client.capabilities, "accepts_compressed", False)
                and audio_path.suffix.lower() != ".wav"):
            log.info("Converting %s → 16k mono WAV for backend %s",
                     audio_path.name, backend)
            audio_bytes, _, _ = convert_to_wav_16k_mono(audio_bytes, audio_path.name)
        # Change 147: TTS-Marker ans Audio-Ende hängen — deterministische
        # Vollständigkeits-Erkennung (User-Idee). Nur ab _TRANSCRIPT_MIN_S
        # (Triage: kurze Aufnahmen/Mocks bleiben unberührt).
        marker_active = (rec.duration_s or 0.0) >= _TRANSCRIPT_MIN_S
        if marker_active:
            audio_bytes = _append_transcript_marker(audio_bytes)
        if enable_streaming and client.capabilities.streaming:

            def _on_chunk(acc_text: str, idx: int, total: int, start: float, end: float, final: bool):
                pct = int((idx + 1) / total * 100)  # Change 151: phasen-lokal 0..100
                # Change 147: Chunk-Zähler in die note — die UI zeigt
                # „Transkribieren 23/45" statt nur der Phase.
                with Session(engine) as session:
                    set_progress(session, rec_id, pct, note=f"asr Chunk {idx + 1}/{total}")
                    if acc_text:
                        rec = crud.get_recording(session, rec_id)
                        if rec:
                            rec.text = acc_text
                            session.add(rec)
                            session.commit()

            result = client.transcribe_streaming(
                audio_bytes, filename, mime,
                noise_reduce=enable_noise_reduce,
                on_chunk=_on_chunk,
            )
            with Session(engine) as session:
                # Change 151: finalizing ist eine eigene Phase (Balken 0..100)
                # — 100 = die Nachbearbeitung läuft; der Balken ist voll,
                # die Chips zeigen die Phase als aktiv.
                set_progress(session, rec_id, 100, note="finalizing")
                rec2 = crud.get_recording(session, rec_id)
                if rec2 is not None and rec2.progress_note is not None:
                    rec2.progress_note = None
                    session.add(rec2)
                    session.commit()
        else:
            def _on_progress(pct: int):
                with Session(engine) as s:
                    set_progress(s, rec_id, pct)
            # Sync-Backends (CrispASR-Familie, async_jobs=False) liefern keinen
            # Job-Progress — sichtbarer Phasen-Hinweis statt starrer 20%.
            # Change 011: Heartbeat tickt last_heartbeat_at, während der
            # blockierende transcribe() läuft (kann Minuten dauern) — die UI
            # zeigt „transcribing · aktiv seit Xs" statt eingefrorenem 21%.
            hb_stop: Optional[threading.Event] = None
            if not getattr(client.capabilities, "async_jobs", False):
                with Session(engine) as session:
                    set_progress(session, rec_id, 21, note="asr")
            # Change 035: Heartbeat-Fallback IMMER (auch async_jobs=True):
            # ps-pk-onnx deklariert async_jobs=True, definiert aber kein
            # eigenes transcribe_async → Basisklasse fällt auf blockierendes
            # transcribe() zurück. Ohne Heartbeat friert last_heartbeat_at
            # ein → falsche Stall-Warnung bei JEDER Transkription (Befund
            # 20.08.). Der Thread liest den aktuellen pct aus der DB und
            # tickt nur last_heartbeat_at — kein Konflikt mit on_progress.
            hb_stop = _start_heartbeat(rec_id, 21, "asr")
            try:
                result = client.transcribe_async(
                    audio_bytes, filename, mime,
                    noise_reduce=enable_noise_reduce,
                    on_progress=_on_progress,
                )
            finally:
                if hb_stop is not None:
                    hb_stop.set()
            with Session(engine) as session:
                set_progress(session, rec_id, 100, note="finalizing")
                rec2 = crud.get_recording(session, rec_id)
                if rec2 is not None and rec2.progress_note is not None:
                    rec2.progress_note = None
                    session.add(rec2)
                    session.commit()

        text = result["text"]
        duration = result["duration"]
        language = result["language"]
        segments = result["segments"]

        # Change 161: Chunk-Overlap-Dopplungen präventiv entfernen — direkt
        # nach der ASR, VOR Diarization/Aligner/DB. ps-pk-onnx transkribiert
        # an 120-s-Chunk-Grenzen dieselbe Wortfolge doppelt (Live-Befund
        # Recording 8976aa1b bei 8:40); ohne diesen Schritt würde der doppelte
        # Text 1:1 persistiert und müsste später post-hoc repariert werden.
        segments, text = dedupe_repeated_word_runs(segments, text)
        phase_times[f"asr:{backend}"] = (time.perf_counter() - _t_asr0) * 1000

        # Change 147: Marker prüfen + Marker-Segmente entfernen. Die
        # Change 147: Vollständigkeits-Erkennung — Chunk-Zählung (primär,
        # deterministisch: endet der Stream vor total_chunks, ist die
        # Verbindung abgerissen). TTS-Marker nur als Fallback für
        # Backends ohne brauchbare Chunk-Zählung (total_chunks == 1).
        if result.get("truncated") and status == "done":
            chunks = result.get("chunks_received", 0)
            total = result.get("chunks_total", 0)
            log.warning(
                "Change 147: ASR-Stream vorzeitig beendet — rec_id=%s "
                "chunks=%s/%s", rec_id, chunks, total,
            )
            error = (
                f"Transkription unvollständig: Der ASR-Stream endete "
                f"vorzeitig ({chunks} von {total} Chunks). Bitte erneut "
                f"transkribieren."
            )
            status = "failed"
        elif marker_active and not result.get("chunked") and status == "done":
            # Fallback: Marker-Zeitprüfung (Audio-Dauer MIT Marker vs.
            # letztes Segment-Ende — kein Abspann-Risiko).
            audio_total_s = _probe_audio_duration(audio_bytes)
            segments, text, marker_found = _strip_transcript_marker(
                segments, text, audio_total_s,
            )
            if not marker_found and not _transcript_complete(
                segments, audio_total_s,
            ):
                log.warning(
                    "Change 147: ASR-Marker fehlt — Stream vorzeitig "
                    "beendet? rec_id=%s segments=%d audio_total=%.1fs",
                    rec_id, len(segments), audio_total_s or 0.0,
                )
                error = (
                    "Transkription unvollständig: Die ASR hat das Audio-Ende "
                    "nicht erreicht (Verbindung abgebrochen). Bitte erneut "
                    "transkribieren."
                )
                status = "failed"

        # Cancel-Prüfung nach ASR: teuerste Phasen (Diar/Align) nicht starten
        if _cancelled(job, rec_id):
            _abort_recording(rec_id, "Abgebrochen (User-Cancel)")
            return

        # Optional speaker diarization — merge labels into segments
        _t_diar0 = time.perf_counter()
        if enable_diarize:
            log.info("Diarization ENABLED for rec_id=%s — calling run_diarization(%s)", rec_id, audio_path)
            # Sichtbares Feedback: ASR ist fertig, Diarization läuft (kann Minuten dauern)
            with Session(engine) as session:
                set_progress(session, rec_id, 0, note="diarization")
            # Change 011/151: Heartbeat tickt last_heartbeat_at; der echte
            # Fortschritt kommt via /progress (Change 150, on_progress unten).
            hb_stop_d = _start_heartbeat(rec_id, 0, "diarization")
            # Zeitbasis: Bei VAD-Verarbeitung (trim/squash, Change 114) arbeiten
            # ASR/Aligner auf dem verarbeiteten Audio — die Diarization muss
            # DASSELBE Audio bekommen, sonst sind die Speaker-Zeiten versetzt
            # und die Zuordnung über Wort-Überlappung wird falsch.
            diar_path = str(audio_path)
            _tmp_wav = None
            try:
                if vad_meta:
                    _tmp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                    _tmp_wav.write(audio_bytes)
                    _tmp_wav.close()
                    diar_path = _tmp_wav.name
                diar = _run_diarization(
                    diar_path,
                    num_speakers=run_diarize_num_speakers,
                    min_duration_off=run_diarize_min_duration_off,
                    on_progress=lambda pct: _report_diar_progress(rec_id, pct),
                    method=run_diarize_method,
                )
                log.info("Diarization returned %d segments for rec_id=%s", len(diar or []), rec_id)
            except DiarizationError as exc_d:
                # Change 157: Ein Diar-Fehler (z.B. Service nicht erreichbar,
                # gated/Token) darf die fertige Transkription nicht vernichten.
                # Degradieren: Run bleibt done (Text+Segmente), der Fehler wird
                # sichtbar auf dem Recording angezeigt (diar_status=failed +
                # error). Kein stilles Verschlucken — der Hinweis ist da.
                log.warning(
                    "process_recording rec_id=%d diarization degraded (%s): %s",
                    rec_id, exc_d.code, exc_d.message,
                )
                diar = None
                diar_error = exc_d.message
            except ImportError as exc_d:
                # Programmierfehler (z. B. falscher relativer Import) — NICHT
                # als "diar=None" verschlucken, sonst wirkt Diarize deaktiviert
                # (Live-Befund 2026-08-16: `from ..audio_utils` → ImportError
                # bei jedem MP3-Upload → 0 Speaker, Status trotzdem done).
                log.exception("Diarization ImportError rec_id=%s (Code-Fehler!): %s", rec_id, exc_d)
                raise
            except Exception as exc_d:
                log.exception("Diarization threw for rec_id=%s: %s", rec_id, exc_d)
                diar = None
            finally:
                if _tmp_wav is not None:
                    try:
                        os.unlink(diar_path)
                    except OSError:
                        pass
                # Change 011: Diarization-Heartbeat stoppen.
                hb_stop_d.set()
                # Diarization-Phase beendet — Hinweis zurücksetzen (97% = fertig)
                from .models import Recording as _Rec

                with Session(engine) as session:
                    rec2 = session.get(_Rec, rec_id)
                    if rec2 is not None:
                        rec2.progress_pct = 97
                        rec2.progress_note = None
                        session.add(rec2)
                        session.commit()
        else:
            diar = None
        # Change 124: Cancel/Timeout NACH der blockierenden Diar-Phase prüfen
        # — vorher wurde erst nach dem Call (Minuten!) weitergearbeitet und
        # der Job lief trotz Cancel bis zum Save durch.
        if _abort_if_cancelled(job, rec_id):
            return
        if enable_diarize:
            phase_times[f"diar:{run_diarize_method or 'pyannote'}"] = (
                time.perf_counter() - _t_diar0
            ) * 1000
        if diar:
            word_stream = _build_word_stream(segments or [], duration)
            merged = _merge_diarization(segments or [], diar, word_stream,
                                        duration, full_text=text)
            if merged:
                segments = merged
                log.info("Speaker merge: %d/%d segments labeled for rec_id=%s",
                         len(merged), len(merged), rec_id)
            else:
                log.warning("Diarization returned no text-mapped segments "
                            "for rec_id=%s (falling back to ASR segments)", rec_id)
        # Change 045: Forced Alignment (Karaoke-Word-Sync) läuft NICHT mehr
        # synchron — der User sieht die Transkription sofort mit den
        # Backend-/linear verteilten Word-Timestamps (_build_word_stream).
        # Das präzise Alignment startet nach "done" im Hintergrund-Worker
        # (AlignmentCache schreibt die verarbeiteten Bytes für ihn).
        from .aligner_client import ALIGN_WORDS_ENABLED

        if ALIGN_WORDS_ENABLED and segments:
            # Cache-Bytes = verarbeitete Audio (nach Trim/Enhance/Konvertierung)
            # — exakt die Zeitbasis des synchronen Align-Laufs. vad_meta
            # (shift/map, Change 114) als Sidecar, damit der Worker die
            # kompensierten Segment-Zeiten vor dem Align zurückrechnen kann.
            _AlignmentCache.write(rec_id, audio_bytes, vad_meta)
            alignment_pending = True
        else:
            alignment_pending = False

        # VAD-Trim kompensieren: ASR/Aligner liefen auf dem verarbeiteten
        # Audio, das Playback nutzt die Originaldatei → alle Timestamps auf
        # die Original-Zeitbasis schieben/remappen (Wort-Klick spielt sonst
        # den Ton einer früheren Stelle). (2026-08-14 / Change 114)
        if vad_meta and vad_meta.get("type") == "shift":
            _shift_segments(segments, float(vad_meta["offset_s"]))
            if duration is not None:
                duration = duration + float(vad_meta["offset_s"])
            log.info("Trim-Offset kompensiert: rec_id=%s +%.2fs auf %d Segmente",
                     rec_id, vad_meta["offset_s"], len(segments))
        elif vad_meta and vad_meta.get("type") == "map":
            _shift_or_remap(segments, vad_meta)
            if duration is not None:
                mapping = vad_meta.get("mapping", [])
                if mapping:
                    duration = max(duration, float(mapping[-1][1]))
            log.info("Squash-Offset kompensiert: rec_id=%s (%d Regionen)",
                     rec_id, len(vad_meta.get("mapping", [])))

        # Waveform-Peaks: bewusst NICHT hier — der synchrone Voll-Decode
        # (bis zu 600 s bei langen Dateien) haengte den Job nach der
        # Align-Phase minutenlang bei 99%. Die Peaks liefert der
        # _schedule_peaks-Thread (non-blocking, nach Upload/Enqueue) bzw. der
        # Nachzug bei GET /recordings. update_result mit waveform_peaks=None
        # ueberschreibt vorhandene Peaks nicht (crud-Guard).
        peaks = None

        # Optional post-processing (A12/A13) — nur wenn per Toggle aktiviert,
        # niemals automatisch. Stubs: Implementierung in Phase 1–2.
        # CrispASR-Backends (crispr-ark/crispr-qwen3) liefern Interpunktion +
        # deutsches Truecasing nativ vom Server (--punc-model fullstop,
        # --truecase-model lstm) — dort KEINE LLM-Punctuation nachschalten,
        # sonst doppelte/konkurrierende Interpunktion.
        native_punct = bool(getattr(client.capabilities, "native_punctuation", False))
        # Change 035: LLM-Phasen (Interpunktion/Enhance/Template) können
        # Minuten dauern und haben keinen Zähler — ohne Heartbeat friert die
        # UI bei 95% ein und zeigt nach 45 s eine FALSCHE Stall-Warnung.
        # note "postprocessing" + Heartbeat, bis der letzte LLM-Call endet.
        hb_stop_llm: Optional[threading.Event] = None
        _llm_work = (
            (enable_punctuation and not native_punct
             and settings.POLYSCHNACK_PUNCTUATION_MODE != "off")
            or enable_llm_enhance or prompt_template_id or llm_endpoint_id
        )
        if _llm_work:
            _t_punc0 = time.perf_counter()
            with Session(engine) as session:
                set_progress(session, rec_id, 95, note="postprocessing")
            hb_stop_llm = _start_heartbeat(rec_id, 95, "postprocessing")
        try:
            if enable_punctuation and not native_punct and settings.POLYSCHNACK_PUNCTUATION_MODE != "off":
                text = run_punctuation(text, settings.POLYSCHNACK_PUNCTUATION_MODE)
            if enable_llm_enhance:
                text, segments = run_llm_enhance(text, segments)

            # Post-Processing mit Prompt-Template (Task D4) — LLM, nur bei Auswahl
            if prompt_template_id or enable_llm_enhance or llm_endpoint_id:
                with Session(engine) as s:
                    from . import llm as llm_mod
                    from .crypto import decrypt
                    from .models import PromptTemplate, UserLlmEndpoint

                    endpoint = None
                    if llm_endpoint_id:
                        ep = s.get(UserLlmEndpoint, llm_endpoint_id)
                        if ep is None:
                            raise RuntimeError("llm endpoint not found")
                        endpoint = {"base_url": ep.base_url,
                                    "api_key": decrypt(ep.api_key), "model": ep.model}
                    if prompt_template_id:
                        tpl = s.get(PromptTemplate, prompt_template_id)
                        if tpl is None:
                            raise RuntimeError("prompt template not found")
                        text = llm_mod.chat(tpl.prompt, text or "", endpoint=endpoint)
                    elif enable_llm_enhance and endpoint:
                        # run_llm_enhance lief bereits oben (Review 2026-08-15,
                        # P1: Doppel-Aufruf = doppelte Latenz + Token-Kosten).
                        # Hier nur noch der optionale Endpoint-Polish.
                        text = llm_mod.chat(
                            "Verbessere folgenden Transkript-Text (keine Einleitung):",
                            text or "", endpoint=endpoint)
        finally:
            if hb_stop_llm is not None:
                hb_stop_llm.set()
            if _llm_work:
                phase_times["punc_truecase"] = (time.perf_counter() - _t_punc0) * 1000
    except DiarizationError as exc_d:
        # Präzise Diarization-Fehlermeldung (gated, no-token, …) —
        # ohne TypeName-Prefix, damit der User den Admin-Hinweis direkt liest.
        status = "failed"
        error = exc_d.message
        log.exception("process_recording rec_id=%d diarization failed (%s)", rec_id, exc_d.code)
    except Exception as exc:  # broad catch: any I/O or HTTP failure marks the row failed
        status = "failed"
        error = f"{type(exc).__name__}: {exc}"
        log.exception("process_recording rec_id=%d failed", rec_id)
    finally:
        # Change 047: Job-Heartbeat stoppen — Job ist beendet (done/failed),
        # kein weiteres Ticken (sonst wuerde ein alter Heartbeat nach einem
        # Re-Transcribe den frischen ueberschreiben).
        if hb_job is not None:
            hb_job.set()

    elapsed_ms = (time.perf_counter() - t0) * 1000

    with Session(engine) as session:
        crud.update_result(
            session,
            rec_id,
            status=status,
            text=text,
            duration_s=duration,
            language=language,
            segments=segments if segments else None,
            processing_ms=elapsed_ms,
            error=error,
            waveform_peaks=peaks,
            phase_times_ms=phase_times or None,
        )
        # Change 157: Diar-Fehler degradieren statt Run abbrechen — die
        # fertige Transkription bleibt (status done), der Fehler wird auf dem
        # Recording sichtbar (diar_status=failed + error-Hinweis auf der
        # Karte). Kein stiller Fehler.
        if status == "done" and diar_error:
            rec3 = crud.get_recording(session, rec_id)
            if rec3 is not None:
                rec3.diar_status = "failed"
                rec3.error = diar_error[:500]
                session.add(rec3)
                session.commit()
        # Change 094 (runs → results): Run/Result-Abschluss — bei done
        # hängt das Ergebnis am Run (TranscriptionResult), Zeiger auf dem
        # Recording; bei failed/Fehler wird der aktive Run markiert.
        if status == "done" or error:
            rec2 = crud.get_recording(session, rec_id)
            if rec2 is not None and rec2.current_run_id:
                from .models import (
                    TranscriptionRun as _Run,
                    TranscriptionResult as _Result,
                )
                run = session.get(_Run, rec2.current_run_id)
                if run is not None:
                    if status == "done":
                        result = _Result(
                            run_id=run.id,
                            text=text or None,
                            segments=segments if segments else None,
                            created_by_user_id=owner_id,
                        )
                        session.add(result)
                        session.flush()
                        run.status = "done"
                        run.duration_s = duration
                        run.language = language or run.language
                        rec2.current_result_id = result.id
                    else:
                        run.status = "failed"
                        run.error = (error or "Unbekannter Fehler")[:500]
                    run.finished_at = datetime.now(timezone.utc)
                    session.add(run)
                    session.add(rec2)
                    # Explizit committen: im failed-Pfad folgt KEIN snapshot()/
                    # delivery-Commit mehr — ohne diesen Commit bliebe der Run
                    # ewig "processing".
                    session.commit()
        if status == "done":
            rec = crud.get_recording(session, rec_id)
            if rec:
                from .versions import list_versions, snapshot

                prior = list_versions(session, rec_id)
                snapshot(
                    session, rec, "retranscribe" if prior else "transcribe",
                    user_id=owner_id,
                )
                if prompt_template_id and rec.text is not None:
                    snapshot(session, rec, "postprocess", user_id=owner_id)
                if delivery_target_id:  # Change 099: aus dem Run
                    from .deliver import deliver
                    from .models import DeliveryTarget

                    target = session.get(DeliveryTarget, delivery_target_id)
                    if target is None:
                        rec.delivery_status, rec.delivery_error = "failed", "target not found"
                    else:
                        try:
                            deliver(rec, target)
                            rec.delivery_status, rec.delivery_error = "done", None
                        except Exception as exc:
                            rec.delivery_status = "failed"
                            rec.delivery_error = f"{type(exc).__name__}: {exc}"[:500]
                    session.add(rec)
                    session.commit()
                # Change 045: Hintergrund-Alignment — sobald der Job "done"
                # ist, wird das präzise Forced-Alignment als eigener
                # Queue-Job (kind=align, eigener Key) eingereiht — Change 155:
                # universelles Scheduling statt nacktem Thread. Der Worker
                # bereitet das Audio selbst vor und aktualisiert die Segmente
                # per Versions-Guard. Nie ein Job-Fail, nie blockierend.
                if alignment_pending:
                    from .queue import QueueError, queue_manager

                    try:
                        queue_manager.enqueue(
                            rec_id, user_id=None, backend=rec.backend or "",
                            kind="align", key=f"align-{rec_id}",
                        )
                    except QueueError as exc:
                        log.warning("bg-align: enqueue fehlgeschlagen rec_id=%s: %s", rec_id, exc)

    # Change 085: Phasen-Stichproben in den ETA-Learner einspeisen (eigene
    # Session; ein Fehler darf den Job-Abschluss nie blockieren).
    if status == "done" and phase_times:
        try:
            from . import learner_store
            digest = None
            if any(k.startswith("asr:") for k in phase_times):
                digest = _backend_image_digest(backend)
            learner_store.ingest_job_sample(rec_id, phase_times, duration,
                                            digest=digest)
        except Exception:
            log.warning("rtf_learner: ingest failed for rec_id=%s", rec_id,
                        exc_info=True)


# ---------------------------------------------------------------------------
# Subtitle / export helpers
# ---------------------------------------------------------------------------


def to_srt(segments: List[Dict[str, Any]]) -> str:
    """Convert a list of segment dicts into an SRT subtitle string.

    Change 008: delegiert an das eingebaute ``srt.json``-Template
    (Template-Renderer ist die einzige Format-Implementierung).
    """
    from .export import BUNDLED_TEMPLATES_DIR, load_template, render_template

    tpl = load_template("srt", BUNDLED_TEMPLATES_DIR)
    return render_template(tpl, segments, {})


def to_vtt(segments: List[Dict[str, Any]]) -> str:
    """Convert a list of segment dicts into a WebVTT subtitle string.

    Change 008: delegiert an das eingebaute ``vtt.json``-Template.
    """
    from .export import BUNDLED_TEMPLATES_DIR, load_template, render_template

    tpl = load_template("vtt", BUNDLED_TEMPLATES_DIR)
    return render_template(tpl, segments, {})


def to_txt(text: str) -> str:
    """Return the plain transcript, normalising line endings."""
    return text.strip() + "\n"


def _bucket_text(
    bucket_words: List[Dict[str, Any]],
    seg_text: Optional[str],
    seg_start: float,
    seg_end: float,
    c0: int,
    is_last: bool,
) -> tuple[str, int]:
    """Change 140: Bucket-Text OHNE Textverlust.

    Rückgabe ``(text, next_c0)`` — ``next_c0`` = Zeichen-Start des
    Folgebuckets (nach der Wortgrenze), nur im Desync-Pfad relevant.

    Normal: Wort-Join (wie bisher). Weichen die Wörter vom Segment-Text ab
    (Desync — Aligner-Wörter decken den Text nicht ab, User-Befund
    ec98bfdf: Export kürzer als das Transkript), wird der Segment-Text
    proportional über die Bucket-Zeiten verteilt. ``c0`` ist der Zeichen-
    Start (vom vorherigen Bucket übergeben); der LETZTE Bucket bekommt den
    Rest bis zum Text-Ende. c1 wird auf die letzte Wortgrenze VOR der
    proportionalen Position gerundet — kein Wort wird an einer
    Bucket-Grenze getrennt; der Folgebucket beginnt bei c1+1 (lückenlos).
    """
    word_text = " ".join(str(w.get("word") or "") for w in bucket_words).strip()
    st = (seg_text or "").strip()
    if not st or word_text == st:
        return word_text, 0
    dur = max(seg_end - seg_start, 1e-6)
    be = float(bucket_words[-1].get("end") or bucket_words[0].get("start") or seg_start)
    c1 = len(st) if is_last else int(len(st) * max(be - seg_start, 0.0) / dur)
    if not is_last:
        sp = st.rfind(" ", c0, c1)
        if sp > c0:
            c1 = sp
    next_c0 = c1 + 1 if (not is_last and c1 < len(st) and st[c1] == " ") else c1
    return st[c0:c1].strip(), next_c0


def resegment_by_duration(
    segments: List[Dict[str, Any]],
    max_duration_s: float,
) -> List[Dict[str, Any]]:
    """Teilt die Wörter der Segmente in neue Segmente ≤ max_duration_s auf.

    Feature 2026-08-15 (User): In der Transkriptionsansicht soll die
    Segmentlänge wählbar sein; der Export (SRT/VTT) nutzt dieselbe
    Aufteilung wie die Preview. Basis sind die vorhandenen Wort-
    Timestamps — an Chunk-Grenzen entstandene Riesen-Segmente (~105 s)
    werden für Untertitel in kurze Blöcke zerlegt.

    Regeln:
    - Nur Wörter mit Timestamps werden aufgeteilt; fehlen sie (kein
      Karaoke), bleiben die Original-Segmente unverändert.
    - Ein Bucket endet, sobald (a) die Ziel-Dauer überschritten würde
      ODER (b) der Sprecher wechselt (Untertitel pro Sprecher sauber).
    - Mindestens 1 Wort pro Bucket (ein einzelnes langes Wort sprengt
      die Dauer bewusst nicht in zwei künstliche Hälften).
    - Text = Wörter verbunden; start/end aus erstem/letztem Wort.
    - Change 088: Segmente mit `_manual: true` (im Frontend gesetzte
      Markierung bei Grenz-Drag/Insert/Delete/Split) werden NICHT
      aufgeteilt — sie wandern unverändert in die Ausgabe. Nur
      unmarkierte Segmente werden nach max_duration_s zerlegt.
    - Change 140 (Desync-Schutz): Weichen die Wörter vom Segment-Text ab
      (Aligner-Wörter decken den Text nicht ab), wird der Segment-Text
      proportional über die Buckets verteilt — der Export verliert nie
      Text (User-Befund ec98bfdf).
    """
    if not segments or max_duration_s <= 0:
        return list(segments)

    out: List[Dict[str, Any]] = []

    for seg in segments:
        if seg.get("_manual") is True:
            out.append(seg)  # Original-Dict unverändert übernehmen
            continue
        if not seg.get("words"):
            # Keine Wort-Timestamps (kein Karaoke): nicht teilbar → Original.
            out.append(seg)
            continue
        seg_text = (seg.get("text") or "").strip()
        seg_start = float(seg.get("start") or 0.0)
        seg_end = float(seg.get("end") or seg_start)
        speaker = seg.get("speaker") or ""

        # Buckets für DIESES Segment sammeln (Grenzen aus den Wörtern).
        buckets: List[List[Dict[str, Any]]] = []
        cur: List[Dict[str, Any]] = []
        for w in seg.get("words") or []:
            item = dict(w)
            item["_speaker"] = speaker
            ws = float(item.get("start") or 0.0)
            we = float(item.get("end") or ws)
            if cur:
                first_s = float(cur[0].get("start") or 0.0)
                cur_speaker = cur[0].get("_speaker", "")
                overflow = (we - first_s) > max_duration_s
                speaker_change = item.get("_speaker", "") != cur_speaker
                if overflow or speaker_change:
                    buckets.append(cur)
                    cur = []
            cur.append(item)
        if cur:
            buckets.append(cur)

        # Texte zuteilen (Change 140: verlustfrei, auch bei Desync).
        c0 = 0
        for i, b in enumerate(buckets):
            start = float(b[0].get("start") or seg_start)
            end = float(b[-1].get("end") or start)
            spk = b[0].get("_speaker", "")
            is_last = i == len(buckets) - 1
            text, next_c0 = _bucket_text(b, seg_text, seg_start, seg_end, c0, is_last)
            if not is_last:
                c0 = next_c0
            seg_out: Dict[str, Any] = {
                "start": start,
                "end": end,
                "text": text,
                "words": [{k: v for k, v in x.items() if k != "_speaker"} for x in b],
            }
            if spk:
                seg_out["speaker"] = spk
            out.append(seg_out)
    return out


# ---------------------------------------------------------------------------
# Audio trimming (for crop — uses ffmpeg)
# ---------------------------------------------------------------------------


def trim_audio(audio_bytes: bytes, start: float, end: float) -> bytes:
    """FFmpeg-based audio trim — returns 16kHz mono WAV bytes."""
    with tempfile.NamedTemporaryFile(suffix=".in") as fin, \
         tempfile.NamedTemporaryFile(suffix=".wav") as fout:
        fin.write(audio_bytes)
        fin.flush()
        dur = end - start
        sp.run([
            "ffmpeg", "-y", "-i", fin.name,
            "-ss", str(start), "-t", str(dur),
            "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            fout.name,
        ], capture_output=True, check=True)
        return fout.read()
