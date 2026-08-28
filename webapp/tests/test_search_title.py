"""Change 149: Suche findet umbenannte Aufnahmen (title).

User-Befund 2026-08-28: Nach dem Umbenennen einer Transkription war sie
per neuem Namen nicht auffindbar — die Suche matchte nur original_name
und text, nicht title (das Feld, das PATCH /title setzt).
"""

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.crud import list_recordings
from app.models import Recording


@pytest.fixture()
def db(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/search.db")
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        yield s


def _mk(db, title=None, original=None, text=""):
    r = Recording(
        id=None,
        title=title,
        original_name=original or "audio_001.wav",
        stored_path="tmp_audio_001.wav",
        text=text,
        user_id=None,
    )
    db.add(r)
    db.commit()
    return r


def test_suche_findet_neuen_titel_nach_rename(db):
    rec = _mk(db, title="Alter Name", original="audio_001.wav")
    # Rename (PATCH /title setzt genau dieses Feld)
    rec.title = "Mein neuer Filmtitel"
    db.commit()

    hits = list_recordings(db, q="neuer filmtitel", user_id=None)
    assert any(r.id == rec.id for r in hits)


def test_suche_findet_originalname_weiterhin(db):
    rec = _mk(db, title="Umbenannt", original="rohaufnahme_xyz.mp3")
    hits = list_recordings(db, q="rohaufnahme", user_id=None)
    assert any(r.id == rec.id for r in hits)


def test_suche_findet_transkript_text_weiterhin(db):
    rec = _mk(db, title="T", text="Das ist der transkribierte Inhalt")
    hits = list_recordings(db, q="transkribierte", user_id=None)
    assert any(r.id == rec.id for r in hits)
