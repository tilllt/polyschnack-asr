"""Invariante: im Backend werden Zeitstempel tz-aware gebaut.

Warum dieser Test: Alle Datetime-Spalten werden als
``datetime.now(timezone.utc)`` geschrieben. Ein naiver Wert bindet SQLModel
seit 0.0.40 nicht mehr — der Query stirbt zur Laufzeit mit
``ValueError: Datetime values must have timezone information``. Getroffen hat es
``_purge_expired()`` in ``db.py``: damit fiel ``init_db()`` aus, jeder
TestClient-Start scheiterte, und die ganze Suite war rot, obwohl sie lokal
(alte sqlmodel-Version 0.0.39) gruen war. Der Test haelt das Muster statisch
fest, damit dieselbe Falle nicht wieder ueber eine Bibliotheks-Aktualisierung
zuschlaegt.
"""

from __future__ import annotations

import re
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
APP = WURZEL / "app"
TESTS = WURZEL / "tests"

#: Muster, die einen Zeitstempel OHNE Zeitzone erzeugen.
VERBOTEN = (
    (re.compile(r"\butcnow\s*\("), "datetime.utcnow() (naiv, ausserdem deprecated)"),
    (re.compile(r"\bdatetime\.now\s*\(\s*\)"), "datetime.now() ohne timezone"),
    (re.compile(r"\bdt\.datetime\.now\s*\(\s*\)"), "dt.datetime.now() ohne timezone"),
    (re.compile(r"\bdate\.today\s*\(\s*\)"), "date.today() (ohne Zeitzone)"),
)


#: Datetime-Literal mit Datum, aber ohne tzinfo: datetime(2026, 8, 1, 10, 0)
LITERAL = re.compile(r"\b(?:dt\.)?datetime\s*\(([^()]*)\)")
LITERAL_DATUM = re.compile(r"\d{4}\s*,\s*\d{1,2}\s*,\s*\d{1,2}")


def _pruefe(wurzeln) -> list[str]:
    treffer: list[str] = []
    selbst = Path(__file__).resolve()
    for pfad in sorted({p for wurzel in wurzeln for p in wurzel.rglob("*.py")}):
        if pfad.resolve() == selbst:
            continue          # diese Datei enthaelt die Muster selbst als Strings
        for nummer, zeile in enumerate(pfad.read_text(encoding="utf-8").splitlines(), 1):
            if "tz-invariant-ok" in zeile:
                continue      # bewusste Ausnahme (z. B. Eingabe fuer iso_utc-Test)
            code = zeile.split("#", 1)[0]          # Kommentare ignorieren
            for muster, name in VERBOTEN:
                if muster.search(code):
                    treffer.append(
                        f"{pfad.relative_to(WURZEL)}:{nummer}: {name} → {zeile.strip()}"
                    )
            for args in LITERAL.findall(code):
                if LITERAL_DATUM.search(args) and "tzinfo" not in args:
                    treffer.append(
                        f"{pfad.relative_to(WURZEL)}:{nummer}: Datetime-Literal ohne "
                        f"tzinfo → {zeile.strip()}"
                    )
    return treffer


def test_keine_naiven_zeitstempel_im_backend():
    treffer = _pruefe([APP])
    assert not treffer, (
        "Naive Zeitstempel im Backend gefunden — tz-aware bauen "
        "(datetime.now(timezone.utc)):\n" + "\n".join(treffer)
    )


def test_keine_naiven_zeitstempel_in_den_tests():
    """Fixtures schreiben echte Zeilen — naive Literale kippen erst beim INSERT
    (``tests/test_share_link.py``: 7 Fehler unter sqlmodel 0.0.47)."""
    treffer = _pruefe([TESTS])
    assert not treffer, (
        "Naive Zeitstempel in den Tests gefunden — tz-aware bauen "
        "(tzinfo=timezone.utc), sonst faellt der Test erst beim INSERT:\n"
        + "\n".join(treffer)
    )
