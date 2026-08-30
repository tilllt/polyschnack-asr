"""Change 158: Aligner-Fehler degradieren — skipped mit ehrlichem Grund.

Der transcribe-Run kontaktiert den Aligner nie synchron (Change 045:
Alignment startet nach done als Hintergrund-Job) — ein ASR-Run kann durch
den Aligner nicht abbrechen. Der align-Job selbst failt nie; bei
Aligner-Fehler (z.B. Container down) wird alignment="skipped" gesetzt.
Change 158 ergänzt die ehrliche Fehlermeldung (rec.error mit Grund) —
kein stiller „Alignment skipped".
"""

from __future__ import annotations

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app import service as service_mod
from app.models import Recording, User


@pytest.fixture()
def db(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/align.db")
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(User(id=1, sub="u1", kind="oidc"))
        s.add(Recording(
            id=1, uid="r1", original_name="a.mp3",
            stored_path=str(tmp_path / "a.mp3"), user_id=1,
            status="done", text="Hallo", alignment="pending",
            segments=[{"start": 0.0, "end": 1.0, "text": "Hallo",
                       "words": [{"start": 0.0, "end": 1.0, "text": "Hallo"}]}],
        ))
        s.commit()
    return eng


def test_align_fehler_skipped_mit_grund(db, monkeypatch):
    """Aligner-Call wirft (Container down) → alignment=skipped + error mit
    Grund ('nicht erreichbar'), Recording bleibt done (Change 158)."""
    monkeypatch.setattr(service_mod, "engine", db)
    monkeypatch.setattr(
        "app.aligner_client.ALIGN_WORDS_ENABLED", True,
    )
    monkeypatch.setattr(
        service_mod, "_prepare_align_audio",
        lambda rec_id, separate_backend="none": (b"MP3", None),
    )

    def _boom(*a, **k):
        raise RuntimeError("Aligner nicht erreichbar (ConnectError)")

    monkeypatch.setattr(service_mod, "_run_align_phase", _boom)

    class _FakeAlign:
        def health(self):
            return False

    monkeypatch.setattr(
        "app.aligner_client.AlignerClient", lambda *a, **k: _FakeAlign(),
    )

    service_mod._run_background_align(1)

    with Session(db) as s:
        rec = s.get(Recording, 1)
        assert rec.status == "done"          # Transkription bleibt
        assert rec.alignment == "skipped"    # nie ein Job-Fail
        assert "nicht erreichbar" in (rec.error or "")
