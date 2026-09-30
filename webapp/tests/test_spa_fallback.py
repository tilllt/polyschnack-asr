"""SPA-Catch-All: /r/:uid Share-Links müssen die index.html liefern
(Client-Router rendert die read-only-Ansicht), nicht rohes JSON/404.
Unbekannte /api/*-Pfade bleiben 404."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def spa_app(monkeypatch, tmp_path):
    """App mit gebautem (Fake-)SPA: tmpdir enthält index.html + asset."""
    (tmp_path / "index.html").write_text("<html>SPA-ROOT</html>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log('hi')")

    import app.main as main_mod

    monkeypatch.setattr(main_mod, "_STATIC_DIR", tmp_path)
    monkeypatch.setattr(main_mod, "_SPA_INDEX", tmp_path / "index.html")

    with TestClient(main_mod.app) as c:
        yield c


def test_share_link_liefert_html_statt_json(spa_app):
    """Der Produktionsbug: /r/:uid gab `{"detail":"Not Found"}` (JSON).
    Jetzt: index.html → Browser rendert die SPA-Ansicht."""
    res = spa_app.get("/r/ee35cbb8b2b5449bbf5a88c8f43b3f3b")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/html")
    assert "SPA-ROOT" in res.text


def test_unbekannte_pfade_liefern_index(spa_app):
    res = spa_app.get("/irgendwas/ganz/unbekannt")
    assert res.status_code == 200
    assert "SPA-ROOT" in res.text


def test_benchmark_route_liefert_index(spa_app):
    """/benchmark muss die SPA liefern, damit die BenchmarkPage rendert."""
    res = spa_app.get("/benchmark")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/html")
    assert "SPA-ROOT" in res.text


def test_static_assets_werden_serviert(spa_app):
    res = spa_app.get("/assets/app.js")
    assert res.status_code == 200
    assert res.text == "console.log('hi')"


def test_unbekannte_api_pfade_bleiben_404(spa_app):
    res = spa_app.get("/api/gibt-es-nicht")
    assert res.status_code == 404
    assert res.headers["content-type"].startswith("application/json")


def test_root_ohne_build_zeigt_hint(tmp_path, monkeypatch):
    """Ohne Build: / liefert den Dev-Hint, unbekannte Pfade 404."""
    import app.main as main_mod

    empty = tmp_path / "leer"
    empty.mkdir()
    monkeypatch.setattr(main_mod, "_STATIC_DIR", empty)
    monkeypatch.setattr(main_mod, "_SPA_INDEX", empty / "index.html")

    with TestClient(main_mod.app) as c:
        res = c.get("/")
        assert res.status_code == 200
        assert "text/html" in res.headers["content-type"]
        res2 = c.get("/r/irgendwas")
        assert res2.status_code == 404


# ---------------------------------------------------------------------------
# Change 237: Der SPA-Rückfall gilt nur für Client-Routen.
# ---------------------------------------------------------------------------


def test_versteckte_und_datei_pfade_bleiben_404(spa_app):
    """Befund 30.09.2026: Ein Scanner bekam für /.env, /.aws/credentials und
    39 weitere Pfade „200 OK" samt SPA-Hülle (kein Leck, aber ein
    irreführender Treffer — 1261 Byte text/html statt 404).
    """
    for pfad in ("/.env", "/.aws/credentials", "/.git/config",
                 "/wp-login.php", "/index.php", "/foo.txt"):
        res = spa_app.get(pfad)
        assert res.status_code == 404, f"{pfad} muss 404 liefern"
        assert not res.headers["content-type"].startswith("text/html"), pfad


def test_client_routen_liefern_weiterhin_die_spa(spa_app):
    """Der Rückfall für echte Routen bleibt unberührt (Gegenprobe zu oben)."""
    for pfad in ("/r/ee35cbb8b2b5449bbf5a88c8f43b3f3b", "/benchmark",
                 "/recording/123", "/irgendwas/ganz/unbekannt"):
        res = spa_app.get(pfad)
        assert res.status_code == 200, pfad
        assert "SPA-ROOT" in res.text, pfad


def test_spa_pfad_pruefung_einheitlich():
    """Die Regel selbst (ohne HTTP): Datei-Endung oder verstecktes Segment."""
    from app.main import _looks_like_file

    assert _looks_like_file("/.env") is True
    assert _looks_like_file("/.aws/credentials") is True
    assert _looks_like_file("/assets/index-abc.js") is True
    assert _looks_like_file("/r/abc") is False
    assert _looks_like_file("/benchmark") is False
    assert _looks_like_file("") is False
