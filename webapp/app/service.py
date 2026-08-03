"""Orchestration layer — coordinates file I/O, ASR calls, and DB writes.

``process_recording`` is the background function scheduled by the upload
endpoint.  Subtitle/text export helpers are also housed here.
"""
from __future__ import annotations

import logging
import subprocess as sp
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlmodel import Session

from . import asr_client, crud
from .asr_client import get_client
from .config import settings
from .crud import get_or_create_user, get_user, set_progress
from .db import engine
from .diarize import DiarizationError
import os

# Heavy optional deps (onnxruntime/pyannote/torch) are imported lazily inside
# the functions so the module imports fast and the CI test job stays light.


def _trim_silence(audio_bytes: bytes) -> bytes:
    from .vad import trim_silence
    return trim_silence(audio_bytes)


def _run_diarization(audio_path: str, num_speakers: Optional[int] = None,
                     min_duration_off: Optional[float] = None) -> list:
    from .diarize import diarize
    return diarize(audio_path, num_speakers=num_speakers,
                   min_duration_off=min_duration_off)


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
    return merged


def _compute_peaks(audio_bytes: bytes) -> list:
    from .peaks import compute_peaks
    return compute_peaks(audio_bytes)

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
            backend = rec.backend or "pk-python"

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

        # Mark progress: 10% — loaded
        with Session(engine) as session:
            set_progress(session, rec_id, 10)

        # Optional VAD silence trimming
        if _VAD_TRIM and enable_vad:
            trimmed = _trim_silence(audio_bytes)
            if len(trimmed) < len(audio_bytes):
                log.info("VAD trim: rec_id=%s %d→%d bytes (%.1fs saved)", rec_id, len(audio_bytes), len(trimmed), (len(audio_bytes) - len(trimmed)) / (2 * 16000))
            audio_bytes = trimmed

        # Optional audio enhancement (ffmpeg filters before ASR)
        if enable_enhance and enable_enhance != "off":
            log.info("Enhance: rec_id=%s level=%s", rec_id, enable_enhance)
            enhanced = enhance_audio(audio_bytes, level=enable_enhance)
            if len(enhanced) != len(audio_bytes):
                log.info("Enhance: rec_id=%s %d→%d bytes", rec_id, len(audio_bytes), len(enhanced))
            audio_bytes = enhanced

        with Session(engine) as session:
            set_progress(session, rec_id, 20)

        # Run ASR (batched sync or SSE streaming)
        client = get_client(backend)
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
                set_progress(session, rec_id, 80)
        else:
            def _on_progress(pct: int):
                with Session(engine) as s:
                    set_progress(s, rec_id, pct)
            result = client.transcribe_async(
                audio_bytes, filename, mime,
                noise_reduce=enable_noise_reduce,
                on_progress=_on_progress,
            )
            with Session(engine) as session:
                set_progress(session, rec_id, 95)

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
            try:
                diar = _run_diarization(
                    str(audio_path),
                    num_speakers=rec.diarize_num_speakers,
                    min_duration_off=rec.diarize_min_duration_off,
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
        # Compute waveform peaks for fast WaveSurfer render
        try:
            audio_bytes_for_peaks = audio_path.read_bytes()
            peaks = _compute_peaks(audio_bytes_for_peaks)
        except Exception:
            log.exception("peaks: compute failed for rec_id=%s", rec_id)
            peaks = None

        # Optional post-processing (A12/A13) — nur wenn per Toggle aktiviert,
        # niemals automatisch. Stubs: Implementierung in Phase 1–2.
        if enable_punctuation and settings.POLYSCHNACK_PUNCTUATION_MODE != "off":
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
