"""Orchestration layer — coordinates file I/O, ASR calls, and DB writes.

``process_recording`` is the background function scheduled by the upload
endpoint.  Subtitle/text export helpers are also housed here.
"""
from __future__ import annotations

import logging
import math
import os
import subprocess as sp
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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


def _trim_silence(audio_bytes: bytes) -> Tuple[bytes, float]:
    """VAD-Trim: entfernt führende/trailing Stille.

    Returns (getrimmte_bytes, offset_s) — offset_s sind die am Anfang
    entfernten Sekunden (0.0 ohne Trim). Der Offset ist nötig, um die
    Timestamps am Ende auf die Original-Zeitbasis zu schieben (das
    Playback nutzt die Originaldatei). (2026-08-14)
    """
    from .vad import trim_silence_with_offset
    return trim_silence_with_offset(audio_bytes)


def _run_diarization(audio_path: str, num_speakers: Optional[int] = None,
                     min_duration_off: Optional[float] = None,
                     method: Optional[str] = None) -> list:
    from .diarize import diarize
    return diarize(audio_path, num_speakers=num_speakers,
                   min_duration_off=min_duration_off, method=method)


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

_VAD_TRIM = os.getenv("VAD_TRIM_SILENCE", "false").lower() in ("true", "1", "yes")
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
            set_progress(session, rec_id, 96, note="alignment")

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
                                        96 + int((gi + 1) / len(groups) * 3.99),
                                        note=note,
                                    )
                        stop.wait(3.0)

                hb = threading.Thread(target=_heartbeat, daemon=True, name=f"align-hb-{gi}")
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
        segments = apply_aligned_words(segments, all_aligned_words, 0.0)
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
    def write(cls, rec_id: int, audio_bytes: bytes, trim_offset_s: float = 0.0) -> None:
        try:
            import json as _json

            cls._ensure_dir()
            cls.path(rec_id).write_bytes(audio_bytes)
            cls.meta_path(rec_id).write_text(
                _json.dumps({"trim_offset_s": trim_offset_s})
            )
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
        """trim_offset_s des Jobs (0.0 wenn unbekannt/fehlt)."""
        try:
            import json as _json

            p = cls.meta_path(rec_id)
            if p.is_file():
                return float(_json.loads(p.read_text()).get("trim_offset_s", 0.0))
        except Exception:
            pass
        return 0.0

    @classmethod
    def delete(cls, rec_id: int) -> None:
        try:
            for p in (cls.path(rec_id), cls.meta_path(rec_id)):
                if p.is_file():
                    p.unlink()
        except Exception as exc:
            log.warning("align-cache: delete failed rec_id=%s: %s", rec_id, exc)


def _run_background_align(rec_id: int) -> None:
    """Hintergrund-Worker (Change 045): präzises Forced-Alignment nach „done".

    - Setzt ``alignment``: pending → running → done|skipped.
    - Liest das Cache-Audio (verarbeitete Bytes = Zeitbasis der Segmente).
    - Versions-Guard: wurden die Segmente seit dem Job geändert (Edit,
      Re-Transcribe), wird das Ergebnis verworfen (nie fremde Edits
      überschreiben).
    - Fehler (Cache weg, Aligner down): ``skipped``, Backend-Timestamps
      bleiben — nie ein Job-Fail.
    """
    from .aligner_client import ALIGN_WORDS_ENABLED
    from .models import Recording as _Rec

    if not ALIGN_WORDS_ENABLED:
        return

    audio_bytes = _AlignmentCache.read(rec_id)
    if audio_bytes is None:
        try:
            with Session(engine) as session:
                rec = session.get(_Rec, rec_id)
                if rec is not None and rec.alignment == "pending":
                    rec.alignment = "skipped"
                    session.add(rec)
                    session.commit()
        except Exception as exc:
            log.warning("bg-align: Cache fehlt, Status-Update fehlgeschlagen (rec_id=%s): %s", rec_id, exc)
        log.info("bg-align: Cache fehlt für rec_id=%s — skipped", rec_id)
        return

    # Baseline der Segmente (für den Versions-Guard) + Job-Parameter.
    try:
        with Session(engine) as session:
            rec = session.get(_Rec, rec_id)
            if rec is None or rec.status != "done":
                _AlignmentCache.delete(rec_id)
                return
            segments: List[Dict[str, Any]] = _json_deepcopy(rec.segments or [])
            language = rec.language
            # Cache-Bytes sind die VERARBEITETE Audio (nach Trim/Enhance) — der
            # Aligner bekommt sie direkt. Nur die Segment-Zeiten sind im Job um
            # trim_offset_s kompensiert → vor dem Align abziehen, danach wieder
            # aufschlagen (identische Zeitbasis wie der synchrone Lauf).
            trim_offset_s = _AlignmentCache.read_meta(rec_id)
            if trim_offset_s > 0:
                _shift_segments(segments, -trim_offset_s)
            rec.alignment = "running"
            session.add(rec)
            session.commit()
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
        if trim_offset_s > 0:
            _shift_segments(new_segments, trim_offset_s)
    except Exception as exc:
        log.warning("bg-align: rec_id=%s failed: %s", rec_id, exc)
        new_segments = None

    try:
        with Session(engine) as session:
            rec = session.get(_Rec, rec_id)
            if rec is None:
                _AlignmentCache.delete(rec_id)
                return
            if new_segments is not None and _same_segments(rec.segments, segments):
                rec.segments = new_segments
                rec.alignment = "done"
            elif new_segments is not None:
                log.info("bg-align: Segmente geändert während des Laufs (rec_id=%s) — Ergebnis verworfen", rec_id)
                rec.alignment = "skipped"
            else:
                rec.alignment = "skipped"
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


def _schedule_realign(rec_id: int) -> bool:
    """Change 046: Re-Alignment auf dem aktuellen (ggf. korrigierten) Text.

    Lädt die gespeicherte Audiodatei, reproduziert VAD-Trim/Enhance wie im
    Job (gleiche Zeitbasis), schreibt den Alignment-Cache und startet den
    Hintergrund-Worker (_run_background_align). Der User kann die
    Transkription weiter sehen/bearbeiten; die Word-Timestamps werden
    akustisch verifiziert, sobald der Worker fertig ist.

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
        try:
            audio_bytes = stored.read_bytes()
        except Exception as exc:
            log.warning("realign: Audio nicht lesbar rec_id=%s: %s", rec_id, exc)
            return False
        trim_offset_s = 0.0
        if _VAD_TRIM and rec.enable_vad:
            try:
                audio_bytes, trim_offset_s = _trim_silence(audio_bytes)
            except Exception:
                trim_offset_s = 0.0
        if rec.enable_enhance and rec.enable_enhance != "off":
            try:
                audio_bytes = enhance_audio(audio_bytes, level=rec.enable_enhance)
            except Exception as exc:
                log.warning("realign: enhance failed rec_id=%s: %s", rec_id, exc)
        rec.alignment = "pending"
        session.add(rec)
        session.commit()

    _AlignmentCache.write(rec_id, audio_bytes, trim_offset_s)
    threading.Thread(
        target=_run_background_align,
        args=(rec_id,),
        daemon=True,
        name=f"realign-{rec_id}",
    ).start()
    log.info("realign: rec_id=%s Worker gestartet", rec_id)
    return True


# ---------------------------------------------------------------------------
# Change 057 — Re-Diarize (Sprecher-Zuordnung neu berechnen)
# ---------------------------------------------------------------------------


def _schedule_rediarize(rec_id: int) -> bool:
    """Change 057: Diarization auf dem aktuellen Audio neu berechnen.

    Analog ``_schedule_realign``: lädt die gespeicherte Audiodatei,
    reproduziert VAD-Trim/Enhance (gleiche Zeitbasis wie beim Job) und
    startet den Hintergrund-Worker ``_run_background_rediarize``. Ersetzt
    NUR die ``speaker``-Felder der Segmente — Text, Wörter, Timestamps,
    manuelle Aufteilung und Alignment bleiben unangetastet.

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
        try:
            audio_bytes = stored.read_bytes()
        except Exception as exc:
            log.warning("rediarize: Audio nicht lesbar rec_id=%s: %s", rec_id, exc)
            return False
        trim_offset_s = 0.0
        if _VAD_TRIM and rec.enable_vad:
            try:
                audio_bytes, trim_offset_s = _trim_silence(audio_bytes)
            except Exception:
                trim_offset_s = 0.0
        if rec.enable_enhance and rec.enable_enhance != "off":
            try:
                audio_bytes = enhance_audio(audio_bytes, level=rec.enable_enhance)
            except Exception as exc:
                log.warning("rediarize: enhance failed rec_id=%s: %s", rec_id, exc)
        rec.diar_status = "pending"
        session.add(rec)
        session.commit()

    threading.Thread(
        target=_run_background_rediarize,
        args=(rec_id, audio_bytes, trim_offset_s),
        daemon=True,
        name=f"rediarize-{rec_id}",
    ).start()
    log.info("rediarize: rec_id=%s Worker gestartet", rec_id)
    return True


def _run_background_rediarize(rec_id: int, audio_bytes: bytes, trim_offset_s: float) -> None:
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
        num_speakers = rec.diarize_num_speakers
        min_duration_off = rec.diarize_min_duration_off
        method = rec.diarize_method
        rec.diar_status = "running"
        # Ehrlicher Status-Hinweis (kein Fake-Progress); wird am Ende
        # (done/skipped/failed) wieder geräumt.
        rec.progress_note = "Re-Diarize läuft …"
        session.add(rec)
        session.commit()

    try:
        _tmp_wav = None
        diar_path = None
        try:
            _tmp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            _tmp_wav.write(audio_bytes)
            _tmp_wav.close()
            diar_path = _tmp_wav.name
            diar = _run_diarization(
                diar_path,
                num_speakers=num_speakers,
                min_duration_off=min_duration_off,
                method=method,
            )
        finally:
            if _tmp_wav is not None and diar_path:
                try:
                    os.unlink(diar_path)
                except OSError:
                    pass
        if not diar:
            raise DiarizationError("empty", "Diarization lieferte keine Sprecher-Segmente")
        # Trim-Offset kompensieren: Segment-Zeiten liegen auf Original-Basis.
        diar_comp = [
            {
                **{k: v for k, v in d.items() if k not in ("start", "end")},
                "start": float(d["start"]) + trim_offset_s,
                "end": float(d["end"]) + trim_offset_s,
            }
            for d in diar
        ]
        word_stream = _build_word_stream(segments_before, duration)
        merged = _merge_diarization(segments_before, diar_comp, word_stream,
                                    duration, full_text=text)
        if not merged:
            raise DiarizationError("empty", "Keine text-zugeordneten Sprecher-Segmente")
    except Exception as exc:
        log.exception("rediarize: rec_id=%s fehlgeschlagen: %s", rec_id, exc)
        with Session(engine) as session:
            rec2 = session.get(_Rec, rec_id)
            if rec2 is not None:
                rec2.diar_status = "failed"
                rec2.progress_note = None
                session.add(rec2)
                session.commit()
        return

    with Session(engine) as session:
        rec2 = session.get(_Rec, rec_id)
        if rec2 is None:
            return
        # Versions-Guard: Segmente seit Job-Start geändert → verwerfen.
        if not _same_segments(rec2.segments or [], segments_before):
            log.info("rediarize: Segmente seit Start geändert — Ergebnis verworfen (rec_id=%s)", rec_id)
            rec2.diar_status = "skipped"
            rec2.progress_note = None
            session.add(rec2)
            session.commit()
            return
        rec2.segments = merged
        rec2.diar_status = "done"
        rec2.progress_note = None
        rec2.updated_at = datetime.now(timezone.utc)
        session.add(rec2)
        session.commit()
        log.info("rediarize: rec_id=%s Sprecher-Zuordnung aktualisiert (%d Segmente)",
                 rec_id, len(merged))


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
                session.add(rec)
                session.commit()
    except Exception:
        log.exception("abort: Status-Update fehlgeschlagen (rec_id=%s)", rec_id)


def _start_heartbeat(rec_id: int, pct: int, note: str,
                     interval_s: float = 5.0) -> threading.Event:
    """Heartbeat-Thread: tickt last_heartbeat_at, bis das Event gesetzt wird.

    Change 011 (2026-08-17): In Phasen ohne messbaren Fortschritt (Sync-ASR
    bei 21%, Diarization bei 96%) ruft dieser Thread periodisch
    ``set_progress`` mit DEMSELBEN pct/note auf — nur ``last_heartbeat_at``
    bewegt sich. Die UI zeigt damit „läuft, aktiv seit Xs" statt eines
    eingefrorenen Prozentwerts. Kein erfundener Fortschritt (pct bleibt
    konstant), kein Fehler-Schlucken: Exceptions werden geloggt, der Thread
    beendet sich dann.
    """
    stop = threading.Event()

    def _tick() -> None:
        while not stop.is_set():
            try:
                with Session(engine) as s:
                    # Change 035: aktuellen pct aus der DB übernehmen statt
                    # fix den Start-pct zu schreiben — wenn on_progress einen
                    # echten Zähler hochzieht, darf der Heartbeat ihn nicht
                    # zurücksetzen (nur last_heartbeat_at soll ticken).
                    from .models import Recording as _Rec

                    rec = s.get(_Rec, rec_id)
                    cur_pct = rec.progress_pct if rec is not None else pct
                    set_progress(s, rec_id, cur_pct, note=note)
            except Exception:
                log.exception("heartbeat: set_progress fehlgeschlagen (rec_id=%s)", rec_id)
                return
            stop.wait(interval_s)

    t = threading.Thread(
        target=_tick, daemon=True,
        name=f"heartbeat-{rec_id}",  # eindeutig pro Recording
    )
    t.start()
    return stop


def _start_job_heartbeat(rec_id: int, interval_s: float = 5.0) -> threading.Event:
    """Job-weiter Heartbeat (Change 047): tickt last_heartbeat_at über den
    GESAMTEN Job — auch in Phasen ohne eigenen Heartbeat (preparing/vad/
    enhance/16k-Konvertierung/Streaming-ASR).

    Befund 2026-08-20: Die phasen-spezifischen Heartbeats (asr/diar/llm)
    lassen Lücken — bei langen Audios (4h52m-YouTube) blockiert z. B. die
    WAV-Konvertierung Minuten OHNE Heartbeat → UI zeigt nach 45 s eine
    FALSCHE Stall-Warnung („keine Aktivität seit 120m"), obwohl der Job
    läuft. Auch nach komplett neuem Start wiederholte sich das (lange
    Datei → gleiche heartbeat-lose Phase).

    Der Job-Heartbeat übergibt ``note=None`` an set_progress → er tickt
    NUR last_heartbeat_at (+pct aus der DB) und überschreibt niemals die
    Phasen-Note der phasen-spezifischen Heartbeats. Kein Konflikt.
    """
    stop = threading.Event()

    def _tick() -> None:
        while not stop.is_set():
            try:
                with Session(engine) as s:
                    from .models import Recording as _Rec

                    rec = s.get(_Rec, rec_id)
                    cur_pct = rec.progress_pct if rec is not None else 1
                    set_progress(s, rec_id, cur_pct, note=None)
            except Exception:
                log.exception("job-heartbeat: set_progress fehlgeschlagen (rec_id=%s)", rec_id)
                return
            stop.wait(interval_s)

    t = threading.Thread(
        target=_tick, daemon=True,
        name=f"job-heartbeat-{rec_id}",
    )
    t.start()
    return stop


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
        enable_vad = rec.enable_vad
        enable_diarize = rec.enable_diarize
        enable_streaming = rec.enable_streaming
        enable_noise_reduce = rec.enable_noise_reduce
        enable_enhance = rec.enable_enhance
        enable_punctuation = rec.enable_punctuation
        enable_llm_enhance = rec.enable_llm_enhance
        prompt_template_id = rec.prompt_template_id
        delivery_target_id = rec.delivery_target_id
        llm_endpoint_id = rec.llm_endpoint_id
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
    peaks = None
    alignment_pending = False
    hb_job: Optional[threading.Event] = None

    try:
        audio_bytes = audio_path.read_bytes()
        trim_offset_s = 0.0

        # Change 047: Job-weiter Heartbeat — tickt last_heartbeat_at über
        # ALLE Phasen (auch preparing/vad/enhance/Konvertierung/Streaming),
        # nicht nur asr/diar/llm. Beendet im finally unten.
        hb_job = _start_job_heartbeat(rec_id)

        # Mark progress: 10% — loaded
        with Session(engine) as session:
            set_progress(session, rec_id, 10, note="preparing")

        # Optional VAD silence trimming
        if _VAD_TRIM and enable_vad:
            _t_vad0 = time.perf_counter()
            with Session(engine) as session:
                set_progress(session, rec_id, 12, note="vad")
            audio_bytes, trim_offset_s = _trim_silence(audio_bytes)
            phase_times["vad"] = (time.perf_counter() - _t_vad0) * 1000
            if trim_offset_s > 0:
                log.info("VAD trim: rec_id=%s offset=%.2fs", rec_id, trim_offset_s)

        # Optional audio enhancement (ffmpeg filters before ASR)
        if enable_enhance and enable_enhance != "off":
            _t_enh0 = time.perf_counter()
            with Session(engine) as session:
                set_progress(session, rec_id, 16, note="enhance")
            log.info("Enhance: rec_id=%s level=%s", rec_id, enable_enhance)
            enhanced = enhance_audio(audio_bytes, level=enable_enhance)
            if len(enhanced) != len(audio_bytes):
                log.info("Enhance: rec_id=%s %d→%d bytes", rec_id, len(audio_bytes), len(enhanced))
            audio_bytes = enhanced
            phase_times[f"enhance:{enable_enhance}"] = (time.perf_counter() - _t_enh0) * 1000

        with Session(engine) as session:
            set_progress(session, rec_id, 20, note="asr")

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
        if enable_streaming and client.capabilities.streaming:

            def _on_chunk(acc_text: str, idx: int, total: int, start: float, end: float, final: bool):
                pct = int((idx + 1) / total * 70) + 10
                with Session(engine) as session:
                    set_progress(session, rec_id, pct)
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
                # 95 statt 80: 80 war der Endwert der Streaming-Skala und wirkte
                # bei abgerissenen Streams wie ein Dauer-Hang. 95 signalisiert
                # „ASR fertig, Nachbearbeitung läuft" (konsistent zum Batch-Pfad).
                set_progress(session, rec_id, 95, note="finalizing")
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
                set_progress(session, rec_id, 95, note="finalizing")
                rec2 = crud.get_recording(session, rec_id)
                if rec2 is not None and rec2.progress_note is not None:
                    rec2.progress_note = None
                    session.add(rec2)
                    session.commit()

        text = result["text"]
        duration = result["duration"]
        language = result["language"]
        segments = result["segments"]
        phase_times[f"asr:{backend}"] = (time.perf_counter() - _t_asr0) * 1000

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
                set_progress(session, rec_id, 96, note="diarization")
            # Change 011: Heartbeat tickt last_heartbeat_at während der
            # Diarization (kein Fortschritts-Reporting vom Dienst) — die UI
            # zeigt „diarizing · aktiv seit Xs" statt eingefrorenem 96%.
            hb_stop_d = _start_heartbeat(rec_id, 96, "diarization")
            # Zeitbasis: Bei VAD-Trim arbeiten ASR/Aligner auf dem getrimmten
            # Audio — die Diarization muss DASSELBE Audio bekommen, sonst sind
            # die Speaker-Zeiten um trim_offset_s versetzt und die Zuordnung
            # über Wort-Überlappung wird falsch. (2026-08-14)
            diar_path = str(audio_path)
            _tmp_wav = None
            try:
                if trim_offset_s > 0:
                    _tmp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                    _tmp_wav.write(audio_bytes)
                    _tmp_wav.close()
                    diar_path = _tmp_wav.name
                diar = _run_diarization(
                    diar_path,
                    num_speakers=rec.diarize_num_speakers,
                    min_duration_off=rec.diarize_min_duration_off,
                    method=rec.diarize_method,
                )
                log.info("Diarization returned %d segments for rec_id=%s", len(diar or []), rec_id)
            except DiarizationError as exc_d:
                # Kein stilles Verschlucken: gated/Token-Fehler müssen als
                # failed mit Admin-Hinweis beim User ankommen.
                raise
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
        if enable_diarize:
            phase_times[f"diar:{rec.diarize_method or 'pyannote'}"] = (
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
            # — exakt die Zeitbasis des synchronen Align-Laufs. trim_offset_s
            # als Sidecar, damit der Worker die kompensierten Segment-Zeiten
            # vor dem Align zurückrechnen kann.
            _AlignmentCache.write(rec_id, audio_bytes, trim_offset_s)
            alignment_pending = True
        else:
            alignment_pending = False

        # VAD-Trim-Offset kompensieren: ASR/Aligner liefen auf dem getrimmten
        # Audio, das Playback nutzt die Originaldatei → alle Timestamps um die
        # entfernten Anfangs-Sekunden nach hinten schieben (Wort-Klick spielt
        # sonst den Ton einer früheren Stelle). (2026-08-14)
        if trim_offset_s > 0:
            _shift_segments(segments, trim_offset_s)
            if duration is not None:
                duration = duration + trim_offset_s
            log.info("Trim-Offset kompensiert: rec_id=%s +%.2fs auf %d Segmente",
                     rec_id, trim_offset_s, len(segments))

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
                if rec.delivery_target_id:
                    from .deliver import deliver
                    from .models import DeliveryTarget

                    target = session.get(DeliveryTarget, rec.delivery_target_id)
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
                # ist, startet der Worker das präzise Forced-Alignment
                # (liest das Cache-Audio, aktualisiert die Segmente per
                # Versions-Guard). Nie ein Job-Fail, nie blockierend.
                if alignment_pending:
                    threading.Thread(
                        target=_run_background_align,
                        args=(rec_id,),
                        daemon=True,
                        name=f"bg-align-{rec_id}",
                    ).start()

    # Change 085: Phasen-Stichproben in den ETA-Learner einspeisen (eigene
    # Session; ein Fehler darf den Job-Abschluss nie blockieren).
    if status == "done" and phase_times:
        try:
            from . import learner_store
            learner_store.ingest_job_sample(rec_id, phase_times, duration)
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
    """
    if not segments or max_duration_s <= 0:
        return list(segments)

    out: List[Dict[str, Any]] = []
    cur: List[Dict[str, Any]] = []

    def flush() -> None:
        if not cur:
            return
        start = float(cur[0].get("start") or 0.0)
        end = float(cur[-1].get("end") or start)
        speaker = cur[0].get("_speaker", "")
        text = " ".join(str(x.get("word") or "") for x in cur).strip()
        seg: Dict[str, Any] = {
            "start": start,
            "end": end,
            "text": text,
            "words": [{k: v for k, v in x.items() if k != "_speaker"} for x in cur],
        }
        if speaker:
            seg["speaker"] = speaker
        out.append(seg)
        cur.clear()

    for seg in segments:
        if seg.get("_manual") is True:
            flush()  # offenen Bucket vor dem manuellen Segment schließen
            out.append(seg)  # Original-Dict unverändert übernehmen
            continue
        if not seg.get("words"):
            # Keine Wort-Timestamps (kein Karaoke): nicht teilbar → Original.
            flush()
            out.append(seg)
            continue
        speaker = seg.get("speaker") or ""
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
                    flush()
            cur.append(item)
    flush()
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
