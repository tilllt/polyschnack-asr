"""SEO-Schutz: Keine PolySchnack-Seite (inkl. Anon-Share-Links) darf
von Suchmaschinen indiziert werden.

- /robots.txt → Disallow: / (immer erreichbar, auch ohne SPA-Build)
- X-Robots-Tag: noindex, nofollow auf ALLEN Responses (Middleware)
- index.html enthält noindex-Meta (Frontend-Build)
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from sqlmodel import SQLModel, Session, create_engine

    from app import db as db_module
    from app.main import app

    eng = create_engine(f"sqlite:///{tmp_path / 'seo.db'}",
                        connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)

    with TestClient(app) as c:
        yield c


def test_robots_txt_disallows_all(client):
    r = client.get("/robots.txt")
    assert r.status_code == 200
    assert "User-agent: *" in r.text
    assert "Disallow: /" in r.text


def test_robots_txt_auch_ohne_spa_build(client):
    """robots.txt ist eine eigene Route — nicht abhängig vom SPA-Build."""
    r = client.get("/robots.txt")
    assert r.status_code == 200


def test_all_responses_have_noindex_header(client):
    r = client.get("/api/stats")
    assert r.status_code == 200
    tag = r.headers.get("x-robots-tag", "")
    assert "noindex" in tag.lower()
    assert "nofollow" in tag.lower()


def test_share_page_noindex_header(client):
    """Anon-Share-Link-Aufrufe tragen ebenfalls den noindex-Header."""
    r = client.get("/r/0123456789abcdef0123456789abcdef")
    tag = r.headers.get("x-robots-tag", "")
    assert "noindex" in tag.lower()


def test_frontend_index_has_noindex_meta():
    """Die SPA-index.html enthält <meta name=robots content=noindex>."""
    idx = Path(__file__).resolve().parent.parent / "frontend" / "index.html"
    if not idx.exists():
        pytest.skip("frontend/index.html fehlt (kein Frontend-Checkout)")
    html = idx.read_text()
    assert 'name="robots"' in html
    assert "noindex" in html
