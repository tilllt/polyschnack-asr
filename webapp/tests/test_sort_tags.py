"""Change 054 — Sortierung, Tag-Filter, Tags-Route, „Last edit date".

Deckt ab:
- list_recordings: sort (date|edited|name|filename|length) + dir (desc|asc),
  NULL-Dauern ans Ende, Tag-Filter (ODER, case-insensitiv) + Kombination mit q
- PATCH /api/recordings/{uid}/tags: dedup/trim, Limits, write-Auth
- updated_at wird bei Segment-PUT/PATCH und Titel-/Tag-Änderung aktualisiert
- Serialisierung enthält ``tags``
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.crud import list_recordings
from app.models import Recording, User
from app.routers import recordings


def _utc(days_ago: int) -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_ago)


@pytest.fixture()
def db(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/sort.db")
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(User(id=1, sub="u1"))
        # Reihenfolge der IDs = Anlage-Reihenfolge; created_at explizit.
        s.add(Recording(id=1, uid="r1", original_name="zulu.mp3", stored_path="p",
                        user_id=1, title="Alpha", duration_s=None,
                        tags=["walzen", "Review"], created_at=_utc(10),
                        updated_at=_utc(10)))
        s.add(Recording(id=2, uid="r2", original_name="alpha.mp3", stored_path="p",
                        user_id=1, title=None, duration_s=500.0,
                        tags=["schellack"], created_at=_utc(5),
                        updated_at=_utc(3)))
        s.add(Recording(id=3, uid="r3", original_name="bravo.mp3", stored_path="p",
                        user_id=1, title="bravo", duration_s=120.0,
                        tags=[], created_at=_utc(2), updated_at=_utc(2)))
        s.add(Recording(id=4, uid="r4", original_name="delta.mp3", stored_path="p",
                        user_id=1, title=None, duration_s=30.0,
                        tags=["walzen"], created_at=_utc(1), updated_at=_utc(1)))
        s.commit()
    return eng


def _uids(rows) -> list[str]:
    return [r.uid for r in rows]


# ---------------------------------------------------------------------------
# Change 092 — GET /api/tags (Autocomplete-Vorschläge, User-Isoliert)
# ---------------------------------------------------------------------------


def test_list_all_tags_dedup_sort_user_isolated(db):
    """GET /tags liefert deduplizierte (case-insensitiv), sortierte Tags —
    nur die des aktuellen Users."""
    with Session(db) as s:
        tags = recordings.list_all_tags(
            request=_FakeRequest(session={"user_id": 1}), session=s)
    # r1: walzen + Review; r2: schellack; r4: walzen (Duplikat).
    # Erste Schreibweise gewinnt („Review"); sortiert case-insensitiv.
    assert tags == ["Review", "schellack", "walzen"]

    # Anderer User (id=99, keine Recordings) → leer
    with Session(db) as s:
        assert recordings.list_all_tags(
            request=_FakeRequest(session={"user_id": 99}), session=s) == []


# ---------------------------------------------------------------------------
# Sortierung (crud-Ebene)
# ---------------------------------------------------------------------------


def test_default_sort_is_date_desc(db):
    with Session(db) as s:
        rows = list_recordings(s, user_id=1)
        assert _uids(rows) == ["r4", "r3", "r2", "r1"]


def test_sort_edited_asc(db):
    with Session(db) as s:
        rows = list_recordings(s, user_id=1, sort="edited", dir="asc")
        # asc = älteste Bearbeitung zuerst: r1 (10 T) → r2 (3) → r3 (2) → r4 (1)
        assert _uids(rows) == ["r1", "r2", "r3", "r4"]


def test_sort_edited_desc(db):
    with Session(db) as s:
        rows = list_recordings(s, user_id=1, sort="edited", dir="desc")
        assert _uids(rows) == ["r4", "r3", "r2", "r1"]


def test_sort_name_uses_title_with_filename_fallback(db):
    with Session(db) as s:
        rows = list_recordings(s, user_id=1, sort="name", dir="asc")
        # r1 "Alpha", r2 (kein Titel → "alpha.mp3"), r3 "bravo", r4 "delta.mp3"
        assert _uids(rows) == ["r1", "r2", "r3", "r4"]


def test_sort_filename_asc(db):
    with Session(db) as s:
        rows = list_recordings(s, user_id=1, sort="filename", dir="asc")
        assert _uids(rows) == ["r2", "r3", "r4", "r1"]  # alpha, bravo, delta, zulu


def test_sort_length_desc_with_nulls_last(db):
    with Session(db) as s:
        rows = list_recordings(s, user_id=1, sort="length", dir="desc")
        # r2 500 → r3 120 → r4 30 → r1 None (ans Ende, obwohl desc)
        assert _uids(rows) == ["r2", "r3", "r4", "r1"]


def test_sort_length_asc_with_nulls_last(db):
    with Session(db) as s:
        rows = list_recordings(s, user_id=1, sort="length", dir="asc")
        assert _uids(rows) == ["r4", "r3", "r2", "r1"]


def test_unknown_sort_falls_back_to_date(db):
    with Session(db) as s:
        rows = list_recordings(s, user_id=1, sort="bogus")
        assert _uids(rows) == ["r4", "r3", "r2", "r1"]


# ---------------------------------------------------------------------------
# Tag-Filter (crud-Ebene)
# ---------------------------------------------------------------------------


def test_tag_filter_single(db):
    with Session(db) as s:
        rows = list_recordings(s, user_id=1, tags=["walzen"])
        assert set(_uids(rows)) == {"r1", "r4"}


def test_tag_filter_or_multiple(db):
    with Session(db) as s:
        rows = list_recordings(s, user_id=1, tags=["schellack", "review"])
        assert set(_uids(rows)) == {"r1", "r2"}


def test_tag_filter_case_insensitive(db):
    with Session(db) as s:
        rows = list_recordings(s, user_id=1, tags=["WALZEN"])
        assert set(_uids(rows)) == {"r1", "r4"}


def test_tag_filter_combined_with_search_q(db):
    with Session(db) as s:
        rows = list_recordings(s, user_id=1, tags=["walzen"], q="zulu")
        assert _uids(rows) == ["r1"]


def test_tag_filter_empty_tags_noop(db):
    with Session(db) as s:
        rows = list_recordings(s, user_id=1, tags=[None, ""])
        assert len(rows) == 4


# ---------------------------------------------------------------------------
# Tags-Route (Endpoint-Ebene)
# ---------------------------------------------------------------------------


class _FakeRequest:
    def __init__(self, session=None):
        self.session = session or {}


@pytest.fixture(autouse=True)
def _patch_auth(monkeypatch):
    monkeypatch.setattr(recordings.settings, "OIDC_ENABLED", True)
    monkeypatch.setattr(
        recordings, "_current_user",
        lambda request, session=None: request.session.get("user_id"))
    monkeypatch.setattr(recordings, "_key_cap", lambda request, session=None: None)
    monkeypatch.setattr(recordings, "_is_admin_session", lambda request: False)


def test_patch_tags_dedup_trim_and_returns(db):
    with Session(db) as s:
        out = recordings.set_recording_tags(
            "r1", recordings.TagsBody(tags=["  Walzen ", "walzen", "", "neu"]),
            request=_FakeRequest(session={"user_id": 1}), session=s)
        assert out["tags"] == ["Walzen", "neu"]
        rec = s.get(Recording, 1)
        assert rec.tags == ["Walzen", "neu"]


def test_patch_tags_updates_updated_at(db):
    with Session(db) as s:
        before = s.get(Recording, 1).updated_at
        recordings.set_recording_tags(
            "r1", recordings.TagsBody(tags=["x"]),
            request=_FakeRequest(session={"user_id": 1}), session=s)
        after = s.get(Recording, 1).updated_at
        assert after >= before


def test_patch_tags_rejects_too_long(db):
    with Session(db) as s:
        with pytest.raises(Exception) as ei:
            recordings.set_recording_tags(
                "r1", recordings.TagsBody(tags=["x" * 41]),
                request=_FakeRequest(session={"user_id": 1}), session=s)
        assert getattr(ei.value, "status_code", 0) == 400


def test_patch_tags_rejects_more_than_20(db):
    with Session(db) as s:
        with pytest.raises(Exception) as ei:
            recordings.set_recording_tags(
                "r1", recordings.TagsBody(tags=[f"t{i}" for i in range(21)]),
                request=_FakeRequest(session={"user_id": 1}), session=s)
        assert getattr(ei.value, "status_code", 0) == 400


def test_patch_tags_requires_write_access(db):
    """User 99 ist weder Owner noch Share-Empfänger → kein write-Zugriff."""
    from fastapi import HTTPException

    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            recordings.set_recording_tags(
                "r1", recordings.TagsBody(tags=["x"]),
                request=_FakeRequest(session={"user_id": 99}), session=s)
        assert ei.value.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Serialisierung
# ---------------------------------------------------------------------------


def test_serialization_contains_tags(db):
    with Session(db) as s:
        rec = s.get(Recording, 1)
        d = recordings._recording_to_dict(rec)
        assert d["tags"] == ["walzen", "Review"]
        assert d["updated_at"] is not None
