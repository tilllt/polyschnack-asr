"""Change 048: Boot-Recovery — hängende Hintergrund-Alignments (pending/running).

Szenario: Container-Restart/Stromausfall tötet den 045/046-Hintergrund-
Worker, bevor er alignment setzt → Status bleibt pending (nie gestartet)
oder running (mitten im Aligner-Call). `recover_stale_alignments` läuft
beim Boot und markiert diese als skipped + löscht verwaiste Cache-Dateien.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Recording
from app.service import _AlignmentCache, recover_stale_alignments


@pytest.fixture()
def db(tmp_path, monkeypatch):
    """In-Memory-DB + Alignment-Cache auf tmp_path umgebogen."""
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    SQLModel.metadata.create_all(eng)
    # _AlignmentCache._DIR ist Klassenattribut (beim Import aus DATA_DIR
    # gesetzt) — für den Test auf tmp_path umbiegen, damit nichts ins
    # echte /data schreibt.
    cache_dir = tmp_path / ".align-cache"
    cache_dir.mkdir()
    monkeypatch.setattr(_AlignmentCache, "_DIR", cache_dir)

    def _make_rec(rec_id: int, alignment: str) -> Recording:
        rec = Recording(
            id=rec_id,
            uid=f"r{rec_id}",
            original_name=f"a{rec_id}.mp3",
            stored_path=str(tmp_path / f"a{rec_id}.mp3"),
            user_id=1,
            status="done",
            text="Hallo",
            alignment=alignment,
        )
        with Session(eng) as s:
            s.add(rec)
            s.commit()
        return rec

    yield eng, _make_rec, cache_dir


def _write_cache(cache_dir: Path, rec_id: int) -> None:
    """Simuliert die verwaisten Worker-Artefakte (Change 045)."""
    (cache_dir / f"{rec_id}.wav").write_bytes(b"\x00" * 64)
    (cache_dir / f"{rec_id}.json").write_text('{"trim_offset_s": 0.0}')


def test_pending_wird_skipped_und_cache_geloescht(db):
    eng, make_rec, cache_dir = db
    make_rec(1, "pending")
    _write_cache(cache_dir, 1)

    with Session(eng) as s:
        n = recover_stale_alignments(s)
        assert n == 1
        rec = s.get(Recording, 1)
        assert rec is not None
        assert rec.alignment == "skipped"
        assert rec.status == "done"  # Haupt-Job unangetastet
    assert not (cache_dir / "1.wav").exists()
    assert not (cache_dir / "1.json").exists()


def test_running_wird_skipped(db):
    eng, make_rec, _ = db
    make_rec(2, "running")
    with Session(eng) as s:
        assert recover_stale_alignments(s) == 1
        assert s.get(Recording, 2).alignment == "skipped"


def test_done_und_skipped_bleiben_unveraendert(db):
    eng, make_rec, cache_dir = db
    make_rec(3, "done")
    make_rec(4, "skipped")
    with Session(eng) as s:
        assert recover_stale_alignments(s) == 0
        assert s.get(Recording, 3).alignment == "done"
        assert s.get(Recording, 4).alignment == "skipped"


def test_idempotent(db):
    eng, make_rec, _ = db
    make_rec(5, "pending")
    with Session(eng) as s:
        assert recover_stale_alignments(s) == 1
    with Session(eng) as s:
        assert recover_stale_alignments(s) == 0


def test_cache_von_done_bleibt_liegen(db):
    """Nur verwaiste pending/running-Caches werden gelöscht — ein Cache
    eines fertigen (done-)Alignments ist kein WIP-Artefakt."""
    eng, make_rec, cache_dir = db
    make_rec(6, "done")
    _write_cache(cache_dir, 6)
    with Session(eng) as s:
        assert recover_stale_alignments(s) == 0
    assert (cache_dir / "6.wav").exists()
    assert (cache_dir / "6.json").exists()
