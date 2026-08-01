"""Harte Limits für anonyme User (Task B5)."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine

from app.anon_limits import enforce_anon_limits
from app.config import settings
from app.models import Recording, User


@pytest.fixture()
def db(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    SQLModel.metadata.create_all(eng)
    return eng


class _Anon:
    id = 1
    kind = "anonymous"


class _Oidc:
    id = 2
    kind = "oidc"


def test_oidc_user_unlimited(db):
    with Session(db) as s:
        enforce_anon_limits(s, _Oidc(), 10 * 1024 * 1024 * 1024, duration_s=99999)


def test_anon_duration_over_limit(db):
    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            enforce_anon_limits(s, _Anon(), 1000, duration_s=settings.POLYSCHNACK_ANON_MAX_DURATION_S + 1)
        assert ei.value.status_code == 409


def test_anon_upload_over_limit(db):
    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            enforce_anon_limits(s, _Anon(),
                                settings.POLYSCHNACK_ANON_MAX_UPLOAD_MB * 1024 * 1024 + 1,
                                duration_s=10)
        assert ei.value.status_code == 413


def test_anon_disk_quota_reached(db):
    with Session(db) as s:
        s.add(Recording(id=1, uid="r1", original_name="a", stored_path="p",
                        user_id=1, size_bytes=settings.POLYSCHNACK_ANON_MAX_DISK_MB * 1024 * 1024))
        s.commit()
    with Session(db) as s:
        with pytest.raises(HTTPException) as ei:
            enforce_anon_limits(s, _Anon(), 1, duration_s=10)
        assert ei.value.status_code == 413


def test_anon_within_limits_ok(db):
    with Session(db) as s:
        enforce_anon_limits(s, _Anon(), 1000, duration_s=10)
