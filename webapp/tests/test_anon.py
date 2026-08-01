"""Anonyme User (Task B1/B2) — Modell-Felder, Config-Defaults, Namen."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session, SQLModel, create_engine

from app.anon_names import generate_name
from app.config import settings
from app.models import User


def test_anon_name_three_words():
    parts = generate_name().split()
    assert len(parts) == 3
    assert all(p.istitle() for p in parts)


def test_anon_names_vary():
    assert len({generate_name() for _ in range(50)}) > 40


def test_user_kind_anonymous_roundtrip(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        u = User(sub="anon:x", kind="anonymous", display_name=generate_name(),
                 last_seen_at=datetime.now(timezone.utc))
        s.add(u)
        s.commit()
        s.refresh(u)
        assert u.kind == "anonymous"
        assert u.display_name
        assert u.last_seen_at is not None


def test_user_default_kind_oidc(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        u = User(sub="oidc-sub")
        s.add(u)
        s.commit()
        s.refresh(u)
        assert u.kind == "oidc"
        assert u.display_name is None
        assert u.last_seen_at is None


def test_anon_config_defaults():
    assert settings.POLYSCHNACK_ANON_RETENTION_MINUTES == 15
    assert settings.POLYSCHNACK_ANON_MAX_DURATION_S >= 60
    assert settings.POLYSCHNACK_ANON_MAX_DISK_MB >= 50
    assert settings.POLYSCHNACK_ANON_MAX_UPLOAD_MB >= 10
