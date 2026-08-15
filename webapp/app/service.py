"""Orchestration layer — coordinates file I/O, ASR calls, and DB writes.

``process_recording`` is the background function scheduled by the upload
endpoint.  Subtitle/text export helpers are also housed here.
"""
from __future__ import annotations

import logging
import os
import subprocess as sp
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlmodel import Session

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
MAX_ALIGN_GROUP_S = 380.0  # Sicherheitsmarge unter dem 400-s-Modell-Limit


def build_align_groups(segments: List[Dict[str, Any]], max_s: float = MAX_ALIGN_GROUP_S) -> List[tuple]:
    """Bündelt aufeinanderfolgende Segmente zu Align-Gruppen ≤ max_s.

    Returns: Liste von (start, end, text) in globalen Sekunden. Lücken
    (Pausen) zwischen Segmenten zählen zur Spanne — der Audio-Ausschnitt
    enthält sie, der Aligner verteilt die Wörter korrekt darüber.
    """
    groups: List[tuple] = []
    cur: Optional[list] = None
    for s in segments:
        start, end = s.get("start"), s.get("end")
        if start is None or end is None:
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
                     audio_name: str, language: Optional[str]) -> List[Dict[str, Any]]:
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
    """
    from .aligner_client import AlignerClient
    from .models import Recording as _Rec

    client = AlignerClient()
    if not client.health():
        log.info("align: crispr-align nicht erreichbar (rec_id=%s) — Backend-Timestamps behalten", rec_id)
        return segments

    with Session(engine) as session:
        set_progress(session, rec_id, 96, note="alignment")

    tmp_audio = ""
    aligned_any = False
    try:
        # Zeitbasis: die VERARBEITETE Audio (nach VAD-Trim/Enhance/Konvertierung)
        # — die Segment-Zeiten beziehen sich auf sie.
        with tempfile.NamedTemporaryFile(suffix=Path(audio_name).suffix or ".bin", delete=False) as tfh:
            tmp_audio = tfh.name
            tfh.write(audio_bytes)

        groups = build_align_groups(segments)
        for gi, (g_start, g_end, g_text) in enumerate(groups):
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
                    words = client.align(chunk_bytes, g_text, lang=language or "de")
                finally:
                    stop.set()
                    hb.join(timeout=1.0)

                if words:
                    segments = apply_aligned_words(segments, words, g_start)
                    aligned_any = True
                    log.info("align: rec_id=%s Gruppe %d/%d (%ds–%ds) → %d Wörter",
                             rec_id, gi + 1, len(groups), g_start, g_end, len(words))
                # Echter Gruppenfortschritt (96–99): die Phase kann bei langen
                # Audios 10–25 min dauern — kein starrer 96-Hinweis. Der note
                # traegt den Gruppen-Zaehler, die UI zeigt "Alignment…".
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
        with Session(engine) as session:
            rec2 = session.get(_Rec, rec_id)
            if rec2 is not None:
                # Loop-Max ist 99 — kein Rueckwaerts-Sprung auf 97 (die UI
                # wuerde sonst minutenlang auf 97% stehenbleiben).
                rec2.progress_pct = 99
                rec2.progress_note = None
                session.add(rec2)
                session.commit()

    if aligned_any:
        log.info("align: Word-Timestamps für rec_id=%s ersetzt", rec_id)
    return segments


def process_recording(rec_id: int, backend: Optional[str] = None) -> None:
    """Load row → read audio → call ASR → persist result.

    Designed to run in a background thread (queue worker, Task 6). The
    backend comes from the bound job; falls back to the recording's own
    ``backend`` field. All exceptions are caught so a transient failure
    cannot crash the worker; the row is updated to status='failed' with the
    error message.
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

    log.info("process_recording rec_id=%s: vad=%s diarize=%s streaming=%s noise=%s",
             rec_id, enable_vad, enable_diarize, enable_streaming, enable_noise_reduce)

    t0 = time.perf_counter()
    status = "done"
    text: str = ""
    duration = None
    language = None
    segments: List[Dict[str, Any]] = []
    error = None
    peaks = None

    try:
        audio_bytes = audio_path.read_bytes()
        trim_offset_s = 0.0

        # Mark progress: 10% — loaded
        with Session(engine) as session:
            set_progress(session, rec_id, 10, note="preparing")

        # Optional VAD silence trimming
        if _VAD_TRIM and enable_vad:
            with Session(engine) as session:
                set_progress(session, rec_id, 12, note="vad")
            audio_bytes, trim_offset_s = _trim_silence(audio_bytes)
            if trim_offset_s > 0:
                log.info("VAD trim: rec_id=%s offset=%.2fs", rec_id, trim_offset_s)

        # Optional audio enhancement (ffmpeg filters before ASR)
        if enable_enhance and enable_enhance != "off":
            with Session(engine) as session:
                set_progress(session, rec_id, 16, note="enhance")
            log.info("Enhance: rec_id=%s level=%s", rec_id, enable_enhance)
            enhanced = enhance_audio(audio_bytes, level=enable_enhance)
            if len(enhanced) != len(audio_bytes):
                log.info("Enhance: rec_id=%s %d→%d bytes", rec_id, len(audio_bytes), len(enhanced))
            audio_bytes = enhanced

        with Session(engine) as session:
            set_progress(session, rec_id, 20, note="asr")

        # Run ASR (batched sync or SSE streaming)
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
            if not getattr(client.capabilities, "async_jobs", False):
                with Session(engine) as session:
                    set_progress(session, rec_id, 21, note="asr")
            result = client.transcribe_async(
                audio_bytes, filename, mime,
                noise_reduce=enable_noise_reduce,
                on_progress=_on_progress,
            )
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

        # Optional speaker diarization — merge labels into segments
        if enable_diarize:
            log.info("Diarization ENABLED for rec_id=%s — calling run_diarization(%s)", rec_id, audio_path)
            # Sichtbares Feedback: ASR ist fertig, Diarization läuft (kann Minuten dauern)
            with Session(engine) as session:
                set_progress(session, rec_id, 96, note="diarization")
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
            except Exception as exc_d:
                log.exception("Diarization threw for rec_id=%s: %s", rec_id, exc_d)
                diar = None
            finally:
                if _tmp_wav is not None:
                    try:
                        os.unlink(diar_path)
                    except OSError:
                        pass
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
        # Forced Alignment (Karaoke-Word-Sync): präzise Word-Timestamps gegen
        # die Akustik (crispr-align). Ersetzt die groben Backend-Timestamps,
        # die über Chunk-Grenzen driften. Optional — nie ein Job-Fail.
        from .aligner_client import ALIGN_WORDS_ENABLED

        if ALIGN_WORDS_ENABLED and segments:
            segments = _run_align_phase(
                rec_id, segments, audio_bytes, audio_path.name, language
            )

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
                elif enable_llm_enhance:
                    text, segments = run_llm_enhance(text, segments)
                    if endpoint:
                        text = llm_mod.chat(
                            "Verbessere folgenden Transkript-Text (keine Einleitung):",
                            text or "", endpoint=endpoint)
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


# ---------------------------------------------------------------------------
# Subtitle / export helpers
# ---------------------------------------------------------------------------


def _format_timestamp_srt(seconds: float) -> str:
    """Format *seconds* as an SRT timestamp ``HH:MM:SS,mmm``."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _format_timestamp_vtt(seconds: float) -> str:
    """Format *seconds* as a WebVTT timestamp ``HH:MM:SS.mmm``."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def to_srt(segments: List[Dict[str, Any]]) -> str:
    """Convert a list of segment dicts into an SRT subtitle string."""
    lines: List[str] = []
    for i, seg in enumerate(segments, start=1):
        start = _format_timestamp_srt(float(seg.get("start", 0)))
        end = _format_timestamp_srt(float(seg.get("end", 0)))
        speaker = seg.get("speaker", "")
        prefix = f"[{speaker}] " if speaker else ""
        text = prefix + seg.get("text", "").strip()
        lines.append(f"{i}\n{start} --> {end}\n{text}\n")
    return "\n".join(lines)


def to_vtt(segments: List[Dict[str, Any]]) -> str:
    """Convert a list of segment dicts into a WebVTT subtitle string."""
    lines: List[str] = ["WEBVTT\n"]
    for seg in segments:
        start = _format_timestamp_vtt(float(seg.get("start", 0)))
        end = _format_timestamp_vtt(float(seg.get("end", 0)))
        speaker = seg.get("speaker", "")
        prefix = f"[{speaker}] " if speaker else ""
        text = prefix + seg.get("text", "").strip()
        lines.append(f"{start} --> {end}\n{text}\n")
    return "\n".join(lines)


def to_txt(text: str) -> str:
    """Return the plain transcript, normalising line endings."""
    return text.strip() + "\n"


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
