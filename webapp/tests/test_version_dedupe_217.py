"""Change 217: Keine Versionsflut — eine Version nur bei echtem Inhaltsunterschied.

Belegter Ausgangsbefund (Datenbank-Gegenprobe): Aufnahme 297 hatte 323
Versionen, Aufnahme 340 132, eine weitere 86; in einer Stichprobe von 1089
Versionen enthielt genau EINE ein leeres Segment — die anderen waren
inhaltlich gleich zu ihrer Vorgängerin. Ursache: ``versions.snapshot()`` legte
bedingungslos eine neue Zeile an (nur „nicht leer" wurde geprüft), obwohl der
Autosave-Speicherpfad denselben Stand mehrfach schreibt.

Festschreibung:
- Eine Version entsteht NUR bei geändertem Inhalts-Fingerabdruck
  (Text + Segmenttexte in Reihenfolge + Sprecher/Grenzen/Wörter) — nie über
  einen Zeitstempel.
- Ist der Inhalt identisch, wird auch nicht geschrieben.
- Bestehende Versionen bleiben unangetastet (kein Aufräumen, kein Umschreiben).
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from app import db as db_module
    from app.config import settings
    from app.main import app

    eng = create_engine(
        f"sqlite:///{tmp_path / 'vflut.db'}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(settings, "AUDIO_DIR", audio_dir)
    monkeypatch.setattr(settings, "OIDC_ENABLED", False)

    with TestClient(app) as c:
        yield c


def _seg(start: float, end: float, text: str, words=None) -> dict:
    s: dict = {"start": start, "end": end, "text": text}
    if words:
        s["words"] = words
    return s


def _words(start: float, end: float, *texts: str) -> list[dict]:
    step = (end - start) / max(len(texts), 1)
    return [
        {"word": w, "start": start + i * step, "end": start + (i + 1) * step}
        for i, w in enumerate(texts)
    ]


def _make_done_recording(client, segments) -> str:
    """Fertige Aufnahme direkt in der DB (ohne Version) — wie im Bestand."""
    resp = client.post(
        "/api/recordings",
        files={"file": ("vflut-test.mp3", b"fake-audio-bytes", "audio/mpeg")},
    )
    assert resp.status_code == 201, resp.text
    rid = resp.json()["uid"]

    from app.db import engine
    from app.models import Recording

    with Session(engine) as s:
        rec = s.exec(select(Recording).where(Recording.uid == rid)).first()
        assert rec is not None
        rec.status = "done"
        rec.segments = segments
        rec.text = " ".join(str(x["text"]) for x in segments)
        s.add(rec)
        s.commit()
    return rid


def _version_count(rid: str) -> int:
    from app.db import engine
    from app.models import Recording, TranscriptVersion

    with Session(engine) as s:
        rec = s.exec(select(Recording).where(Recording.uid == rid)).first()
        assert rec is not None
        return len(
            s.exec(
                select(TranscriptVersion).where(TranscriptVersion.rec_id == rec.id)
            ).all()
        )


# ---------------------------------------------------------------------------
# 1) snapshot() — der einzige Ort, an dem Versionen entstehen
# ---------------------------------------------------------------------------


def test_snapshot_gleicher_inhalt_erzeugt_keine_zweite_version(tmp_path):
    """Zweimal derselbe Inhalt → genau EINE Version."""
    from app.models import Recording, TranscriptVersion
    from app.versions import snapshot

    eng = create_engine(f"sqlite:///{tmp_path}/a.db")
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        segs = [_seg(0.0, 1.0, "Hallo Welt", _words(0.0, 1.0, "Hallo", "Welt"))]
        s.add(Recording(id=1, uid="r1", original_name="a.mp3", stored_path="p",
                        status="done", text="Hallo Welt", segments=segs))
        s.commit()
        rec = s.get(Recording, 1)
        assert snapshot(s, rec, "edit") is not None
        # identischer Inhalt, erneut gespeichert (Autosave + Edit-Mode-Ende)
        assert snapshot(s, rec, "edit") is None
        assert snapshot(s, rec, "edit") is None
        assert len(s.exec(select(TranscriptVersion)).all()) == 1


def test_snapshot_geaenderter_inhalt_erzeugt_neue_version(tmp_path):
    """Geänderter Text bzw. geänderte Grenzen → neue Version."""
    from app.models import Recording, TranscriptVersion
    from app.versions import snapshot

    eng = create_engine(f"sqlite:///{tmp_path}/b.db")
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        segs = [_seg(0.0, 1.0, "Hallo Welt")]
        s.add(Recording(id=1, uid="r1", original_name="a.mp3", stored_path="p",
                        status="done", text="Hallo Welt", segments=segs))
        s.commit()
        rec = s.get(Recording, 1)
        v1 = snapshot(s, rec, "edit")
        assert v1 is not None and v1.version_no == 1

        rec.text = "Hallo Du"
        rec.segments = [_seg(0.0, 1.0, "Hallo Du")]
        s.add(rec)
        s.commit()
        v2 = snapshot(s, rec, "edit")
        assert v2 is not None and v2.version_no == 2

        # Grenze verschoben = Inhaltsänderung (kein Zeitstempel-Vergleich)
        rec.segments = [_seg(0.0, 2.5, "Hallo Du")]
        s.add(rec)
        s.commit()
        v3 = snapshot(s, rec, "edit")
        assert v3 is not None and v3.version_no == 3
        assert len(s.exec(select(TranscriptVersion)).all()) == 3


def test_snapshot_ignoriert_zeitstempel_und_anzeigefelder(tmp_path):
    """Nur der Inhalt zählt: ``updated_at``/``id`` erzeugen keine Version."""
    from datetime import datetime, timedelta, timezone

    from app.models import Recording, TranscriptVersion
    from app.versions import snapshot

    eng = create_engine(f"sqlite:///{tmp_path}/c.db")
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        segs = [_seg(0.0, 1.0, "Hallo Welt")]
        s.add(Recording(id=1, uid="r1", original_name="a.mp3", stored_path="p",
                        status="done", text="Hallo Welt", segments=segs))
        s.commit()
        rec = s.get(Recording, 1)
        assert snapshot(s, rec, "edit") is not None

        # Zeitstempel + reine Anzeigefelder ändern sich → immer noch identisch
        rec.updated_at = datetime.now(timezone.utc) + timedelta(seconds=16)
        rec.segments = [dict(segs[0], id=8)]
        s.add(rec)
        s.commit()
        assert snapshot(s, rec, "edit") is None
        assert len(s.exec(select(TranscriptVersion)).all()) == 1


def test_content_fingerprint_rundet_rauschen_weg():
    """Float-Rauschen unter 0,5 ms ist keine Inhaltsänderung."""
    from app.versions import content_fingerprint

    a = content_fingerprint("Hallo Welt", [_seg(0.0, 1.0, "Hallo Welt")])
    b = content_fingerprint("Hallo Welt", [_seg(0.0, 1.000499, "Hallo Welt")])
    c = content_fingerprint("Hallo Welt", [_seg(0.0, 1.2, "Hallo Welt")])
    assert a == b
    assert a != c
    # Reihenfolge der Segmente zählt
    assert content_fingerprint("a b", [_seg(0, 1, "a"), _seg(1, 2, "b")]) != \
        content_fingerprint("a b", [_seg(0, 1, "b"), _seg(1, 2, "a")])


# ---------------------------------------------------------------------------
# 2) PUT /segments — Autosave-Pfad: identischer Inhalt schreibt nicht
# ---------------------------------------------------------------------------


def test_put_gleicher_inhalt_keine_version_und_kein_schreiben(client):
    """Gleicher Inhalt zweimal speichern → genau EINE Version."""
    rid = _make_done_recording(client, [_seg(0, 10, "eins zwei", _words(0, 10, "eins", "zwei"))])
    segs = [_seg(0, 10, "eins zwei drei", _words(0, 10, "eins", "zwei", "drei"))]

    r = client.put(f"/api/recordings/{rid}/segments", json={"segments": segs})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["changed"] is True and body["version_created"] is True
    assert _version_count(rid) == 1
    stamp = body["updated_at"]
    assert stamp

    # Zweiter identischer Save (z. B. Autosave/Edit-Mode-Ende) → nichts
    r2 = client.put(f"/api/recordings/{rid}/segments", json={"segments": segs})
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    assert body2["changed"] is False, body2
    assert body2["version_created"] is False, body2
    assert _version_count(rid) == 1
    assert body2["updated_at"] == stamp  # kein unnötiger Schreibvorgang
    # Kein Fehler, aber auch kein Speichererfolg — die Antwort sagt es ehrlich.


def test_put_geaenderter_inhalt_erzeugt_neue_version(client):
    rid = _make_done_recording(client, [_seg(0, 10, "eins zwei", _words(0, 10, "eins", "zwei"))])
    erst = [_seg(0, 10, "eins zwei drei", _words(0, 10, "eins", "zwei", "drei"))]

    r = client.put(f"/api/recordings/{rid}/segments", json={"segments": erst})
    assert r.status_code == 200, r.text
    assert _version_count(rid) == 1

    changed = [_seg(0, 10, "eins zwei VIER", _words(0, 10, "eins", "zwei", "VIER"))]
    r2 = client.put(f"/api/recordings/{rid}/segments", json={"segments": changed})
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    assert body2["changed"] is True and body2["version_created"] is True
    assert body2["text"] == "eins zwei VIER"
    assert _version_count(rid) == 2

    # und der identische Stand danach wieder nicht
    r3 = client.put(f"/api/recordings/{rid}/segments", json={"segments": changed})
    assert r3.status_code == 200, r3.text
    assert r3.json()["version_created"] is False
    assert _version_count(rid) == 2


def test_put_leeres_segment_unter_mehreren_aendert_verhalten_nicht(client):
    """Change 213 bleibt unangetastet: leere Segmente fallen still aus der
    Liste (Client filtert), die Dedupe-Regel greift danach unverändert."""
    segs = [
        _seg(0, 5, "eins", _words(0, 5, "eins")),
        _seg(5, 10, "zwei", _words(5, 10, "zwei")),
        _seg(10, 15, "drei", _words(10, 15, "drei")),
    ]
    rid = _make_done_recording(client, segs)

    # Ein leeres Segment unter mehreren: unverändert 400 (Invariante
    # „kein Segment ohne Text") und KEINE Version.
    mit_leerem = [segs[0], _seg(5, 10, ""), segs[2]]
    r = client.put(f"/api/recordings/{rid}/segments", json={"segments": mit_leerem})
    assert r.status_code == 400, r.text
    assert _version_count(rid) == 0

    # Client-Verhalten (Change 213): leere Segmente weg, Rest speichern.
    gefuellt = [segs[0], segs[2]]
    r2 = client.put(f"/api/recordings/{rid}/segments", json={"segments": gefuellt})
    assert r2.status_code == 200, r2.text
    assert r2.json()["version_created"] is True
    assert _version_count(rid) == 1

    # Zweimal derselbe (gefilterte) Stand → weiterhin genau EINE Version.
    r3 = client.put(f"/api/recordings/{rid}/segments", json={"segments": gefuellt})
    assert r3.status_code == 200, r3.text
    assert r3.json()["changed"] is False
    assert _version_count(rid) == 1


def test_put_autosave_ohne_version_bleibt_ohne_version(client):
    """Change 068 bleibt gültig: create_version=false legt nie eine an."""
    segs = [_seg(0, 10, "eins zwei", _words(0, 10, "eins", "zwei"))]
    rid = _make_done_recording(client, segs)

    r = client.put(
        f"/api/recordings/{rid}/segments?create_version=false",
        json={"segments": [_seg(0, 10, "eins zwei drei", _words(0, 10, "eins", "zwei", "drei"))]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["changed"] is True
    assert r.json()["version_created"] is False
    assert _version_count(rid) == 0
