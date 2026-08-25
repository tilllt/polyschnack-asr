"""Seed für lokale PolySchnack-Reproduktions-Instanz (nur Dev).

Legt Recordings im anon-space (user_id=None) an: unterschiedliche
Titel/Dateinamen, Zeiten, Dauern, Tags + ein WhatsApp-Batch, damit
Sortierung und Tag-Filter in der GUI reproduzierbar sind.
"""
import datetime as dt
import os
import sys
from pathlib import Path

os.environ.setdefault("DATA_DIR", "/opt/data/pk-asr/.dev-data")
sys.path.insert(0, "/opt/data/pk-asr/webapp")

from sqlmodel import Session, SQLModel, create_engine  # noqa: E402

from app.config import settings  # noqa: E402
from app.models import Recording  # noqa: E402

DATA = Path(settings.DATA_DIR)
DATA.mkdir(parents=True, exist_ok=True)
eng = create_engine(f"sqlite:///{settings.DB_PATH}")
SQLModel.metadata.create_all(eng)


def utc(**kw) -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc) - dt.timedelta(**kw)


recs = [
    # (name, title, created_days_ago, updated_days_ago, duration_s, tags, batch)
    ("alpha.mp3", "Alpha Aufnahme", 20, 20, 90.0, ["arbeit"], None),
    ("bravo.mp3", None, 18, 18, 200.0, ["privat"], None),
    ("charlie.mp3", "Charlie Meeting", 15, 2, None, ["arbeit", "interview"], None),
    ("delta.mp3", None, 12, 12, 55.0, [], None),
    ("echo.mp3", "Echo Notizen", 10, 10, 130.0, ["interview"], None),
    ("foxtrot.mp3", None, 8, 8, 500.0, ["privat"], None),
    ("golf.mp3", "Golf Ideen", 6, 6, 30.0, ["arbeit"], None),
    ("hotel.mp3", None, 4, 1, 75.0, [], None),
    ("india.mp3", "India Podcast", 3, 3, 300.0, ["privat", "interview"], None),
    ("juliet.mp3", None, 2, 2, 12.0, [], None),
    ("kilo.mp3", "Kilo Draft", 1, 1, 45.0, ["arbeit"], None),
    ("wa1.mp3", None, 9, 9, 60.0, ["privat"], "batch1"),
    ("wa2.mp3", None, 9, 9, 61.0, ["privat"], "batch1"),
    ("wa3.mp3", None, 9, 9, 62.0, ["privat"], "batch1"),
]

with Session(eng) as s:
    for i, (name, title, cd, ud, dur, tags, batch) in enumerate(recs, 1):
        s.add(Recording(
            id=i,
            uid=f"seed{i:02d}",
            original_name=name,
            title=title,
            stored_path=f"/nonexistent/{name}",
            mime="audio/mpeg",
            size_bytes=100000 + i,
            duration_s=dur,
            status="done",
            backend="ps-pk-onnx",
            alignment="done",
            diar_status="done",
            tags=tags,
            batch_id=batch,
            source="whatsapp" if batch else "upload",
            waveform_peaks="[]",
            created_at=utc(days=cd),
            updated_at=utc(days=ud),
        ))
    s.commit()

with Session(eng) as s:
    n = len(s.exec(__import__("sqlmodel").select(Recording)).all())
print(f"OK: {n} Recordings in {settings.DB_PATH}")
