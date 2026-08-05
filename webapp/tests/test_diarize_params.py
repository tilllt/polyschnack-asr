"""Diarization-Parameter (Option B): num_speakers → diarize_max_speakers.

Punkt 1 des Parameter-Menüs:
1. Sprecheranzahl → diarize_max_speakers (CrispASR-Feld, Upper Bound)
2. Methode (pyannote|foxnose|…) → diarize_method (Task: foxnose)

Bewusste Abweichung seit Option B: ``min_duration_off`` (Sensitivität) hat
in CrispASR keine direkte Entsprechung und wird NICHT übertragen —
nächster Hebel wäre diarize_cluster_threshold (anderes Semantikfeld).
"""
import httpx
import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine

from app.diarize import diarize
from app.config import settings
from app.models import Recording, User
from app.routers import recordings


class _FakeClient:
    def __init__(self):
        self.last_kwargs = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, files=None, data=None):
        self.last_kwargs = {"url": url, "files": files, "data": data}
        return httpx.Response(200, json={"segments": []})


def _patch(monkeypatch):
    fc = _FakeClient()
    monkeypatch.setattr("app.diarize.httpx.Client", lambda *a, **k: fc)
    monkeypatch.setattr(settings, "DIAR_URL", "http://crispr-crispr-diar:5098")
    return fc


def test_diarize_reicht_max_speakers_durch(monkeypatch, tmp_path):
    fc = _patch(monkeypatch)
    p = tmp_path / "x.wav"
    p.write_bytes(b"RIFF....")
    diarize(str(p), num_speakers=2)
    assert fc.last_kwargs["data"]["diarize_max_speakers"] == "2"


def test_diarize_ohne_num_speakers_kein_feld(monkeypatch, tmp_path):
    fc = _patch(monkeypatch)
    p = tmp_path / "x.wav"
    p.write_bytes(b"RIFF....")
    diarize(str(p))
    assert "diarize_max_speakers" not in fc.last_kwargs["data"]


def test_diarize_min_duration_off_wird_nicht_uebertragen(monkeypatch, tmp_path):
    """CrispASR kennt kein min_duration_off — Parameter wird ignoriert."""
    fc = _patch(monkeypatch)
    p = tmp_path / "x.wav"
    p.write_bytes(b"RIFF....")
    diarize(str(p), min_duration_off=0.4)
    data = fc.last_kwargs["data"]
    assert "min_duration_off" not in data
    assert "diarize_cluster_threshold" not in data  # bewusst nicht gemappt


def test_diarize_default_method_aus_settings(monkeypatch, tmp_path):
    """Ohne explizite Methode greift settings.DIARIZE_METHOD (Default pyannote)."""
    fc = _patch(monkeypatch)
    p = tmp_path / "x.wav"
    p.write_bytes(b"RIFF....")
    diarize(str(p))
    assert fc.last_kwargs["data"]["diarize_method"] == "pyannote"


def test_diarize_reicht_explizite_methode_durch(monkeypatch, tmp_path):
    fc = _patch(monkeypatch)
    p = tmp_path / "x.wav"
    p.write_bytes(b"RIFF....")
    diarize(str(p), method="foxnose")
    assert fc.last_kwargs["data"]["diarize_method"] == "foxnose"


def test_diarize_invalid_method_wirft_valueerror(monkeypatch, tmp_path):
    """Unbekannte Methode → Whitelist-Fehler statt stiller Default.

    Bewusst hart: ein Tippfehler (z. B. \"foxnoze\") darf nicht lautlos
    pyannote ausführen — das wäre ein stiller Fehler. Raise ValueError.
    """
    fc = _patch(monkeypatch)
    p = tmp_path / "x.wav"
    p.write_bytes(b"RIFF....")
    try:
        diarize(str(p), method="foxnoze")
    except ValueError as exc:
        assert "foxnoze" in str(exc)
    else:
        raise AssertionError("unbekannte Methode muss ValueError werfen")


# ------------------------------------------------------------ Endpoint-Durchstich


class _FakeRequest:
    def __init__(self, session=None):
        self.session = session or {}


@pytest.fixture(autouse=True)
def _patch_user(monkeypatch):
    monkeypatch.setattr(recordings.settings, "OIDC_ENABLED", True)
    monkeypatch.setattr(recordings, "_current_user",
                        lambda request, session=None: request.session.get("user_id"))


@pytest.fixture()
def db(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(User(id=1, sub="oidc-user"))
        s.add(Recording(id=1, uid="r1", original_name="a.mp3", stored_path="p",
                        user_id=1, status="uploaded"))
        s.commit()
    return eng


@pytest.fixture()
def qm(monkeypatch):
    calls = []
    monkeypatch.setattr(recordings.queue_manager, "enqueue",
                        lambda *a, **k: calls.append(a) or 1)
    return calls


def _req(uid=None):
    return _FakeRequest(session={"user_id": uid} if uid is not None else {})


def test_transcribe_persistiert_diarize_method(db, qm):
    """transcribe_ep übernimmt diarize_method in die Recording-Zeile
    (Durchstich bis zum Worker: rec.diarize_method → diarize(method=...))."""
    with Session(db) as s:
        r = recordings.transcribe_ep(
            "r1", _req(1), enable_vad=False, enable_diarize=True,
            diarize_num_speakers=None, diarize_min_duration_off=None,
            diarize_method="foxnose",
            enable_streaming=False, enable_noise_reduce=True, enable_enhance="off",
            enable_punctuation=None, enable_llm_enhance=None,
            prompt_template_id=None, delivery_target_id=None, llm_endpoint_id=None,
            backend="", session=s,
        )
        assert r["status"] in ("queued", "processing") or r is not None
        rec = s.get(Recording, 1)
        assert rec.diarize_method == "foxnose"


def test_transcribe_ohne_methode_null(db, qm):
    """Kein diarize_method im Request → Feld bleibt None (Server-Default)."""
    with Session(db) as s:
        recordings.transcribe_ep(
            "r1", _req(1), enable_vad=False, enable_diarize=True,
            diarize_num_speakers=None, diarize_min_duration_off=None,
            diarize_method=None,
            enable_streaming=False, enable_noise_reduce=True, enable_enhance="off",
            enable_punctuation=None, enable_llm_enhance=None,
            prompt_template_id=None, delivery_target_id=None, llm_endpoint_id=None,
            backend="", session=s,
        )
        rec = s.get(Recording, 1)
        assert rec.diarize_method is None
