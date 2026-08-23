"""Yjs-Kollaboration (Change 053): Room-Factory, Snapshot-Persistenz, Auth-Hook."""
import json

import pytest

# Optional: ohne pycrdt im Image/CI-Env wird die ganze Yjs-Suite übersprungen
# (der Editor fällt dann auf Solo-Modus zurück) — niemals Collection-Fehler.
pytest.importorskip("pycrdt")

from pycrdt import Doc, Map, Text  # noqa: E402

from app.yjs import build_yjs_mount, decode_session_cookie, make_on_connect  # noqa: E402
from app.yjs.rooms import FileProvider, DATA_DIR, _room_factory  # noqa: E402


def _make_doc_with_segments():
    doc = Doc()
    segments = Map()
    doc["segments"] = segments
    segments["0"] = Text("Hallo")
    return doc


def test_room_factory_creates_doc_and_provider(monkeypatch, tmp_path):
    monkeypatch.setattr("app.yjs.rooms.DATA_DIR", tmp_path)
    provider = _room_factory(path="/yjs/abc123")
    assert isinstance(provider, FileProvider)
    assert provider.path == "abc123"  # Pfad normalisiert (kein Slash im Dateinamen)
    assert "segments" in provider.doc


def test_room_factory_uses_room_doc(monkeypatch, tmp_path):
    """Review 2026-08-20: Das von YRoom übergebene Doc MUSS verwendet werden
    (Synchronisation + Snapshot laufen sonst ins Leere)."""
    monkeypatch.setattr("app.yjs.rooms.DATA_DIR", tmp_path)
    room_doc = Doc()
    provider = _room_factory(doc=room_doc, path="/yjs/abc123")
    assert provider.doc is room_doc
    # Maps werden auf dem übergebenen Doc angelegt, nicht auf einem eigenen.
    assert room_doc.get("segments", type=Map) is not None
    assert room_doc.get("meta", type=Map) is not None


def test_file_provider_snapshot_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr("app.yjs.rooms.DATA_DIR", tmp_path)
    # Echter Pfad: doc.observe feuert bei jeder Änderung → _on_change
    # appendet event.update in den Snapshot.
    doc = _make_doc_with_segments()
    p = FileProvider(doc, "room1")
    p.start()
    segs = doc["segments"]
    segs["0"] = Text("Neuer Text")  # observe → Snapshot-Update
    p.stop()
    assert (tmp_path / "room1.bin").exists()

    # Laden: frisches Doc wendet die Updates in Reihenfolge an
    doc2 = Doc()
    p2 = FileProvider(doc2, "room1")
    p2.start()
    segs2 = doc2.get("segments", type=Map)
    assert segs2 is not None and str(segs2.get("0")) == "Neuer Text"
    p2.stop()


def _make_cookie(secret: str, session: dict) -> str:
    """Session-Cookie exakt wie die aktuelle Starlette-SessionMiddleware."""
    import base64
    import json

    from itsdangerous import TimestampSigner

    signer = TimestampSigner(str(secret))
    payload = base64.b64encode(json.dumps(session).encode("utf-8"))
    return signer.sign(payload).decode("utf-8")


def test_decode_session_cookie_roundtrip():
    secret = "test-secret-123"
    cookie = _make_cookie(secret, {"kind": "oidc", "is_authenticated": True})
    assert decode_session_cookie(cookie, secret)["kind"] == "oidc"
    # Falsches Secret → None
    assert decode_session_cookie(cookie, "falsches-secret") is None


def test_on_connect_access_control(monkeypatch, tmp_path):
    """Change 053-Review: WS-Zugriff = Session + write-Freigabe (Owner/Share),
    konsistent zur Segment-Edit-Route."""
    monkeypatch.setattr("app.yjs.rooms.DATA_DIR", tmp_path)
    # Change 099-Review: vorher schrieb der Test in die ECHTE app-DB
    # (perf-DB) — beim 2. Lauf UNIQUE-Kollision. Eigene tmp-Engine:
    # make_on_connect importiert `from ..db import engine` lazy → wirkt.
    from sqlmodel import create_engine

    test_eng = create_engine(f"sqlite:///{tmp_path}/yjs.db")
    monkeypatch.setattr("app.db.engine", test_eng)
    from app.db import init_db
    from sqlmodel import Session as _DbSession
    from app.models import Recording, RecordingShare, User

    init_db()
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"MP3DATA")
    with _DbSession(test_eng) as db:
        db.add(User(id=101, sub="yjs-owner", preferred_username="alice"))
        db.add(User(id=102, sub="yjs-other", preferred_username="bob"))
        db.add(Recording(id=101, uid="yjs-own", original_name="a.mp3",
                         stored_path=str(audio), user_id=101, status="done",
                         text="Hallo", segments=[]))
        db.add(Recording(id=102, uid="yjs-shared", original_name="p.mp3",
                         stored_path=str(audio), user_id=102, status="done",
                         text="public", segments=[]))
        db.add(RecordingShare(rec_id=102, user_id=101, level="write"))
        db.commit()

    secret = "test-secret-123"
    on_connect = make_on_connect(secret)

    def scope_for(uid: str, user_id: int | None):
        headers = []
        if user_id is not None:
            cookie = _make_cookie(secret, {"user_id": user_id})
            headers = [(b"cookie", f"session={cookie}".encode())]
        return {"path": f"/yjs/{uid}", "headers": headers}

    assert on_connect(None, scope_for("yjs-own", 101)) is False      # Owner
    assert on_connect(None, scope_for("yjs-shared", 101)) is False   # Share write
    assert on_connect(None, scope_for("yjs-shared", 102)) is False   # Owner
    assert on_connect(None, scope_for("yjs-own", 102)) is True       # fremd, kein Share
    assert on_connect(None, scope_for("unbekannt", 101)) is True     # Recording fehlt
    assert on_connect(None, scope_for("yjs-own", None)) is True      # kein Cookie
    anon_cookie = _make_cookie(secret, {})
    assert on_connect(None, {"path": "/yjs/yjs-own",
                             "headers": [(b"cookie", f"session={anon_cookie}".encode())]}) is True


def test_build_yjs_mount_returns_asgi_app():
    app = build_yjs_mount("secret")
    assert callable(app)
