"""Change 238 — Wartungsauftrag: ausstehende Forced-Alignments nachziehen.

**Warum es diesen Auftrag gibt.** Change 237 hat die Ursache behoben, aus der
das Hintergrund-Alignment seit Change 173 nie mehr automatisch eingereiht
wurde (der eigene Transkriptions-Job blockierte den Folge-Auftrag). Die
Aufnahmen aus diesen Wochen stehen deshalb mit den groben Wortzeiten des
Transkriptionslaufs da — auf der KI-Box gemessen: **103 von 116 Aufnahmen
ohne align-Job** (Stand 30.09.2026), der jüngste align-Job stammt vom
19.09.2026.

**Wie er arbeitet.** Nicht sofort für alle 103, sondern gedrosselt in Wellen:
je Welle bis zu `WAVE` Aufträge, dazwischen `PAUSE_S` Ruhe. Die Aufträge
laufen mit **Priorität 1** (wie anonyme Jobs) und damit hinter der normalen
Arbeit eines angemeldeten Nutzers. Jeder Auftrag ist der reguläre
`align`-Queue-Job (Change 046/155): der Worker bereitet das Audio selbst vor
und die Wortzeiten werden per Versions-Guard nur dann ersetzt, wenn die
Segmente unverändert sind. Text und Segmente werden **nie** angefasst.

**Wie man ihn startet und abbricht.** Er läuft nur, wenn im Datenverzeichnis
die Datei `.align-backfill` liegt — und nur beim Start der Anwendung
(Wartungsfenster). Die Datei während des Laufs löschen bricht ab; nach dem
letzten offenen Auftrag endet er von selbst. Ohne Datei passiert nichts.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from sqlmodel import Session, select

from . import db
from .models import Job as JobRow
from .models import Recording

log = logging.getLogger(__name__)

#: Wartungsauftrag: liegt diese Datei im Datenverzeichnis, werden beim Start
#: ausstehende Alignments nachgezogen. Löschen = Abbruch (auch im Lauf).
FLAG_NAME = ".align-backfill"

#: Aufträge je Welle und Ruhe zwischen den Wellen (schont die Box).
WAVE = 4
PAUSE_S = 20.0


def flag_path(data_dir: Optional[str] = None) -> Path:
    """Pfad der Auftrags-Datei (Standard: DATA_DIR des Containers)."""
    return Path(data_dir or os.getenv("DATA_DIR", "/data")) / FLAG_NAME


def backfill_enabled(data_dir: Optional[str] = None) -> bool:
    """Liegt ein Wartungsauftrag vor?"""
    return flag_path(data_dir).is_file()


def candidates(session: Session, limit: int = 200,
               exclude: Optional[Set[int]] = None) -> List[Recording]:
    """Fertige Aufnahmen, deren feines Alignment nie gelaufen ist.

    Kriterium ist bewusst die **Job-Tabelle**, nicht das Feld ``alignment``:
    das Feld steht auch dann auf ``done``, wenn nur die groben Wortzeiten des
    Transkriptionslaufs existieren (`_build_word_stream`). „Kein align-Job"
    ist damit das ehrliche Merkmal für „der präzise Lauf hat nie
    stattgefunden". Neueste zuerst — die jüngsten Aufnahmen hat der Nutzer
    gerade offen.
    """
    mit_job = select(JobRow.rec_id).where(JobRow.kind == "align")
    stmt = (
        select(Recording)
        .where(Recording.status == "done")
        .where(~Recording.id.in_(mit_job))
        .order_by(Recording.id.desc())
        .limit(limit)
    )
    rows = list(session.exec(stmt).all())
    if exclude:
        rows = [r for r in rows if r.id not in exclude]
    return rows


def run_backfill(*, wave: int = WAVE, pause_s: float = PAUSE_S,
                 stop_event: Optional[threading.Event] = None,
                 max_total: Optional[int] = None,
                 data_dir: Optional[str] = None) -> Dict[str, Any]:
    """Zieht ausstehende Alignments nach — gedrosselt und abbruchfähig.

    Endet, wenn (a) die Auftrags-Datei fehlt (Abbruch durch den Nutzer),
    (b) keine Aufnahme mehr aussteht oder (c) ``max_total`` erreicht ist.
    Aufnahmen, deren Audio fehlt, werden gemerkt und nicht erneut versucht —
    sonst liefe die Schleife endlos gegen dieselben Kandidaten.
    """
    flag = flag_path(data_dir)
    stats: Dict[str, Any] = {"enqueued": 0, "skipped": 0, "rounds": 0,
                             "ende": "unbekannt", "ohne_audio": []}
    unmoeglich: Set[int] = set()

    while True:
        if stop_event is not None and stop_event.is_set():
            stats["ende"] = "abgebrochen"
            break
        if not flag.is_file():
            stats["ende"] = "auftragsdatei-fehlt"
            break

        with Session(db.engine) as session:
            offen = candidates(session, limit=wave, exclude=unmoeglich)
        if not offen:
            stats["ende"] = "nichts-mehr-offen"
            break

        for rec in offen:
            if not flag.is_file() or (stop_event is not None and stop_event.is_set()):
                stats["ende"] = "abgebrochen"
                break
            if _einreihen(rec.id):
                stats["enqueued"] += 1
            else:
                stats["skipped"] += 1
                if rec.id is not None:
                    unmoeglich.add(int(rec.id))
                    stats["ohne_audio"].append(int(rec.id))
        stats["rounds"] += 1

        if stats["ende"] == "abgebrochen":
            break
        if max_total is not None and stats["enqueued"] >= max_total:
            stats["ende"] = "obergrenze-erreicht"
            break
        if pause_s > 0:
            time.sleep(pause_s)

    log.info("Wartungsauftrag align-backfill beendet: %s", stats)
    return stats


def _einreihen(rec_id: int) -> bool:
    """Regulären align-Job einreihen (Priorität 1 — hinter der Nutzer-Arbeit)."""
    from .service import _schedule_realign

    return _schedule_realign(int(rec_id), "none", priority=1)
