"""Stale-Processing-Watchdog: hängengebliebene Transkriptionen als failed markieren.

User-Befund 2026-08-14: im Live-Modus blieb der Progress bei 80% hängen und
der Status „processing" für immer — PolySchnack erkannte nicht, dass die
Transkription nie fertig wurde. Ursachen: (a) der alte Peaks-Code verbrauchte
bei langen Dateien Gigabytes RAM → Webapp-Container wurde OOM-gekillt mitten
in der Verarbeitung, (b) eine abgerissene SSE-Verbindung hing bis zum
3600-s-Client-Timeout. In beiden Fällen blieb die Recording ewig
status="processing", weil es keinen Mechanismus gab, verwaiste Jobs zu
erkennen.

Dieser Sweep markiert Recordings, deren letztes Progress-Update (updated_at)
älter als POLYSCHNACK_STALE_PROCESSING_MINUTES ist, als failed mit einer
verständlichen Meldung — der User kann dann einfach erneut transkribieren,
statt auf einen Geist zu starren.

Aktive Diarization wird übersprungen (progress_note == "diarization"): diese
Phase feuert lange keine Progress-Updates, kann aber durchaus Minuten bis
Stunden dauern — der User sieht den „erkenne Sprecher…"-Hinweis.
"""
from __future__ import annotations

import datetime as dt
import logging
import os

from sqlmodel import Session, select

from .models import Recording

log = logging.getLogger(__name__)

STALE_PROCESSING_MINUTES = int(os.getenv("POLYSCHNACK_STALE_PROCESSING_MINUTES", "120"))

_STALE_MESSAGE = (
    "Verarbeitung wurde unterbrochen (Worker-Neustart oder Speichermangel) "
    "und nie abgeschlossen — bitte erneut transkribieren."
)


def sweep_stale_processing(session: Session) -> int:
    """Markiere hängengebliebene processing-Recordings als failed.

    Returns: Anzahl markierter Recordings.
    """
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(
        minutes=STALE_PROCESSING_MINUTES
    )
    rows = session.exec(
        select(Recording).where(
            Recording.status == "processing",
            Recording.updated_at < cutoff,
        )
    ).all()
    marked = 0
    now = dt.datetime.now(dt.timezone.utc)
    for rec in rows:
        # Diarization läuft ohne Progress-Updates, kann aber lange dauern —
        # den sichtbaren Hinweis nicht als Hang interpretieren.
        if rec.progress_note == "diarization":
            continue
        rec.status = "failed"
        rec.error = _STALE_MESSAGE
        rec.updated_at = now
        session.add(rec)
        marked += 1
    if marked:
        session.commit()
        log.warning("stale-processing sweep: %d hängende Transkription(en) als failed markiert", marked)
    return marked
