"""Change 202 — Schriftgröße je Zeile (Bildschirm füllen, Größe springt).

Geprüft wird an der **erzeugten Datei** und an der reinen Rechnung: jede Zeile
trägt ihre eigene Schriftgröße, die Zeile füllt die verfügbare Breite, die
Höhe wird eingehalten, und der Sicherheitsrand wirkt auch ohne
Schriftanpassung. Gegenprobe: `off` erzeugt unverändert keine Größen-Tags.
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ass_export import fitwidth, textfit  # noqa: E402
from app.ass_export import ass_generator  # noqa: E402
from app.ass_export.ass_generator import generate_ass  # noqa: E402
from tests.test_ass_export import ALL_PRESETS, recording, seg  # noqa: E402

#: Schriftgrößen-Tag im Event-Text (mit Ziffer, damit ``\fscx`` nicht zählt).
FS_RE = re.compile(r"\\fs(\d+)")
TAGS_RE = re.compile(r"\{[^}]*\}")


def recordings():
    """Eine Ein-Wort-Zeile, eine Vier-Wort-Zeile und eine sehr lange Zeile."""
    return {
        "kurz": recording([seg(0.0, 0.6, [("Ich", 0.0, 0.5)])], name="kurz.mp3"),
        "lang": recording([seg(0.0, 2.0, [("Donaudampfschifffahrt", 0.0, 0.4),
                                          ("ist", 0.4, 0.8),
                                          ("ein", 0.8, 1.2),
                                          ("Wortungeheuer", 1.2, 1.9)])],
                          name="lang.mp3"),
    }


def events(content: str):
    return [ln for ln in content.splitlines() if ln.startswith("Dialogue:")]


def event_size(line: str):
    m = FS_RE.search(line)
    return int(m.group(1)) if m else None


def event_text(line: str) -> str:
    """Text-Feld eines Events (10. Komma-getrenntes Feld) ohne Tags."""
    text = line.split(",", 9)[-1]
    return TAGS_RE.sub("", text).strip()


def style_line(content: str) -> str:
    return next(ln for ln in content.splitlines() if ln.startswith("Style:"))


def style_margins(content: str) -> tuple:
    """``(MarginL, MarginR, MarginV)`` aus der Stil-Zeile."""
    felder = style_line(content).split(",")
    return int(felder[-4]), int(felder[-3]), int(felder[-2])


# --------------------------------------------------------------------------
# Reine Rechnung
# --------------------------------------------------------------------------
def test_kurze_zeile_bekommt_groessere_schrift():
    """Ein Wort wird größer gesetzt als zehn Wörter — der Sprung ist das Ziel."""
    groessen, ueberlauf = fitwidth.per_line_sizes(
        available_w=1721, available_h=939,
        widths=[144.0, 1440.0], heights=[73.0, 73.0], base_size=48)
    assert ueberlauf == 0
    assert groessen[0] > groessen[1]
    assert groessen[1] == 119  # 1721 / 1440 × 100, abgerundet


def test_hoehengrenze_begrenzt_kurzes_wort():
    """Ohne Höhengrenze liefe ein einzelnes Wort oben aus dem Bild."""
    # Schmaler Text: die Breite würde 2868 px verlangen, die Höhe lässt 1286 zu.
    ohne, _ = fitwidth.per_line_sizes(1721, 0, [60.0], [73.0], base_size=48)
    mit, _ = fitwidth.per_line_sizes(1721, 939, [60.0], [73.0], base_size=48)
    assert mit[0] < ohne[0]
    # Die Tinte bleibt innerhalb der verfügbaren Höhe.
    assert 73.0 * mit[0] / 100 <= 939 + 0.5


def test_untergrenze_und_ueberlauf():
    """Auch das kleinste Maß bleibt lesbar; was dann noch zu breit ist, wird gemeldet."""
    groessen, ueberlauf = fitwidth.per_line_sizes(
        1721, 939, [20000.0], [73.0], base_size=48)
    assert groessen[0] == 24          # 0,5 × 48
    assert ueberlauf == 1, "zu breite Zeile muss gemeldet werden, nicht still laufen"

    # Grenzfall: knapp unter der Untergrenze passt es noch, knapp darüber nicht.
    passt, u1 = fitwidth.per_line_sizes(1721, 939, [7000.0], [73.0], base_size=48)
    zu_breit, u2 = fitwidth.per_line_sizes(1721, 939, [7200.0], [73.0], base_size=48)
    assert passt[0] == 24 and u1 == 0
    assert zu_breit[0] == 24 and u2 == 1


def test_breite_ist_die_grenze_wenn_die_hoehe_grosszuegig_ist():
    """Bei viel Platz nach oben entscheidet die Breite."""
    groessen, _ = fitwidth.per_line_sizes(1000, 100000, [500.0], [10.0], base_size=48)
    assert 500.0 * groessen[0] / 100 <= 1000 + 0.5
    assert 500.0 * groessen[0] / 100 > 1000 - 10


# --------------------------------------------------------------------------
# Sicherheitsrand
# --------------------------------------------------------------------------
def test_sicherheitsrand_setzt_die_stilraender():
    """``safe_margin_pct`` wirkt auch ohne Schriftanpassung (``off``)."""
    rec = recordings()["kurz"]
    ass = generate_ass(rec, "classic", {"fit_mode": "off",
                                        "safe_margin_pct": 10}).content
    assert style_margins(ass)[:2] == (192, 192), "10 % von 1920 px"

    alt = generate_ass(rec, "classic", {"fit_mode": "off",
                                        "safe_margin_pct": 0}).content
    assert style_margins(alt)[:2] == (40, 40), "0 % = Stand vor Change 202"


def test_sicherheitsrand_verkleinert_die_schrift():
    """Der Rand muss auch in der Rechnung ankommen, nicht nur im Kopf."""
    rec = recordings()["lang"]
    weit = generate_ass(rec, "classic", {"fit_mode": "per_line",
                                         "safe_margin_pct": 0})
    eng = generate_ass(rec, "classic", {"fit_mode": "per_line",
                                        "safe_margin_pct": 15})
    assert max(event_size(e) for e in events(eng.content)) < \
        max(event_size(e) for e in events(weit.content))


# --------------------------------------------------------------------------
# Erzeugte Datei
# --------------------------------------------------------------------------
@pytest.mark.parametrize("preset", ALL_PRESETS)
def test_jedes_event_traegt_genau_eine_schriftgroesse(preset):
    """Ein Event ohne Größe fiele still auf den Stil zurück — das wäre ein Fehler."""
    ass = generate_ass(recordings()["lang"], preset,
                       {"fit_mode": "per_line", "words_per_line": 2}).content
    assert events(ass), "keine Events erzeugt"
    for line in events(ass):
        assert len(FS_RE.findall(line)) == 1, f"nicht genau ein \\fs: {line[:90]}"


@pytest.mark.parametrize("preset", ALL_PRESETS)
def test_off_schreibt_keine_schriftgroesse(preset):
    """Gegenprobe: ohne Schriftanpassung bleibt alles wie vorher."""
    ass = generate_ass(recordings()["lang"], preset, {"fit_mode": "off"}).content
    assert not FS_RE.search(ass)


def test_groesse_springt_mit_der_zeile():
    """Bei einem Wort je Zeile unterscheiden sich die Größen deutlich."""
    ass = generate_ass(recordings()["lang"], "classic",
                       {"fit_mode": "per_line", "words_per_line": 1}).content
    groessen = [event_size(e) for e in events(ass)]
    assert len(groessen) >= 4
    assert max(groessen) > min(groessen) * 3, f"kein Sprung: {groessen}"
    texte = [event_text(e) for e in events(ass)]
    assert "Donaudampfschifffahrt" in " ".join(texte)


def test_zeilen_bleiben_bei_der_eingestellten_wortzahl():
    """``per_line`` balanciert NICHT nach Breite — die Wortzahl gibt den Takt."""
    rec = recordings()["lang"]
    ass = generate_ass(rec, "classic", {"fit_mode": "per_line",
                                        "words_per_line": 2}).content
    assert [len(event_text(e).split()) for e in events(ass)] == [2, 2]


def test_balanced_bleibt_eine_groesse():
    """Change 201 muss unangetastet bleiben: dort gilt EINE Größe."""
    ass = generate_ass(recordings()["lang"], "classic",
                       {"fit_mode": "balanced", "words_per_line": 2}).content
    assert not FS_RE.search(ass), "balanced schreibt die Größe in den Stil"
    groesse = int(style_line(ass).split(",")[2])
    assert groesse > 48, "balanced soll die Größe anheben"


def test_vorlage_ohne_platzhalter_wird_gemeldet(monkeypatch):
    """Fehlt ``fs_tag`` in einer Vorlage, wird das gemeldet statt verschluckt."""
    import app.ass_export.ass_generator as gen

    monkeypatch.setattr(gen, "render_preset_file",
                        lambda *a, **k: "Dialogue: 0,0:00:00.00,0:00:01.00,"
                                        "Default,,0,0,0,,ohne Tag")
    res = generate_ass(recordings()["kurz"], "classic", {"fit_mode": "per_line"})
    assert "fit_tag_missing:classic" in res.warnings


# --------------------------------------------------------------------------
# Mit der echten Schrift
# --------------------------------------------------------------------------
needs_font = pytest.mark.skipif(
    textfit.text_width("M", font_name="Arial", bold=True) is None,
    reason="keine Schrift/Pillow im Prüflauf (im Image-Bau geprüft)",
)


@needs_font
def test_zeile_fuellt_die_breite_und_laeuft_nicht_ueber():
    """Am echten Beispiel: die Tinte füllt die Breite weitgehend aus."""
    rec = recordings()["lang"]
    res = generate_ass(rec, "classic", {"fit_mode": "per_line",
                                        "words_per_line": 1,
                                        "safe_margin_pct": 5})
    verfuegbar = ass_generator._available_width(res.params)
    for line in events(res.content):
        text = event_text(line)
        groesse = event_size(line)
        breite = textfit.text_width(text, font_name="Arial", bold=True) * groesse / 100
        assert breite <= verfuegbar + 0.5, f"läuft über den Rand: {text}"
        if len(text) > 3:  # Einzelbuchstaben sind durch die Höhe begrenzt
            assert breite > verfuegbar * 0.8, f"Breite bleibt ungenutzt: {text}"


@needs_font
def test_tinte_und_zeilenbox_bleiben_innerhalb_der_hoehe():
    """Die gemessene Tinte **und** die reservierte Zeilenbox müssen passen.

    Die Zeilenbox (Auf- + Abstieg ≈ 1,14 em) ist die wirksame Grenze: libass
    setzt die Box mit ihrer Unterkante auf ``margin_v``. Wer nur die Tinte
    begrenzt, bekommt oben abgeschnittene Buchstaben (am Renderer belegt).
    """
    rec = recordings()["lang"]
    res = generate_ass(rec, "classic", {"fit_mode": "per_line",
                                        "safe_margin_pct": 5})
    frei = ass_generator._available_height(res.params)
    box = textfit.line_box_height(font_name="Arial", bold=True)
    assert box and box > textfit.text_height("WEG", font_name="Arial", bold=True)
    for line in events(res.content):
        text = event_text(line)
        groesse = event_size(line)
        tinte = textfit.text_height(text, font_name="Arial", bold=True) * groesse / 100
        assert tinte <= frei + 0.5, f"Tinte zu hoch: {text}"
        assert box * groesse / 100 <= frei + 0.5, f"Zeilenbox zu hoch: {text}"


@needs_font
def test_messung_der_hoehe_haengt_am_text():
    """Die Höhe ist keine Konstante — genau deshalb wird sie gemessen."""
    kurz = textfit.text_height("WEG", font_name="Arial", bold=True)
    hoch = textfit.text_height("ÄÖÜgjpqy", font_name="Arial", bold=True)
    assert kurz and hoch and hoch > kurz * 1.3


# --------------------------------------------------------------------------
# Am echten Renderer (libass) — Tinte im Bild, eine Zeile, kein Umbruch
# --------------------------------------------------------------------------
needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None,
                                  reason="ffmpeg (mit libass) fehlt")


@needs_font
@needs_ffmpeg
def test_gerenderte_zeile_bleibt_eine_zeile_im_sicherheitsrand(tmp_path):
    """Ein Umbruch wäre das Schlimmste: zwei Zeilen statt „füllt den Bildschirm".

    Geprüft wird am gerenderten Bild (nicht an der Rechnung): die Tinte liegt
    innerhalb des Sicherheitsrands und bildet **einen** zusammenhängenden
    Block — eine zweite Zeile würde einen zweiten Block erzeugen.
    """
    np = pytest.importorskip("numpy")
    from tests.test_ass_export_render import render

    rec = recordings()["lang"]
    params = {"fit_mode": "per_line", "words_per_line": 1, "safe_margin_pct": 10}
    res = generate_ass(rec, "classic", params)
    frames, stderr = render(res.content, tmp_path, duration=2.0)
    assert "Parse error" not in stderr

    # Bild ist 640×360, PlayRes 1920×1080 → Faktor 1/3.
    skala = 360 / float(res.params["play_res_y"])
    rand = int(round(640 * params["safe_margin_pct"] / 100))
    hoehe_max = ass_generator._available_height(res.params) * skala

    geprueft = 0
    for frame in frames:
        maske = frame.sum(axis=2) > 60
        if not maske.any():
            continue
        geprueft += 1
        zeilen = np.where(maske.any(axis=1))[0]
        spalten = np.where(maske.any(axis=0))[0]
        # Eine Zeile: die Tinte passt in die Höhe, die die Rechnung zulässt.
        # (Ein Umbruch ergäbe zwei Zeilenboxen übereinander und damit mehr als
        # das Doppelte — genau der Fehler, den die Höhengrenze verhindert.)
        assert zeilen[-1] - zeilen[0] + 1 <= hoehe_max + 3, \
            "Tinte höher als eine Zeilenbox — Zeile umgebrochen?"
        assert spalten[0] >= rand - 6, f"links im Sicherheitsrand: {spalten[0]}"
        assert spalten[-1] <= 640 - rand + 6, f"rechts darüber hinaus: {spalten[-1]}"
    assert geprueft > 0, "kein Bild mit Tinte gefunden"
