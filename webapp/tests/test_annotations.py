"""Change 056 — Annotationen: Zeit-Ableitung, CRUD, Threads, Rechte."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine

from app.models import Annotation, Recording, RecordingShare, User
from app.routers import annotations as ann_mod

SEGS = [
    {"start": 0.0, "end": 2.0, "text": "Hallo Welt",
     "words": [{"word": "Hallo", "start": 0.0, "end": 1.0},
               {"word": "Welt", "start": 1.0, "end": 2.0}]},
    {"start": 2.0, "end": 4.0, "text": "zweiter Satz",
     "words": [{"word": "zweiter", "start": 2.0, "end": 3.0},
               {"word": "Satz", "start": 3.0, "end": 4.0}]},
    {"start": 4.0, "end": 6.0, "text": "ohne wörter"},
]


@pytest.fixture()
def db(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'ann.db'}")
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(User(id=1, sub="u1", name="Anna"))
        s.add(User(id=2, sub="u2", name="Ben"))
        # User 3 hat write-Share (darf annotieren/antworten, ist nicht Autor)
        s.add(User(id=3, sub="u3", name="Carla"))
        s.add(Recording(id=1, uid="r1", original_name="a.mp3", stored_path="p",
                        user_id=1, status="done", segments=SEGS))
        s.add(RecordingShare(rec_id=1, user_id=3, level="write"))
        s.commit()
    return eng


@pytest.fixture(autouse=True)
def _patch_auth(monkeypatch):
    from app.identity import Identity

    def _fake_identity(request, session=None):
        uid = request.session.get("user_id")
        return Identity(User(id=uid, sub=f"u{uid}"), None)

    import app.identity as identity_mod

    monkeypatch.setattr(identity_mod, "current_identity", _fake_identity)


class _Req:
    def __init__(self, user_id=1, session=None):
        self.session = session or {"user_id": user_id}


# ---------------------------------------------------------------------------
# Zeit-Ableitung
# ---------------------------------------------------------------------------


def test_time_window_from_words(db):
    with Session(db) as s:
        rec = s.get(Recording, 1)
        # Markierung über "Welt" (Pos 6..10): Wort "Welt" 1.0–2.0
        w = ann_mod._time_window(rec, 0, 6, 10)
        assert w == (1.0, 2.0)
        # Markierung über "Hallo Welt" (0..10): 0.0–2.0
        w2 = ann_mod._time_window(rec, 0, 0, 10)
        assert w2 == (0.0, 2.0)


def test_time_window_fallback_to_segment(db):
    with Session(db) as s:
        rec = s.get(Recording, 1)
        # Segment ohne Wörter → Segment-Grenzen
        w = ann_mod._time_window(rec, 2, 0, 5)
        assert w == (4.0, 6.0)


def test_time_window_out_of_range(db):
    with Session(db) as s:
        rec = s.get(Recording, 1)
        with pytest.raises(HTTPException) as ei:
            ann_mod._time_window(rec, 99, 0, 1)
        assert ei.value.status_code == 400


# ---------------------------------------------------------------------------
# CRUD + Threads
# ---------------------------------------------------------------------------


def test_create_annotation(db):
    with Session(db) as s:
        out = ann_mod.create_annotation(
            "r1", ann_mod.AnnotationCreate(segment_idx=0, char_start=6, char_end=10,
                                           body="**schwer verständlich**"),
            request=_Req(1), session=s)
        assert out["body"] == "**schwer verständlich**"
        assert out["start_s"] == 1.0 and out["end_s"] == 2.0
        assert out["user_id"] == 1 and out["user_name"] == "Anna"
        assert out["parent_id"] is None


def test_create_empty_body_400(db):
    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            ann_mod.create_annotation(
                "r1", ann_mod.AnnotationCreate(segment_idx=0, char_start=0,
                                               char_end=2, body="   "),
                request=_Req(1), session=s)
        assert ei.value.status_code == 400


def test_create_requires_write(db):
    # User 2: kein Owner/Share → write verweigert
    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            ann_mod.create_annotation(
                "r1", ann_mod.AnnotationCreate(segment_idx=0, char_start=0,
                                               char_end=2, body="x"),
                request=_Req(2), session=s)
        assert ei.value.status_code in (401, 403)


def test_list_sorted_by_start(db):
    with Session(db) as s:
        ann_mod.create_annotation(
            "r1", ann_mod.AnnotationCreate(segment_idx=2, char_start=0, char_end=3,
                                           body="spät"),
            request=_Req(1), session=s)
        ann_mod.create_annotation(
            "r1", ann_mod.AnnotationCreate(segment_idx=0, char_start=0, char_end=5,
                                           body="früh"),
            request=_Req(1), session=s)
        rows = ann_mod.list_annotations("r1", request=_Req(1), session=s)
        assert [r["body"] for r in rows] == ["früh", "spät"]


def test_list_requires_read(db):
    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            ann_mod.list_annotations("r1", request=_Req(2), session=s)
        assert ei.value.status_code in (401, 403)


def test_reply_inherits_window(db):
    with Session(db) as s:
        top = ann_mod.create_annotation(
            "r1", ann_mod.AnnotationCreate(segment_idx=0, char_start=6, char_end=10,
                                           body="top"),
            request=_Req(1), session=s)
        rep = ann_mod.reply_to_annotation(
            top["id"], ann_mod.AnnotationReply(body="Antwort von Carla"),
            request=_Req(3), session=s)
        assert rep["parent_id"] == top["id"]
        assert rep["start_s"] == top["start_s"] and rep["end_s"] == top["end_s"]
        assert rep["user_id"] == 3 and rep["user_name"] == "Carla"


def test_reply_on_reply_400(db):
    with Session(db) as s:
        top = ann_mod.create_annotation(
            "r1", ann_mod.AnnotationCreate(segment_idx=0, char_start=0, char_end=2,
                                           body="top"),
            request=_Req(1), session=s)
        rep = ann_mod.reply_to_annotation(
            top["id"], ann_mod.AnnotationReply(body="Antwort"),
            request=_Req(3), session=s)
        with pytest.raises(HTTPException) as ei:
            ann_mod.reply_to_annotation(
                rep["id"], ann_mod.AnnotationReply(body="noch eine"),
                request=_Req(1), session=s)
        assert ei.value.status_code == 400


def test_patch_only_author_or_admin(db):
    with Session(db) as s:
        ann = ann_mod.create_annotation(
            "r1", ann_mod.AnnotationCreate(segment_idx=0, char_start=0, char_end=2,
                                           body="original"),
            request=_Req(1), session=s)
        # fremder User (2) hat write auf die Recording nicht → 401/403
        with pytest.raises(HTTPException) as ei:
            ann_mod.update_annotation(
                ann["id"], ann_mod.AnnotationPatch(body="geändert"),
                request=_Req(2), session=s)
        assert ei.value.status_code in (401, 403)
        # Autor darf
        out = ann_mod.update_annotation(
            ann["id"], ann_mod.AnnotationPatch(body="geändert"),
            request=_Req(1), session=s)
        assert out["body"] == "geändert"


def test_delete_cascades_replies(db):
    with Session(db) as s:
        top = ann_mod.create_annotation(
            "r1", ann_mod.AnnotationCreate(segment_idx=0, char_start=0, char_end=2,
                                           body="top"),
            request=_Req(1), session=s)
        rep = ann_mod.reply_to_annotation(
            top["id"], ann_mod.AnnotationReply(body="Antwort"),
            request=_Req(3), session=s)
        out = ann_mod.delete_annotation(top["id"], request=_Req(1), session=s)
        assert out["replies_deleted"] == 1
        assert s.get(Annotation, top["id"]) is None
        assert s.get(Annotation, rep["id"]) is None
