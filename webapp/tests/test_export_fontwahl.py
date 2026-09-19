"""Change 203 — die Schriftart ist ein Auswahlfeld, kein Textfeld.

Geprüft wird die abgeleitete Liste (reine Rechnung, ohne fontconfig), das
Auslesen der Schriften dieses Rechners, die offene Annahme fremder Namen und
die Wirkung im erzeugten ASS. Gegenprobe: ein Name, den der Renderdienst auf
eine andere Familie abbildet, darf nicht angeboten werden.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ass_export import presets, textfit  # noqa: E402
from app.ass_export.ass_generator import generate_ass  # noqa: E402
from app.ass_export.presets import (  # noqa: E402
    ParamError,
    parameter_specs,
    validate_overrides,
)
from app.ass_export.presets import font_choices  # noqa: E402
from tests.test_ass_export import recording, seg  # noqa: E402

#: Was in beiden Images liegt — Webapp wie Renderdienst (Stand: Änderung).
BEIDE = ("Liberation Mono", "Liberation Sans", "Liberation Serif")
#: Zusätzlich im Webapp-Image (fonts-liberation 1.07.4), NICHT im Render-Image:
#: dort zeigt ``fc-match "Liberation Sans Narrow"`` auf ``Liberation Sans``.
NUR_WEBAPP = ("Liberation Sans Narrow",)
ERWARTET = ["Arial", "Liberation Sans", "Times New Roman", "Liberation Serif",
            "Courier New", "Liberation Mono"]


# --------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------
def test_schema_liefert_ein_auswahlfeld():
    spec = parameter_specs()["font_name"]
    assert spec["type"] == "enum", "nur ein enum rendert die GUI als <select>"
    assert spec["open"] is True, "die API soll weiterhin jeden Namen annehmen"
    assert spec["max_len"] == 64
    assert spec["values"], "leere Liste würde ein leeres Dropdown ergeben"


def test_vorgabe_steht_immer_in_der_auswahl():
    """Ein <select> ohne den aktuellen Wert zeigt stumm den ersten Eintrag."""
    for eigene, fremde in (((), None), (BEIDE + NUR_WEBAPP, BEIDE),
                           (BEIDE, ()), (("Kurios",), ("Anderes",))):
        werte = font_choices(eigene, fremde)
        assert presets.PARAM_SPECS["font_name"]["default"] in werte, (eigene, fremde)


# --------------------------------------------------------------------------
# Ableitung der Auswahl (reine Rechnung)
# --------------------------------------------------------------------------
def test_standardnamen_kommen_als_paar_vor_ihrer_ersatzfamilie():
    assert font_choices(BEIDE, BEIDE) == ERWARTET


def test_schrift_die_ein_host_anders_aufloest_faellt_heraus():
    """Kern des Changes: gemessen wird in der Webapp, eingebrannt im Renderer."""
    ohne_filter = font_choices(BEIDE + NUR_WEBAPP)
    assert "Liberation Sans Narrow" in ohne_filter, "Gegenprobe: allein wäre sie drin"
    assert "Liberation Sans Narrow" not in font_choices(BEIDE + NUR_WEBAPP, BEIDE)


def test_unbekannte_renderliste_laesst_die_eigene_liste_gelten():
    """Ohne Renderdienst wird nichts eingebrannt — dann zählt die Messung."""
    assert font_choices(BEIDE + NUR_WEBAPP, None) == \
        ["Arial", "Liberation Sans", "Times New Roman", "Liberation Serif",
         "Courier New", "Liberation Mono", "Liberation Sans Narrow"]


def test_weitere_familien_kommen_alphabetisch_dahinter():
    """Zusatzfamilien nur, wenn BEIDE Seiten sie haben — sonst hinten anstellen."""
    beide = ("Liberation Sans", "DejaVu Sans", "Zierschrift")
    assert font_choices(beide, beide) == \
        ["Arial", "Liberation Sans", "DejaVu Sans", "Zierschrift"]
    # DejaVu hat nur die messende Instanz → nicht anbieten.
    assert font_choices(("Liberation Sans", "DejaVu Sans"), ("Liberation Sans",)) == \
        ["Arial", "Liberation Sans"]
    # Kleinschreibung sortiert nach den Standardpaaren, nicht davor.
    assert font_choices(("ainfont", "Liberation Sans"), ("ainfont", "Liberation Sans")) == \
        ["Arial", "Liberation Sans", "ainfont"]


def test_keine_doppelten_werte():
    werte = font_choices(("Liberation Sans", "Liberation Sans", "Arial"), ("Liberation Sans"))
    assert len(werte) == len(set(werte))
    assert werte.count("Arial") == 1


# --------------------------------------------------------------------------
# Auslesen der Schriften dieses Rechners
# --------------------------------------------------------------------------
def test_fc_list_wird_mit_ausdruecklichem_format_aufgerufen(monkeypatch):
    """``fc-list : family`` liefert je nach Version die GANZE Zeile (Pfad,
    Schnitt) — davon sind wir hier schon einmal erwischt worden. Der Aufruf
    muss deshalb das Ausgabeformat selbst setzen."""
    gesehen = {}

    def merke(*args, **kwargs):
        gesehen["args"] = args[0] if args else []
        return type("R", (), {"stdout": "Liberation Sans\n"})()

    monkeypatch.setattr(textfit.shutil, "which", lambda name: "/usr/bin/fc-list")
    monkeypatch.setattr(textfit.subprocess, "run", merke)
    textfit.font_families.cache_clear()
    try:
        textfit.font_families()
    finally:
        textfit.font_families.cache_clear()
    assert "-f" in gesehen["args"], gesehen["args"]
    assert "%{family}" in " ".join(gesehen["args"]), gesehen["args"]


def test_familien_werden_aus_der_fc_list_ausgabe_gelesen(monkeypatch):
    ausgabe = (
        "  Liberation Mono  \n"
        "IPAGothic,IPAゴシック\n"
        "Liberation Sans\n"
        "\n"
        "Libération Serif\n"
    )
    monkeypatch.setattr(textfit.shutil, "which", lambda name: "/usr/bin/fc-list")
    monkeypatch.setattr(textfit.subprocess, "run", lambda *a, **k: type(
        "R", (), {"stdout": ausgabe})())
    textfit.font_families.cache_clear()
    try:
        gefunden = textfit.font_families()
    finally:
        textfit.font_families.cache_clear()
    assert sorted(gefunden) == list(gefunden), "Reihenfolge muss stabil sortiert sein"
    assert set(gefunden) == {"IPAGothic", "IPAゴシック", "Liberation Mono",
                             "Liberation Sans", "Libération Serif"}
    assert len(gefunden) == 5, "Leerzeilen und doppelte Namen dürfen nicht durchkommen"


def test_einzelner_name_als_zeichenkette_zerstoert_die_auswahl_nicht():
    """``"Liberation Sans"`` ist als Sequence die Menge seiner Buchstaben."""
    assert font_choices("Liberation Sans", "Liberation Sans") == \
        ["Arial", "Liberation Sans"]


def test_ohne_fc_list_bleibt_die_liste_leer(monkeypatch):
    """Dann entscheidet der Aufrufer (hier: nur die Vorgabe wird angeboten)."""
    monkeypatch.setattr(textfit.shutil, "which", lambda name: None)
    textfit.font_families.cache_clear()
    try:
        assert textfit.font_families() == ()
        assert font_choices(textfit.font_families()) == ["Arial"]
    finally:
        textfit.font_families.cache_clear()


def test_fc_list_fehler_wird_nicht_verschluckt_sondern_gemeldet(monkeypatch):
    def kaputt(*a, **k):
        raise OSError("fc-list nicht startbar")

    monkeypatch.setattr(textfit.shutil, "which", lambda name: "/usr/bin/fc-list")
    monkeypatch.setattr(textfit.subprocess, "run", kaputt)
    textfit.font_families.cache_clear()
    try:
        assert textfit.font_families() == ()
    finally:
        textfit.font_families.cache_clear()


# --------------------------------------------------------------------------
# Offene Auswahl: die Liste hilft, sie sperrt nicht
# --------------------------------------------------------------------------
def test_fremder_schriftenname_bleibt_erlaubt():
    assert validate_overrides({"font_name": "DejaVu Sans"})["font_name"] == "DejaVu Sans"
    assert validate_overrides({"font_name": "Comic Sans MS"})["font_name"] == "Comic Sans MS"


def test_leerer_und_zu_langer_name_bleiben_fehler():
    with pytest.raises(ParamError):
        validate_overrides({"font_name": "   "})
    with pytest.raises(ParamError):
        validate_overrides({"font_name": "X" * 65})


def test_komma_wird_ersetzt_statt_die_stilzeile_zu_zerreissen():
    assert validate_overrides({"font_name": "Liberation Sans, Narrow"})["font_name"] == \
        "Liberation Sans  Narrow"


def test_andere_auswahlen_bleiben_streng():
    """Die Offenheit gilt nur für die Schrift, nicht für Modus-Listen."""
    with pytest.raises(ParamError):
        validate_overrides({"position": "irgendwo"})
    with pytest.raises(ParamError):
        validate_overrides({"fit_mode": "per_word"})


# --------------------------------------------------------------------------
# Wirkung in der erzeugten Datei
# --------------------------------------------------------------------------
def test_gewaehlte_schrift_landet_im_stil():
    rec = recording([seg(0.0, 1.0, [("Hallo", 0.0, 0.9)])], name="schrift.mp3")
    res = generate_ass(rec, "classic", {"font_name": "Liberation Serif"})
    stil = next(z for z in res.content.splitlines() if z.startswith("Style:"))
    assert "Liberation Serif" in stil
    assert res.params["font_name"] == "Liberation Serif"


def test_vorgabe_bleibt_arial():
    """Bestandsverhalten: die ASS-Datei nennt den Standardnamen, nicht den Ersatz."""
    rec = recording([seg(0.0, 1.0, [("Hallo", 0.0, 0.9)])], name="schrift2.mp3")
    res = generate_ass(rec, "classic", {})
    assert res.params["font_name"] == "Arial"


# --------------------------------------------------------------------------
# Gegenprobe gegen die Wirklichkeit (nur wo Schriften vorhanden sind)
# --------------------------------------------------------------------------
needs_font = pytest.mark.skipif(
    not textfit.font_families(),
    reason="kein fontconfig/fc-list im Prüflauf",
)


@needs_font
def test_angebotene_schriften_sind_hier_aufloesbar():
    """Jeder angebotene Name muss sich hier auch wirklich auflösen lassen."""
    werte = font_choices(textfit.font_families())
    for name in werte:
        assert textfit.font_path(name, True) is not None, name


@needs_font
def test_gefundene_familien_sind_keine_dateipfade():
    """Falsches fc-list-Format hat hier schon zugeschlagen (Pfad+Schnitt)."""
    for name in textfit.font_families():
        assert "/" not in name and ":style=" not in name, name
