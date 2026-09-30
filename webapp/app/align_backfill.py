"""Change 238 — Wartungsauftrag: ausstehende Forced-Alignments nachziehen.

**Warum es diesen Auftrag gibt.** Change 237 hat die Ursache behoben, aus der
das Hintergrund-Alignment seit Change 173 nie mehr automatisch eingereiht
wurde (der eigene Transkriptions-Job blockierte den Folge-Auftrag). Die
Aufnahmen aus diesen Wochen stehen deshalb mit den groben Wortzeiten des
Transkriptionslaufs da — auf der KI-Box gemessen: **103 von 116 Aufnahmen
ohne align-Job** (Stand 30.09.2026), der jüngste align-Job stammt vom
19.09.2026.

**Wie er arbeitet.** Als Task der Scheduler-Registry (dasselbe Muster wie
``peaks-backfill``), nicht als eigener Thread: Der Scheduler ruft ``tick()``
regelmäßig auf, jeder Takt reiht **bis zu ``WAVE``** Aufträge ein und ist
sofort wieder fertig (kein Schlafen im Task, kein Overlap). Die Aufträge
laufen mit **Priorität 1** — wie anonyme Jobs, also hinter der Arbeit eines
angemeldeten Nutzers. Jeder Auftrag ist der reguläre ``align``-Queue-Job
(Change 046/155): der Worker bereitet das Audio selbst aus der gespeicherten
Datei vor, der Versions-Guard verwirft das Ergebnis, wenn sich die Segmente
während des Laufs geändert haben. Text und Segmente werden **nie** angefasst.

**Wie man ihn startet und abbricht.** Er läuft nur, wenn im Datenverzeichnis
die Datei ``.align-backfill`` liegt. Anlegen startet ihn (innerhalb eines
Ticks), Löschen beendet ihn — ohne Neustart, ohne Konfiguration. Ohne Datei
ist der Task ein Leerlauf.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from sqlmodel import Session, select

from . import db
from .models import Job as JobRow
from .models import Recording

log = logging.getLogger(__name__)

#: Wartungsauftrag: liegt diese Datei im Datenverzeichnis, werden ausstehende
#: Alignments nachgezogen. Löschen = Ende (greift beim nächsten Takt).
FLAG_NAME = ".align-backfill"

#: Aufträge je Takt (schont die Box: die Wartung läuft neben dem Betrieb).
WAVE = 4

#: Takt des Auftrags in Sekunden (so registriert in main.py).
TICK_S = 30.0

#: Prozess-Status der Wartung — nur Anzeige/Diagnose, keine Steuerung.
_state: Dict[str, Any] = {
    "enqueued": 0,
    "skipped": 0,
    "ohne_audio": set(),
    "abschluss_gemeldet": False,
}


def flag_path(data_dir: Optional[str] = None) -> Path:
    """Pfad der Auftrags-Datei (Standard: DATA_DIR des Containers)."""
    return Path(data_dir or os.getenv("DATA_DIR", "/data")) / FLAG_NAME


def backfill_enabled(data_dir: Optional[str] = None) -> bool:
    """Liegt ein Wartungsauftrag vor?"""
    return flag_path(data_dir).is_file()


def status() -> Dict[str, Any]:
    """Bilanz des laufenden Auftrags (für Protokoll und Diagnose)."""
    out = dict(_state)
    out["ohne_audio"] = sorted(int(x) for x in _state["ohne_audio"])
    out["aktiv"] = backfill_enabled()
    return out


def reset_state() -> None:
    """Bilanz zurücksetzen (Auftrag beendet oder neu angelegt)."""
    _state.update({"enqueued": 0, "skipped": 0, "ohne_audio": set(),
                   "abschluss_gemeldet": False})


def candidates(session: Session, limit: int = 200,
               exclude: Optional[Set[int]] = None) -> List[Recording]:
    """Fertige Aufnahmen, deren feines Alignment nie gelaufen ist.

    Kriterium ist bewusst die **Job-Tabelle**, nicht das Feld ``alignment``:
    das Feld steht auch dann auf ``done``, wenn nur die groben Wortzeiten des
    Transkriptionslaufs existieren (``_build_word_stream``). „Kein align-Job"
    ist damit das ehrliche Merkmal für „der präzise Lauf hat nie
    stattgefunden". Neueste zuerst — die jüngsten Aufnahmen hat der Nutzer
    gerade offen.
    """
    mit_job = select(JobRow.rec_id).where(JobRow.kind == "align")
    stmt = (
        select(Recording)
        .where(Recording.status == "done")
        .where(~Recording.id.in_(mit_job))
    )
    if exclude:
        # Ausschluss in der ABFRAGE, nicht danach: sonst frisst das LIMIT die
        # Plätze mit Aufnahmen, die wir ohnehin überspringen wollen.
        stmt = stmt.where(~Recording.id.in_(sorted(int(x) for x in exclude)))
    stmt = stmt.order_by(Recording.id.desc()).limit(limit)
    return list(session.exec(stmt).all())


def tick(limit: int = WAVE) -> int:
    """Ein Takt des Wartungsauftrags — reiht bis zu ``limit`` Aufträge ein.

    Gibt die Zahl der eingereihten Aufträge zurück (0 ohne Auftragsdatei
    oder wenn nichts mehr offen ist). Wird vom Scheduler aufgerufen; läuft
    nie länger als ein paar Datenbankabfragen.
    """
    if not backfill_enabled():
        if _state["enqueued"] or _state["ohne_audio"]:
            log.info("Wartungsauftrag align-backfill beendet: %s", status())
            reset_state()
        return 0

    with Session(db.engine) as session:
        offen = candidates(session, limit=limit, exclude=_state["ohne_audio"])

    if not offen:
        if not _state["abschluss_gemeldet"]:
            log.info(
                "Wartungsauftrag align-backfill: nichts mehr offen "
                "(%d nachgezogen, %d ohne Audio) — Auftragsdatei kann gelöscht werden",
                _state["enqueued"], len(_state["ohne_audio"]))
            _state["abschluss_gemeldet"] = True
        return 0

    eingereiht = 0
    for rec in offen:
        if rec.id is None:
            continue
        if _einreihen(int(rec.id)):
            eingereiht += 1
            _state["enqueued"] += 1
        else:
            # Audio fehlt/nicht lesbar oder Aufnahme inzwischen belegt: merken,
            # nicht erneut versuchen (sonst bliebe der Task an derselben
            # Aufnahme hängen und käme nie weiter).
            _state["skipped"] += 1
            _state["ohne_audio"].add(int(rec.id))

    if eingereiht:
        log.info("Wartungsauftrag align-backfill: %d Auftrag/Aufträge eingereiht "
                 "(Summe %d)", eingereiht, _state["enqueued"])
    return eingereiht


def _einreihen(rec_id: int) -> bool:
    """Regulären align-Job einreihen (Priorität 1 — hinter der Nutzer-Arbeit)."""
    from .service import _schedule_realign

    return _schedule_realign(int(rec_id), "none", priority=1)
