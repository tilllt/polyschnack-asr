"""PATCH endpoint for inline segment text editing."""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session

from ..config import settings
from ..crud import get_recording_by_uid
from ..db import get_session
from ..permissions import ensure_access

router = APIRouter(prefix="/api")


class SegmentUpdate(BaseModel):
    text: str | None = None
    # Feature 2026-08-16: Sprecher-Zuweisung pro Segment (Dropdown) — nur
    # dieses Segment, kein globales Rename. Wörter bleiben unberührt.
    speaker: str | None = None


class SpeakerRename(BaseModel):
    from_speaker: str
    to_speaker: str


# ---------------------------------------------------------------------------
# Wort-Diff (Change 010): Text-Edits erhalten die Timestamps unveränderter
# Wörter. Bisher wurde die Wortliste aus new_text.split() neu gebaut und
# GLEICHVERTEILT über die Segment-Dauer gelegt — Wörter hinzufügen/löschen
# stauchte/dehnte dadurch auch akustisch korrekte Nachbarwörter (Karaoke,
# Wort-Seek, Re-Segmentierung arbeiteten auf künstlichen Werten).
# ---------------------------------------------------------------------------


def _align_words(
    old_words: list[dict[str, Any]],
    new_text: str,
    seg_start: float,
    seg_end: float,
) -> list[dict[str, Any]]:
    """Baut die neue Wortliste per Sequenz-Alignment gegen die alte.

    Regeln (Spec transcription-view, Req 7, Change 010):
    1. Gleiche Wortzahl → 1:1-Mapping: Wort an Position i behält die
       Timestamps von alt[i] (deckt „Wort korrigieren" verlustfrei ab).
    2. Unterschiedliche Wortzahl → LCS-Alignment über die Wort-Strings:
       übereinstimmende Wörter behalten ihre Timestamps; eingefügte
       Wörter interpolieren zwischen den erhaltenen Nachbarn
       (Segment-Grenzen als Rand); gelöschte Wörter entfallen.
    3. Kein Match + unterschiedliche Wortzahl → Gleichverteilung über
       die Segment-Dauer (Fallback, Zeile bleibt Karaoke-fähig).
    """
    new_words_list = new_text.split() if new_text else []

    if not old_words:
        return _distribute_words(new_words_list, seg_start, seg_end)

    old_strings = [str(w.get("word", "")) for w in old_words]

    # Regel 1: gleiche Wortzahl → 1:1-Mapping (Timestamps bleiben exakt).
    if len(old_words) == len(new_words_list):
        return [
            {
                "word": nw,
                "start": float(old_words[i].get("start", seg_start)),
                "end": float(old_words[i].get("end", seg_start)),
            }
            for i, nw in enumerate(new_words_list)
        ]

    # Regel 2: LCS über die Wort-Strings.
    lcs = _lcs_indices(old_strings, new_words_list)
    if not lcs:
        # Regel 3: nichts wiedererkannt → Gleichverteilung.
        return _distribute_words(new_words_list, seg_start, seg_end)
    # Match-Quote: werden weniger als die Hälfte der neuen Wörter
    # wiedererkannt, ist das Alignment unzuverlässig (z. B. fast komplett
    # umformulierter Satz) → Gleichverteilung als sichere Basis.
    if 2 * len(lcs) < len(new_words_list):
        return _distribute_words(new_words_list, seg_start, seg_end)

    result: list[dict[str, Any]] = []
    new_i = 0
    for old_idx, new_idx in lcs:
        # Eingefügte Wörter zwischen letztem Match und diesem Match:
        # gleichmäßig über die Lücke verteilen (letztes erhaltenes Ende
        # → Start dieses Matches); ohne Lücke: 0.01-s-Scheibe davor.
        if new_i < new_idx:
            result.extend(_place_words(
                new_words_list[new_i:new_idx],
                _prev_boundary(result, seg_start),
                float(old_words[old_idx].get("start", seg_start)),
            ))
            new_i = new_idx
        # Match-Wort: Timestamps vom alten Wort übernehmen.
        ow = old_words[old_idx]
        result.append({
            "word": new_words_list[new_idx],
            "start": float(ow.get("start", seg_start)),
            "end": float(ow.get("end", seg_start)),
        })
        new_i = new_idx + 1
    # Restliche eingefügte Wörter am Ende: gleichmäßig zwischen letztem
    # erhaltenen Wort und Segment-Ende.
    if new_i < len(new_words_list):
        result.extend(_place_words(
            new_words_list[new_i:],
            _prev_boundary(result, seg_start),
            seg_end,
        ))
    return result


def _lcs_indices(
    old_list: list[str],
    new_list: list[str],
) -> list[tuple[int, int]]:
    """Indizes (old_idx, new_idx) der längsten gemeinsamen Teilfolge."""
    n, m = len(old_list), len(new_list)
    if n == 0 or m == 0:
        return []
    # DP-Tabelle; nur die letzte Zeile brauchen wir zum Rückwärtslaufen
    # nicht — wir speichern die volle Tabelle (Segmente sind kurz).
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            if old_list[i] == new_list[j]:
                dp[i][j] = dp[i + 1][j + 1] + 1
            else:
                dp[i][j] = max(dp[i + 1][j], dp[i][j + 1])
    result: list[tuple[int, int]] = []
    i = j = 0
    while i < n and j < m:
        if old_list[i] == new_list[j]:
            result.append((i, j))
            i += 1
            j += 1
        elif dp[i + 1][j] >= dp[i][j + 1]:
            i += 1
        else:
            j += 1
    return result


def _prev_boundary(
    words: list[dict[str, Any]],
    seg_start: float,
) -> float:
    """End des letzten erzeugten Wortes (bzw. Segment-Start am Anfang)."""
    if words:
        try:
            return float(words[-1].get("end", seg_start))
        except (TypeError, ValueError):
            return seg_start
    return seg_start


def _place_words(
    words: list[str],
    space_start: float,
    space_end: float,
) -> list[dict[str, Any]]:
    """Mehrere eingefügte Wörter gleichmäßig über eine Lücke verteilen.

    Liegt eine echte Lücke vor (span > 0), werden die Wörter gleichmäßig
    zwischen space_start (Ende des letzten erhaltenen Wortes) und
    space_end (Start des nächsten Matches bzw. Segment-Ende) aufgeteilt.
    Ist die Lücke ≤ 0 (lückenlose Nachbarn, kein freier Platz), enden die
    Wörter exakt an space_end (Chronologie zum FOLGENDEN bleibt:
    next.start >= letztes.end) und überlappen minimal (0.01 s) den
    vorherigen Bereich — nie über das Segment-Ende hinaus, nie davor.
    Unveränderte Nachbarwörter behalten ihre Timestamps exakt.
    """
    span = space_end - space_start
    n = len(words)
    if n == 0:
        return []
    if span > 1e-9:
        step = span / n
        return [
            {
                "word": words[i],
                "start": space_start + i * step,
                "end": space_start + (i + 1) * step,
            }
            for i in range(n)
        ]
    # Keine Lücke: 0.01-s-Scheibe direkt vor space_end, gleichmäßig.
    slice_start = space_end - 0.01
    step = 0.01 / n
    return [
        {
            "word": words[i],
            "start": slice_start + i * step,
            "end": slice_start + (i + 1) * step,
        }
        for i in range(n)
    ]


def _distribute_words(
    new_words_list: list[str],
    seg_start: float,
    seg_end: float,
) -> list[dict[str, Any]]:
    """Gleichverteilung über die Segment-Dauer (Fallback, Stand vor 010)."""
    seg_duration = max(seg_end - seg_start, 0.1)
    w_duration = seg_duration / max(len(new_words_list), 1)
    return [
        {
            "word": w,
            "start": seg_start + i * w_duration,
            "end": seg_start + (i + 1) * w_duration,
        }
        for i, w in enumerate(new_words_list)
    ]


@router.post("/recordings/{rid}/speaker-rename")
def rename_speaker(
    rid: str,
    body: SpeakerRename,
    request: Request = None,
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """Ersetzt ``speaker`` in ALLEN Segmenten einer Aufnahme (global).

    User-Anforderung: Doppelklick auf einen Speaker-Namen in der GUI →
    umbenennen → der neue Name gilt an allen Vorkommen (Segmente, SRT/VTT,
    Versionen ab jetzt). Auth + Zugriff wie beim Segment-Edit (write).
    """
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")

    from ..identity import current_identity

    identity = current_identity(request, session)
    if identity is None or getattr(identity, "user", None) is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    uid = identity.user.id
    ensure_access(session, rec, uid, "write", cap=identity.key_level)

    from_speaker = body.from_speaker.strip()
    to_speaker = body.to_speaker.strip()
    if not from_speaker or not to_speaker:
        raise HTTPException(
            status_code=400, detail="from_speaker and to_speaker must not be empty"
        )

    # Tiefe Kopie (In-Place-Mutation würde SQLAlchemy-Change-Erkennung umgehen)
    import json as _json

    segments = _json.loads(_json.dumps(rec.segments or []))
    renamed = 0
    for s in segments:
        if s.get("speaker") == from_speaker:
            s["speaker"] = to_speaker
            renamed += 1
    if renamed == 0:
        raise HTTPException(
            status_code=400, detail=f"speaker '{from_speaker}' not found in segments"
        )

    rec.segments = list(segments)  # neue Referenz → SQLAlchemy erkennt die Änderung
    session.add(rec)
    session.commit()
    session.refresh(rec)

    from ..versions import snapshot

    snapshot(session, rec, "edit", user_id=uid)

    return {"segments": rec.segments, "text": rec.text, "renamed": renamed}


@router.post("/recordings/{rid}/realign")
def realign_recording(
    rid: str,
    request: Request = None,
    separate_backend: str = Form("none"),  # Change 113: BGM-Removal wie Re-Transcribe
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """Change 046: Re-Alignment auf dem aktuellen (ggf. korrigierten) Text.

    Der User hat die Transkription korrigiert (Ground Truth) → der
    Forced-Aligner verifiziert die Word-Timestamps erneut gegen die
    Akustik. Segment-Grenzen bleiben unangetastet, nur die Wörter
    (Timestamps) werden ersetzt. Läuft im Hintergrund (alignment-Feld
    zeigt pending→running→done|skipped); die Transkription bleibt
    sichtbar/bearbeitbar.

    Change 113: optionales Music-Removal (separate_backend) — bei
    Musik-Aufnahmen alignt der Forced-Aligner auf den Vocals statt auf
    dem Original (sonst alignment=skipped, „kein Aligner-Ergebnis").
    """
    if not isinstance(separate_backend, str):
        separate_backend = "none"  # direkte Funktionsaufrufe (Tests) liefern Form(...)-Objekte
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")

    from ..identity import current_identity

    identity = current_identity(request, session)
    if identity is None or getattr(identity, "user", None) is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    uid = identity.user.id
    ensure_access(session, rec, uid, "write", cap=identity.key_level)

    if rec.status != "done":
        raise HTTPException(
            status_code=409,
            detail="Transkription ist noch nicht fertig — Re-Alignment erst nach Abschluss möglich",
        )

    from ..service import _schedule_realign

    if rec.id is None or not _schedule_realign(rec.id, separate_backend):
        raise HTTPException(
            status_code=503,
            detail="Re-Alignment nicht möglich (Aligner deaktiviert, Audio fehlt oder nicht lesbar)",
        )
    return {"id": rid, "alignment": "pending"}


@router.post("/recordings/{rid}/rediarize")
def re_diarize_recording(
    rid: str,
    request: Request = None,
    num_speakers: str = Form(""),
    min_duration_off: str = Form(""),
    method: str = Form(""),
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """Change 057: Sprecher-Zuordnung (Diarization) neu berechnen.

    Analog Re-Align: läuft im Hintergrund (diar_status zeigt
    pending→running→done|failed|skipped), die Transkription bleibt
    sichtbar/bearbeitbar. Es werden NUR die ``speaker``-Felder der
    Segmente ersetzt — Text, Wörter, Timestamps, manuelle Aufteilung und
    Alignment bleiben unangetastet.

    Change 116: optionale Diar-Optionen (num_speakers, min_duration_off,
    method) übersteuern die gespeicherten Run-Einstellungen.
    """
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")

    from ..identity import current_identity

    identity = current_identity(request, session)
    if identity is None or getattr(identity, "user", None) is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    uid = identity.user.id
    ensure_access(session, rec, uid, "write", cap=identity.key_level)

    if rec.status != "done":
        raise HTTPException(
            status_code=409,
            detail="Transkription ist noch nicht fertig — Re-Diarize erst nach Abschluss möglich",
        )
    if getattr(rec, "diar_status", "done") in ("pending", "running"):
        raise HTTPException(
            status_code=409,
            detail="Re-Diarize läuft bereits",
        )

    from ..service import _schedule_rediarize

    opts: Dict[str, Any] = {}
    if num_speakers not in ("", None):
        try:
            opts["num_speakers"] = int(num_speakers)
        except (TypeError, ValueError):
            pass
    if min_duration_off not in ("", None):
        try:
            opts["min_duration_off"] = float(min_duration_off)
        except (TypeError, ValueError):
            pass
    if method not in ("", None):
        opts["method"] = method

    if rec.id is None or not _schedule_rediarize(rec.id, opts or None):
        raise HTTPException(
            status_code=503,
            detail="Re-Diarize nicht möglich (Audio fehlt oder nicht lesbar)",
        )
    return {"id": rid, "diar_status": "pending"}


@router.patch("/recordings/{rid}/segments/{idx}")
def update_segment(
    rid: str,
    idx: int,
    body: SegmentUpdate,
    request: Request = None,
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """Update the text of a single segment in-place."""
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")

    from ..identity import current_identity

    identity = current_identity(request, session)
    if identity is None or getattr(identity, "user", None) is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    uid = identity.user.id
    ensure_access(session, rec, uid, "write", cap=identity.key_level)

    # Tiefe Kopie: neue dicts → SQLAlchemy erkennt die Zuweisung als Änderung
    # (In-Place-Mutation der JSON-Liste würde auch die "alte" Liste verändern,
    # sodass alte == neue und der Commit stillschweigend übersprungen wird).
    import json as _json

    segments = _json.loads(_json.dumps(rec.segments or []))
    if idx < 0 or idx >= len(segments):
        raise HTTPException(status_code=404, detail="segment not found")

    new_text = body.text.strip() if body.text is not None else None
    new_speaker = body.speaker.strip() if body.speaker is not None else None
    if new_text is None and new_speaker is None:
        raise HTTPException(
            status_code=400, detail="text or speaker must be provided"
        )

    if new_text is not None:
        if not new_text:
            raise HTTPException(status_code=400, detail="text must not be empty")
        segments[idx]["text"] = new_text
        # Change 010 (Wort-Diff): unveränderte Wörter behalten ihre
        # Timestamps (1:1 bei gleicher Wortzahl, LCS bei Einfügen/Löschen);
        # nur neue Wörter interpolieren, gelöschte entfallen. Fallback:
        # Gleichverteilung, wenn nichts wiedererkannt wird.
        seg_start = segments[idx].get("start", 0)
        seg_end = segments[idx].get("end", seg_start + 1)
        segments[idx]["words"] = _align_words(
            segments[idx].get("words") or [],
            new_text,
            seg_start,
            seg_end,
        )
    if new_speaker is not None:
        if not new_speaker:
            raise HTTPException(status_code=400, detail="speaker must not be empty")
        # Nur Sprecher-Zuweisung: Wörter/Timestamps bleiben unangetastet.
        if new_speaker == "_none":
            segments[idx].pop("speaker", None)
        else:
            segments[idx]["speaker"] = new_speaker
    rec.segments = list(segments)  # neue Referenz → SQLAlchemy erkennt die Änderung
    rec.text = " ".join(s["text"] for s in segments)
    rec.updated_at = dt.datetime.now(dt.timezone.utc)  # Change 054: „Last edit date"
    session.add(rec)
    session.commit()
    session.refresh(rec)

    from ..versions import snapshot

    snapshot(session, rec, "edit", user_id=uid)

    return {"segments": rec.segments, "text": rec.text}


class SegmentListUpdate(BaseModel):
    """Komplette Segmentliste (Feature 2026-08-15: Segmentlängen).

    Vom Frontend nach Re-Segmentierung (frei wählbare Dauer) oder
    manuell verschobenen Grenzen (draggable Timecode-Marker) gesendet.
    Die Wörter bleiben erhalten — nur start/end/text/Speaker dürfen
    abweichen. Persistiert wird die Liste; der Export (SRT/VTT) und die
    Preview nutzen damit dieselben Grenzen.
    """

    segments: list[dict[str, Any]]


@router.put("/recordings/{rid}/segments")
def replace_segments(
    rid: str,
    body: SegmentListUpdate,
    request: Request = None,
    session: Session = Depends(get_session),
    # Change 068: Autosave ruft ohne create_version auf (nur DB-Write,
    # keine Versions-Spam je Tastenanschlag); die Version entsteht erst
    # beim Verlassen des Edit-Mode (create_version=True, Default).
    create_version: bool = True,
) -> Dict[str, Any]:
    """Ersetzt die komplette Segmentliste einer fertigen Aufnahme.

    Auth + Zugriff wie beim Segment-Edit (write). Der Gesamt-Text wird
    aus den Segment-Texten neu zusammengesetzt. Voraussetzung: mindestens
    ein Segment; jedes Segment braucht start/end/text. Wörter sind
    optional, bleiben aber für Karaoke + Wort-für-Wort-Verschiebung
    erhalten.

    Change 068: ``create_version=False`` (Autosave) schreibt nur den
    DB-Stand ohne TranscriptVersion; ``True`` (Default, Edit-Mode-Ende)
    legt zusätzlich eine Version an.
    """
    rec = get_recording_by_uid(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")

    from ..identity import current_identity

    identity = current_identity(request, session)
    if identity is None or getattr(identity, "user", None) is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    uid = identity.user.id
    ensure_access(session, rec, uid, "write", cap=identity.key_level)

    if rec.status != "done":
        raise HTTPException(status_code=409, detail="transcription not complete yet")

    segs = body.segments
    if not segs:
        raise HTTPException(status_code=400, detail="segments must not be empty")
    for i, s in enumerate(segs):
        if "start" not in s or "end" not in s:
            raise HTTPException(
                status_code=400, detail=f"segment {i} missing start/end"
            )
        if not str(s.get("text") or "").strip():
            raise HTTPException(status_code=400, detail=f"segment {i} empty text")

    # Tiefe Kopie → SQLAlchemy erkennt die Zuweisung als Änderung.
    import json as _json

    stored = _json.loads(_json.dumps(segs))
    rec.segments = stored
    # Change 009: jede Segment-Struktur-Operation (Grenz-Drag, +/−, Split,
    # Re-Segmentierung) markiert die Aufteilung als manuell — die Anzeige
    # nutzt segments direkt und re-segmentiert nie automatisch darüber.
    rec.segments_manual = True
    rec.text = " ".join(str(s["text"]).strip() for s in stored)
    rec.updated_at = dt.datetime.now(dt.timezone.utc)  # Change 054: „Last edit date"
    session.add(rec)
    session.commit()
    session.refresh(rec)

    # Change 068: Autosave (create_version=False) → nur DB-Write, keine
    # TranscriptVersion (keine Versions-Spam je Tastenanschlag). Version
    # erst beim Verlassen des Edit-Mode (True, Default).
    if create_version:
        from ..versions import snapshot

        snapshot(session, rec, "edit", user_id=uid)

    return {"segments": rec.segments, "text": rec.text,
            "segments_manual": rec.segments_manual}
