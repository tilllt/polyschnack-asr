"""Tests für Change 201 — Schriftgröße füllt die Bildschirmbreite."""

import sys
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ass_export import fitwidth, textfit  # noqa: E402
from app.ass_export.ass_generator import build_lines, generate_ass  # noqa: E402
from app.ass_export.ass_generator import Word  # noqa: E402

TAG_RE = re.compile(r"\{[^}]*\}")


# --------------------------------------------------------------------------
# Reine Rechnung (ohne Schrift, ohne Umgebung)
# --------------------------------------------------------------------------
def test_font_size_trifft_die_breite():
    """Idealfall: die breiteste Zeile landet genau auf der verfügbaren Breite.

    base_size so gewählt, dass die ideale Größe im erlaubten Bereich
    (0,5×…3×) liegt — sonst greift die Untergrenze und der Überlauf wird
    gemeldet (das prüft der Test daneben).
    """
    groesse, ueberlauf = fitwidth.font_size_for(1833, [1000], base_size=100)
    assert ueberlauf == 0
    breite = 1000 * groesse / 100
    assert breite <= 1833 + 0.5, "darf nicht über den Rand"
    assert breite > 1833 - 20, f"Breite bleibt ungenutzt ({breite:.0f} px)"


def test_font_size_rundet_ab():
    """Abrunden, nicht runden: aufgerundet läuft die Zeile über den Rand.

    Gemessen: ideal 34,5 px → gerundet 35 → 1859 px bei 1833 px verfügbar.
    """
    groesse, ueberlauf = fitwidth.font_size_for(1833, [5312], base_size=48)
    assert groesse == 34
    assert 5312 * groesse / 100 <= 1833
    assert ueberlauf == 0


def test_font_size_bleibt_im_bereich_um_die_einstellung():
    """Sehr kurze Zeile → nicht ins Unermessliche; sehr lange → nicht unlesbar."""
    gross, _ = fitwidth.font_size_for(1833, [200], base_size=48)     # ideal 916
    assert gross == int(48 * fitwidth.MAX_FACTOR)
    klein, ueberlauf = fitwidth.font_size_for(1833, [20000], base_size=48)  # ideal 9
    assert klein == int(48 * fitwidth.MIN_FACTOR)
    assert ueberlauf == 1, "was selbst bei der Untergrenze zu breit ist, wird gemeldet"


def test_ausbalancieren_verteilt_nach_breite():
    """Acht Wörter, vier sehr lang: die Zeilen werden gleichmäßig(er) verteilt."""
    breiten = [200, 200, 200, 200, 1200, 1200, 1200, 1200]
    zeilen = fitwidth.balanced_split(breiten, max_words=4, available=1800)
    assert sum(len(z) for z in zeilen) == 8
    assert all(len(z) <= 4 for z in zeilen), "Obergrenze Wörter je Zeile verletzt"
    summen = [sum(breiten[i] for i in z) for z in zeilen]
    assert all(s <= 1800 for s in summen), f"Zeile zu breit: {summen}"
    # Ausgeglichener als eine starre 4/4-Teilung (800 gegen 4800)
    assert max(summen) - min(summen) < 4800 - 800


def test_ausbalancieren_haelt_lange_woerter_zusammen():
    """Ein einzelnes zu breites Wort bekommt seine eigene Zeile — nicht zerschnitten."""
    zeilen = fitwidth.balanced_split([2500], max_words=4, available=1800)
    assert zeilen == [[0]]


# --------------------------------------------------------------------------
# Messung mit der echten Schrift (im Image immer vorhanden)
# --------------------------------------------------------------------------
needs_font = pytest.mark.skipif(
    textfit.text_width("M", font_name="Arial", bold=True) is None,
    reason="keine Schrift/Pillow im Prüflauf (im Image-Bau geprüft)",
)


@needs_font
def test_messung_nutzt_die_echte_schrift():
    schmal = textfit.text_width("iiii", font_name="Arial", bold=True)
    breit = textfit.text_width("MMMM", font_name="Arial", bold=True)
    assert schmal and breit and breit > schmal * 2, "Messung wirkt nicht plausibel"
    # Fett ist breiter als normal
    assert textfit.text_width("Hallo", font_name="Arial", bold=True) > \
        textfit.text_width("Hallo", font_name="Arial", bold=False)


@needs_font
def test_groesse_macht_die_zeile_breit_aber_nicht_zu_breit():
    """Am echten Beispiel: die berechnete Größe füllt die Breite, ohne zu überlaufen."""
    verfuegbar = textfit.available_width({"play_res_x": 1920, "outline_width": 3, "shadow": 1})
    breiten = [textfit.text_width(t, font_name="Arial", bold=True) for t in
               ["Wir haben damals die Untertitel fuer das", "Teamtreffen erstellt"]]
    groesse, ueberlauf = fitwidth.font_size_for(verfuegbar, breiten, base_size=56)
    gefuellt = max(breiten) * groesse / 100
    assert ueberlauf == 0
    assert gefuellt <= verfuegbar + 0.5, "Zeile läuft über den Rand"
    assert gefuellt > verfuegbar * 0.55, "Breite bleibt ungenutzt"


# --------------------------------------------------------------------------
# Im Generator
# --------------------------------------------------------------------------
def _aufnahme():
    woerter = []
    t = 0.0
    for wort in "Wir haben damals die Untertitel fuer das Teamtreffen erstellt".split():
        woerter.append({"word": wort, "start": t, "end": t + 0.4})
        t += 0.5
    segmente = [{"start": 0, "end": t + 1, "text": "x", "words": woerter}]
    return SimpleNamespace(original_name="Probe.mp4", segments=segmente)


def _events(ass: str):
    return [l.split(",", 9)[-1] for l in ass.splitlines() if l.startswith("Dialogue:")]


@needs_font
def test_balanced_vergroessert_die_schrift_gegenueber_off():
    aufnahme = _aufnahme()
    aus = generate_ass(aufnahme, "highlight", {"fit_mode": "off"})
    an = generate_ass(aufnahme, "highlight", {"fit_mode": "balanced"})
    assert an.params["font_size"] > aus.params["font_size"], "Modus wirkt nicht"
    # Der ASS-Stil trägt die wirksame Größe (eine Wahrheit, nicht zwei)
    stil = [l for l in an.content.splitlines() if l.startswith("Style:")][0]
    felder = stil.split(",")
    assert felder[0] == "Style: Default"
    assert int(felder[2]) == an.params["font_size"], f"Stil {felder[2]} != Antwort {an.params['font_size']}"


@needs_font
def test_off_bleibt_wie_bisher():
    """Ohne den Modus ändert sich nichts — bestehende Presets bleiben gleich."""
    aufnahme = _aufnahme()
    aus = generate_ass(aufnahme, "highlight", {"fit_mode": "off"})
    ohne = generate_ass(aufnahme, "highlight", {})
    assert aus.content == ohne.content, "off darf nichts verändern"


@needs_font
def test_zeilen_bleiben_in_der_breite():
    """Keine ausgelieferte Zeile überschreitet die verfügbare Breite (am Beispiel)."""
    aufnahme = _aufnahme()
    res = generate_ass(aufnahme, "highlight", {"fit_mode": "balanced"})
    verfuegbar = textfit.available_width({**res.params, "margin_l": 40, "margin_r": 40})
    groesse = res.params["font_size"]
    zu_breit = []
    for text in _events(res.content):
        rein = TAG_RE.sub("", text).replace("\\N", " ").strip()
        if not rein:
            continue
        breite = sum(textfit.text_width(w, font_name=res.params["font_name"],
                                       bold=res.params["bold"]) for w in rein.split())
        breite += textfit.text_width(" ", font_name=res.params["font_name"],
                                     bold=res.params["bold"]) * (len(rein.split()) - 1)
        breite = breite * groesse / 100
        if breite > verfuegbar + 1:
            zu_breit.append((round(breite), rein[:40]))
    assert not zu_breit, f"zu breite Zeilen: {zu_breit}"


@needs_font
def test_wortzahl_bleibt_obergrenze():
    """`words_per_line` begrenzt weiterhin, wie viele Wörter in eine Zeile dürfen."""
    woerter = [Word(index=i, text=f"Wort{i}", start_ms=i * 400, end_ms=i * 400 + 400,
                    segment_index=0, speaker="", real_timing=True) for i in range(12)]
    for maxw in (2, 3, 5):
        zeilen = build_lines(woerter, maxw, sentence_breaks=False,
                             measure=lambda t: float(textfit.text_width(
                                 t, font_name="Arial", bold=True) or 0))
        assert all(len(z.words) <= maxw for z in zeilen), f"Obergrenze {maxw} verletzt"


@needs_font
def test_ueberlauf_wird_gemeldet(monkeypatch):
    """Passt der Text auch bei der kleinsten Schrift nicht, wird gewarnt."""
    lang = Word(index=0, text="Donaudampfschifffahrtsgesellschaftskapitaen", start_ms=0,
                end_ms=400, segment_index=0, speaker="", real_timing=True)
    aufnahme = SimpleNamespace(original_name="Probe.mp4", segments=[{
        "start": 0, "end": 1, "text": "x",
        "words": [{"word": lang.text, "start": 0.0, "end": 0.4}],
    }])
    res = generate_ass(aufnahme, "highlight", {"fit_mode": "balanced", "font_size": 200})
    assert any(w.startswith("fit_overflow") for w in res.warnings), res.warnings


def test_ohne_messmoeglichkeit_bleibt_die_groesse(monkeypatch):
    """Fehlt die Messung, wird gewarnt und die eingestellte Größe benutzt."""
    monkeypatch.setattr(textfit, "available", lambda fehlt: (fehlt.append("pillow"), False)[1])
    aufnahme = _aufnahme()
    res = generate_ass(aufnahme, "highlight", {"fit_mode": "balanced", "font_size": 48})
    assert res.params["font_size"] == 48
    assert any(w.startswith("fit_unavailable") for w in res.warnings), res.warnings


def test_modus_ist_im_dialog_verfuegbar():
    """Der Regler muss dort stehen, wo er wirkt (used_params der Presets)."""
    from app.ass_export.presets import list_presets, used_params
    for preset in list_presets():
        assert "fit_mode" in used_params(preset), preset.name
