"""Change 114 Regressionstests: VAD-Modi (off|edges|all) user-konfigurierbar.

- vad_mode wird von den Routen in den Run übernommen (ohne Env-Gate).
- _apply_vad liefert vad_meta (shift/map); _remap_segments mappt Timestamps
  forward/inverse; der Align-Cache transportiert das Meta kompatibel.
"""

import io
import wave
from pathlib import Path

import pytest


def _wav_bytes(duration_s: float = 1.0) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(duration_s * 16000))
    return buf.getvalue()


# ------------------------------------------------------------ _run_vad_mode --

def test_run_vad_mode_legacy_fallback():
    from app.service import _run_vad_mode

    class _R:
        def __init__(self, vad_mode=None, enable_vad=False):
            self.vad_mode = vad_mode
            self.enable_vad = enable_vad

    assert _run_vad_mode(None) == "off"
    assert _run_vad_mode(_R(vad_mode="all")) == "all"
    assert _run_vad_mode(_R(vad_mode="edges")) == "edges"
    assert _run_vad_mode(_R(vad_mode="", enable_vad=True)) == "edges"   # Legacy
    assert _run_vad_mode(_R(vad_mode=None, enable_vad=False)) == "off"  # Legacy
    assert _run_vad_mode(_R(vad_mode="", enable_vad=False)) == "off"


# -------------------------------------------------------------- _apply_vad --

def test_apply_vad_off_unveraendert():
    from app.service import _apply_vad
    data = _wav_bytes()
    out, meta = _apply_vad(data, "off")
    assert out == data and meta is None


def test_apply_vad_edges_shift_meta(monkeypatch):
    import app.service as service
    data = _wav_bytes(2.0)
    monkeypatch.setattr(service, "_trim_silence", lambda b: (b"TRIMMED", 1.25))
    out, meta = service._apply_vad(data, "edges")
    assert out == b"TRIMMED"
    assert meta == {"type": "shift", "offset_s": 1.25}


def test_apply_vad_all_map_meta(monkeypatch):
    import app.service as service
    data = _wav_bytes(2.0)
    monkeypatch.setattr("app.vad.squash_silence_with_mapping",
                        lambda b: (b"SQUASHED", [(0.5, 1.5, 0.0)]))
    out, meta = service._apply_vad(data, "all")
    assert out == b"SQUASHED"
    assert meta == {"type": "map", "mapping": [[0.5, 1.5, 0.0]]}


def test_apply_vad_all_fallback_ohne_regionen():
    """Keine Speech-Region (Modell fehlt) → Original unverändert, kein Abbruch."""
    import app.service as service
    data = _wav_bytes(2.0)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("app.vad.squash_silence_with_mapping", lambda b: (b, []))
    try:
        out, meta = service._apply_vad(data, "all")
    finally:
        monkeypatch.undo()
    assert out == data and meta is None


# --------------------------------------------------------- _remap_segments --

def test_remap_segments_forward_und_inverse():
    from app.service import _remap_segments
    mapping = [[1.0, 3.0, 0.0], [5.0, 7.0, 2.5]]
    segs = [
        {"start": 1.5, "end": 2.5, "words": [{"start": 2.0, "end": 2.2}]},
        {"start_ms": 6000.0, "end_ms": 6500.0, "words": []},
    ]
    # forward: Original → squashed
    _remap_segments(segs, mapping, inverse=False)
    assert segs[0]["start"] == pytest.approx(0.5)   # 1.5 in Region 1 → 0.0+(1.5-1.0)
    assert segs[0]["end"] == pytest.approx(1.5)
    assert segs[0]["words"][0]["start"] == pytest.approx(1.0)
    assert segs[1]["start_ms"] == pytest.approx(3500.0)  # 6.0s in Region 2 → 2.5+(6-5)
    # inverse: squashed → Original (Roundtrip)
    _remap_segments(segs, mapping, inverse=True)
    assert segs[0]["start"] == pytest.approx(1.5)
    assert segs[0]["words"][0]["start"] == pytest.approx(2.0)
    assert segs[1]["start_ms"] == pytest.approx(6000.0)


def test_remap_roundtrip_exakt_fuer_alle_zeitpunkte_in_regionen():
    """Zeitreferenz-Frage (User 24.08.): Forward+Inverse ist für ALLE
    Zeitpunkte INNERHALB von Speech-Regionen exakt (100%-Wiederherstellung).

    Systematisch: viele Zeitpunkte in beiden Regionen (inkl. Grenzen
    alt_start/alt_end), Segment- UND Wort-Ebene, start/end UND ms-Felder.
    """
    from app.service import _map_time, _unmap_time
    mapping = [[1.0, 3.0, 0.0], [5.0, 7.0, 2.5]]
    for t in [1.0, 1.0001, 1.5, 2.9999, 3.0, 5.0, 5.5, 6.9999, 7.0]:
        # forward (Original→squashed) dann inverse (squashed→Original)
        t_squashed = _map_time(t, mapping)
        t_back = _unmap_time(t_squashed, mapping)
        assert t_back == pytest.approx(t, abs=1e-9), f"Roundtrip fehlt bei t={t}"


def test_remap_grenzfaelle_definierte_semantik():
    """Zeitpunkte in ENTFERNTEN Lücken (zwischen Regionen) haben kein
    Original-Pendant — die Zeit existiert im gesquashten Audio nicht mehr.
    Definierte Semantik: clamp auf die nächste Regionskante. Das ist kein
    exakter Roundtrip (mathematisch unmöglich), aber deterministisch."""
    from app.service import _map_time, _unmap_time
    mapping = [[1.0, 3.0, 0.0], [5.0, 7.0, 2.5]]
    # t=4.0 liegt in der entfernten Lücke → clamp auf Ende Region 1 (squashed)
    assert _map_time(4.0, mapping) == pytest.approx(2.0)
    # t vor der ersten Region → 0.0
    assert _map_time(0.5, mapping) == pytest.approx(0.0)
    # t nach der letzten Region → Ende der letzten Region (squashed)
    assert _map_time(8.0, mapping) == pytest.approx(4.5)
    # inverse: squashed-Zeit in einer Fuge → Anfang/Ende der Region
    assert _unmap_time(2.25, mapping) == pytest.approx(3.0)  # Fuge zwischen Regionen
    assert _unmap_time(-1.0, mapping) == pytest.approx(1.0)  # vor Region 1


def test_remap_kette_apply_vad_all_align_roundtrip(monkeypatch):
    """Komplette Kette (Align-Pfad, Change 114): squash → forward (Job) →
    inverse (Worker) → exakte Original-Zeiten für alle Regionen-Zeitpunkte."""
    import app.service as service
    from app.service import _apply_vad, _remap_segments

    mapping = [[0.5, 1.5, 0.0], [2.0, 4.0, 1.0]]
    monkeypatch.setattr("app.vad.squash_silence_with_mapping",
                        lambda b: (b"SQ", [(a, b2, c) for a, b2, c in mapping]))
    _, vad_meta = _apply_vad(b"RAW", "all")
    assert vad_meta["type"] == "map"

    # Segmente auf Original-Achse (wie aus der DB nach Job-Kompensation)
    segs = [{"start": 0.7, "end": 1.2, "words": [{"start": 2.5, "end": 3.0}]}]
    orig = [segs[0]["start"], segs[0]["end"], segs[0]["words"][0]["start"]]

    # Job: forward (Original → squashed) — Aligner arbeitet auf squashed
    _remap_segments(segs, vad_meta["mapping"], inverse=False)
    # Worker: inverse (squashed → Original) — exakt zurück
    _remap_segments(segs, vad_meta["mapping"], inverse=True)

    assert segs[0]["start"] == pytest.approx(orig[0])
    assert segs[0]["end"] == pytest.approx(orig[1])
    assert segs[0]["words"][0]["start"] == pytest.approx(orig[2])


# ------------------------------------------------------ Align-Cache (meta) --

def test_align_cache_vad_meta_shift_und_alt(tmp_path, monkeypatch):
    import app.service as service
    monkeypatch.setattr(service._AlignmentCache, "_DIR", tmp_path / ".align-cache")
    service._AlignmentCache.write(1, b"X", {"type": "shift", "offset_s": 2.0})
    assert service._AlignmentCache.read_vad_meta(1) == {"type": "shift", "offset_s": 2.0}
    assert service._AlignmentCache.read_meta(1) == 0.0  # kein trim_offset_s-Feld

    # Alt-Format: float trim_offset_s → read_vad_meta liefert shift-Äquivalent
    service._AlignmentCache.write(2, b"Y", 1.5)
    assert service._AlignmentCache.read_meta(2) == 1.5
    assert service._AlignmentCache.read_vad_meta(2) == {"type": "shift", "offset_s": 1.5}

    # map-Format
    service._AlignmentCache.write(3, b"Z", {"type": "map", "mapping": [[0.5, 1.5, 0.0]]})
    assert service._AlignmentCache.read_vad_meta(3)["type"] == "map"


# ------------------------------------------------- Route vad_mode-Übernahme --

def test_upload_speichert_vad_mode(tmp_path, monkeypatch):
    from app import db as db_module
    from app.main import app
    from sqlmodel import Session, SQLModel, create_engine, select
    from fastapi.testclient import TestClient
    from app.models import TranscriptionRun

    eng = create_engine(f"sqlite:///{tmp_path / 't.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    from app.config import settings
    monkeypatch.setattr(settings, "OIDC_ENABLED", False)
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "AUDIO_DIR", tmp_path / "audio")
    monkeypatch.setattr(settings, "DB_PATH", tmp_path / "t.db")
    (tmp_path / "audio").mkdir(exist_ok=True)
    with TestClient(app) as c:
        r = c.post("/api/recordings",
                   files={"file": ("v.wav", _wav_bytes(), "audio/wav")},
                   data={"name": "v.wav", "vad_mode": "all"})
        assert r.status_code == 201, r.text
    with Session(eng) as s:
        run = s.exec(select(TranscriptionRun).order_by(TranscriptionRun.id.asc())).first()
        assert run is not None
        assert run.vad_mode == "all"
        assert run.enable_vad is True  # abgeleitet


def test_upload_vad_legacy_enable_vad_true_ergibt_edges(tmp_path, monkeypatch):
    """Alt-Client sendet nur enable_vad=true → vad_mode "edges"."""
    from app import db as db_module
    from app.main import app
    from sqlmodel import Session, SQLModel, create_engine, select
    from fastapi.testclient import TestClient
    from app.models import TranscriptionRun

    eng = create_engine(f"sqlite:///{tmp_path / 't.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    from app.config import settings
    monkeypatch.setattr(settings, "OIDC_ENABLED", False)
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "AUDIO_DIR", tmp_path / "audio")
    monkeypatch.setattr(settings, "DB_PATH", tmp_path / "t.db")
    (tmp_path / "audio").mkdir(exist_ok=True)
    with TestClient(app) as c:
        r = c.post("/api/recordings",
                   files={"file": ("v.wav", _wav_bytes(), "audio/wav")},
                   data={"name": "v.wav", "enable_vad": "true"})
        assert r.status_code == 201, r.text
    with Session(eng) as s:
        run = s.exec(select(TranscriptionRun).order_by(TranscriptionRun.id.asc())).first()
        assert run.vad_mode == "edges"


def test_retranscribe_speichert_vad_mode(db, _patch_user, monkeypatch):
    from sqlmodel import Session
    from app.models import Recording, TranscriptionRun
    from app.routers import recordings

    with Session(db) as s:
        params = recordings.RetranscribeParams(vad_mode="all")
        recordings.retranscribe("r1", params, _req(1), s)
        rec = s.get(Recording, 1)
        run = s.get(TranscriptionRun, rec.current_run_id) if rec.current_run_id else None
        assert run is not None and run.vad_mode == "all" and run.enable_vad is True


@pytest.fixture()
def db(tmp_path, monkeypatch):
    from sqlmodel import Session, SQLModel, create_engine
    from app.models import Recording, User
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr("app.db.engine", eng)
    monkeypatch.setattr("app.service.engine", eng)
    monkeypatch.setattr("app.routers.recordings.engine", eng)  # Direkt-Import
    monkeypatch.setattr("app.db.engine", eng)  # queue liest db.engine zur Laufzeit
    with Session(eng) as s:
        s.add(User(id=1, sub="oidc-user"))
        audio = tmp_path / "a.mp3"
        audio.write_bytes(_wav_bytes(0.5))  # echtes Mini-WAV (ffmpeg-Konvertierung)
        s.add(Recording(id=1, uid="r1", original_name="a.mp3", stored_path=str(audio),
                        user_id=1, status="uploaded"))
        s.commit()
    return eng


class _FakeRequest:
    def __init__(self, session=None):
        self.session = session or {}


def _req(uid=None):
    return _FakeRequest(session={"user_id": uid} if uid is not None else {})


@pytest.fixture()
def _patch_user(monkeypatch):
    from app.routers import recordings
    monkeypatch.setattr(recordings.settings, "OIDC_ENABLED", True)
    monkeypatch.setattr(recordings, "_current_user",
                        lambda request, session=None: request.session.get("user_id"))
