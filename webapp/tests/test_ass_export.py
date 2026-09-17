"""Change 193 — ASS-Caption-Generator: Presets, Parameter, Zeit-Invarianten.

Diese Tests prüfen die *erzeugten Dateien* (nicht die Implementierung):
Event-Struktur, Zeit-Monotonie, Überlappungsfreiheit, Texterhalt
(Klammern dürfen keine Wörter verschlucken — libass-Beleg im
``test_ass_export_render.py``) und die Karaoke-Synchronität.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ass_export import (  # noqa: E402
    NoWordTimestamps,
    ParamError,
    generate_ass,
    list_presets,
    load_preset,
)
from app.ass_export.template_engine import ass_escape, cs, tc  # noqa: E402

ALL_PRESETS = ["classic", "karaoke", "highlight", "kinetic", "modern"]
WORD_TEMPLATES = ["highlight", "kinetic", "modern"]

EVENT_RE = re.compile(
    r"^Dialogue: (?P<layer>\d+),"
    r"(?P<start>\d+:\d{2}:\d{2}\.\d{2}),"
    r"(?P<end>\d+:\d{2}:\d{2}\.\d{2}),"
    r"(?P<style>[^,]*),(?P<name>[^,]*),"
    r"(?P<margin_l>\d+),(?P<margin_r>\d+),(?P<margin_v>\d+),"
    r"(?P<effect>[^,]*),(?P<text>.*)$"
)
TAG_RE = re.compile(r"\{[^}]*\}")


def recording(segments, name="Testaufnahme.mp3"):
    return SimpleNamespace(original_name=name, segments=segments)


def seg(start, end, words, speaker=None, text=None):
    data = {
        "start": start,
        "end": end,
        "text": text if text is not None else " ".join(w for w, _, _ in words),
        "words": [{"start": s, "end": e, "text": w} for w, s, e in words],
    }
    if speaker:
        data["speaker"] = speaker
    return data


def parse_events(content: str):
    """Alle Dialogue-Zeilen als Dicts."""
    events = []
    for line in content.splitlines():
        if not line.startswith("Dialogue:"):
            continue
        m = EVENT_RE.match(line)
        assert m, f"Dialogue-Zeile passt nicht ins ASS-Format: {line!r}"
        ev = m.groupdict()
        ev["start_ms"] = tc_to_ms(ev["start"])
        ev["end_ms"] = tc_to_ms(ev["end"])
        events.append(ev)
    return events


def tc_to_ms(value: str) -> int:
    h, m, rest = value.split(":")
    s, cs_ = rest.split(".")
    return ((int(h) * 60 + int(m)) * 60 + int(s)) * 1000 + int(cs_) * 10


def visible_text(text: str) -> str:
    """Event-Text ohne ASS-Override-Blöcke und ohne \\k-Tags."""
    out = TAG_RE.sub("", text)
    out = re.sub(r"\\[kK][fo]?\d+", "", out)
    return out


def karaoke_durations_ms(text: str):
    return [int(v) for v in re.findall(r"\\kf(\d+)", text)]


@pytest.fixture()
def sample():
    return recording([
        seg(0.0, 2.0, [("Hallo", 0.0, 0.4), ("Welt", 0.45, 0.8),
                       ("das", 0.9, 1.1), ("ist", 1.15, 1.35),
                       ("ein", 1.4, 1.55), ("Test.", 1.6, 1.95)],
            speaker="Sprecher 1"),
        seg(2.5, 4.0, [("Zweite", 2.5, 2.8), ("Zeile", 2.85, 3.2),
                       ("{mit}", 3.3, 3.5), ("Klammern.", 3.55, 3.9)],
            speaker="Sprecher 1"),
    ])


# ---------------------------------------------------------------------------
# Preset-Katalog
# ---------------------------------------------------------------------------


def test_catalog_has_five_standard_presets():
    names = [p.name for p in list_presets()]
    for expected in ALL_PRESETS:
        assert expected in names, f"Preset {expected} fehlt (Katalog: {names})"


@pytest.mark.parametrize("name", ALL_PRESETS)
def test_preset_has_description_defaults_and_template(name):
    preset = load_preset(name)
    assert preset.description.strip(), "Beschreibung fehlt"
    assert preset.title.strip()
    defaults = preset.effective_defaults()
    assert defaults["words_per_line"] >= 1
    assert defaults["play_res_x"] > 0 and defaults["play_res_y"] > 0
    assert (Path(preset.template_file).name == preset.template_file)


def test_unknown_preset_raises():
    from app.ass_export import PresetNotFound

    with pytest.raises(PresetNotFound):
        load_preset("gibts-nicht")
    with pytest.raises(PresetNotFound):
        load_preset("../etc/passwd")


# ---------------------------------------------------------------------------
# Parameter
# ---------------------------------------------------------------------------


def test_parameter_override_changes_style_and_layout(sample):
    result = generate_ass(sample, "classic", {
        "font_size": 72, "text_color": "#00FF00", "position": "top",
        "play_res_x": 1080, "play_res_y": 1920,
    })
    style_line = [l for l in result.content.splitlines() if l.startswith("Style:")][0]
    assert ",72," in style_line
    # Grün → BGR "00FF00" landet als &H0000FF00 (AA=00, B=00, G=FF, R=00).
    assert "&H0000FF00" in style_line
    assert ",8," in style_line  # alignment top-center
    assert "PlayResX: 1080" in result.content
    assert "PlayResY: 1920" in result.content


@pytest.mark.parametrize("bad,value", [
    ("font_size", 1000),
    ("font_size", "zwölf"),
    ("text_color", "#ZZZ"),
    ("position", "diagonal"),
    ("words_per_line", 0),
    ("tail_ms", -5),
    ("unbekannt", 1),
])
def test_invalid_parameters_are_rejected(sample, bad, value):
    with pytest.raises(ParamError):
        generate_ass(sample, "classic", {bad: value})


def test_bool_parameters_accept_strings():
    preset = load_preset("modern")
    params = preset.resolve({"hide_upcoming": "false", "bold": "true"})
    assert params["hide_upcoming"] is False
    assert params["bold"] is True


def test_font_name_commas_are_removed():
    preset = load_preset("classic")
    params = preset.resolve({"font_name": "Arial, Black"})
    assert "," not in params["font_name"]


# ---------------------------------------------------------------------------
# Struktur + Zeiten
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ALL_PRESETS)
def test_document_is_complete_and_events_are_wellformed(sample, name):
    result = generate_ass(sample, name)
    content = result.content
    assert "[Script Info]" in content
    assert "[V4+ Styles]" in content
    assert "[Events]" in content
    assert content.count("\nStyle: ") == 1
    events = parse_events(content)
    assert events, "keine Events erzeugt"
    for ev in events:
        assert ev["end_ms"] > ev["start_ms"], f"Event ohne Dauer: {ev}"
        assert ev["style"] == "Default"
        assert "\n" not in ev["text"]


@pytest.mark.parametrize("name", ALL_PRESETS)
def test_events_never_overlap_and_start_monotone(sample, name):
    events = sorted(parse_events(generate_ass(sample, name).content),
                    key=lambda e: e["start_ms"])
    assert events[0]["start_ms"] >= 0
    for prev, cur in zip(events, events[1:]):
        assert cur["start_ms"] >= prev["start_ms"]
        assert cur["start_ms"] >= prev["end_ms"], (
            f"{name}: Events überlappen: {prev['start']}-{prev['end']} / "
            f"{cur['start']}-{cur['end']}"
        )


@pytest.mark.parametrize("name", ["classic", "karaoke"])
def test_line_presets_emit_one_event_per_line(sample, name):
    result = generate_ass(sample, name)
    assert len(parse_events(result.content)) == result.lines


@pytest.mark.parametrize("name", WORD_TEMPLATES)
def test_word_presets_emit_one_event_per_word(sample, name):
    result = generate_ass(sample, name)
    assert len(parse_events(result.content)) == result.words
    assert result.steps == result.words


def test_curly_braces_do_not_swallow_words(sample):
    """libass verschluckt {...}-Blöcke — der Text muss trotzdem vollständig sein."""
    for name in ALL_PRESETS:
        result = generate_ass(sample, name)
        texts = [visible_text(e["text"]) for e in parse_events(result.content)]
        joined = " ".join(texts)
        for word in ["Hallo", "Welt", "Zeile", "(mit)", "Klammern.", "Test."]:
            if name in WORD_TEMPLATES:
                continue  # Wort-Presets malen je Event nur die Zeile
            assert word in joined, f"{name}: {word!r} fehlt in {joined!r}"
        # Die Klammer-Wörter stehen als runde Klammern (Ersatz statt Verlust).
        assert "{" not in " ".join(visible_text(e["text"]) for e in parse_events(result.content))


def test_timings_follow_the_words(sample):
    """Zeiten kommen aus den Wort-Timings, nicht aus Segment- oder Schätzzeiten."""
    events = sorted(parse_events(generate_ass(sample, "highlight").content),
                    key=lambda e: e["start_ms"])
    assert events[0]["start_ms"] == 0
    assert events[0]["end_ms"] == 450       # Ende = Start des nächsten Wortes
    assert events[-1]["end_ms"] == 4200     # letztes Wort 3.90 s + 300 ms Nachlauf
    assert events[5]["start_ms"] == 1600    # "Test." beginnt bei 1.60 s


def test_karaoke_durations_match_the_words(sample):
    """\\kf-Dauern: lückenlos in Wortreihenfolge, Summe ≈ Event-Dauer.

    Ohne Nachlauf (tail_ms=0) deckt die Karaoke den ganzen Event ab (bis auf
    die Zentisekunden-Rundung) — sonst läuft der Farbbalken dem Wort davon.
    """
    result = generate_ass(sample, "karaoke", {"tail_ms": 0})
    events = parse_events(result.content)
    assert events
    for ev in events:
        durations = karaoke_durations_ms(ev["text"])
        assert durations, f"keine \\kf-Tags: {ev['text']!r}"
        total_ms = sum(d * 10 for d in durations)
        duration = ev["end_ms"] - ev["start_ms"]
        assert abs(total_ms - duration) <= 10 * len(durations), (
            f"Karaoke läuft nicht synchron: {total_ms} ms vs {duration} ms"
        )
        assert all(d >= 1 for d in durations)


def test_karaoke_durations_are_centiseconds_not_milliseconds(sample):
    """Faktor-10-Falle: 450 ms Wortabstand muss \\kf45 ergeben, nicht \\kf450."""
    events = parse_events(generate_ass(sample, "karaoke").content)
    first = karaoke_durations_ms(events[0]["text"])
    assert first[0] == 45  # 0.00 s → 0.45 s
    assert max(first) < 200  # nichts über 2 s pro Silbe


def test_lead_and_tail_extend_the_line_but_not_the_words():
    data = recording([seg(10.0, 12.0, [("Hallo", 10.0, 10.5),
                                       ("Welt", 10.6, 11.0)])])
    plain = parse_events(generate_ass(
        data, "classic", {"lead_ms": 0, "tail_ms": 0}).content)[0]
    extended = parse_events(generate_ass(
        data, "classic", {"lead_ms": 200, "tail_ms": 500}).content)[0]
    assert plain["start_ms"] == 10_000 and plain["end_ms"] == 11_000
    assert extended["start_ms"] == 9_800
    assert extended["end_ms"] == 11_500


def test_lead_never_pushes_into_the_previous_line(sample):
    events = parse_events(generate_ass(sample, "classic", {"lead_ms": 1500}).content)
    assert events[1]["start_ms"] >= events[0]["end_ms"]


def test_short_words_get_a_minimum_event(sample):
    short = recording([seg(0.0, 1.0, [("Ja", 0.0, 0.02), ("nein", 0.03, 0.05)])])
    events = parse_events(generate_ass(short, "highlight").content)
    for ev in events:
        assert ev["end_ms"] > ev["start_ms"]


def test_uppercase_and_box_parameters(sample):
    result = generate_ass(sample, "modern", {"uppercase": True, "box": True})
    assert "HALLO" in result.content
    style = [l for l in result.content.splitlines() if l.startswith("Style:")][0]
    assert ",3," in style  # BorderStyle 3 = Kasten


# ---------------------------------------------------------------------------
# Fehlende / gemischte Wortzeiten
# ---------------------------------------------------------------------------


def test_recording_without_word_timings_raises():
    """Nur Segmentzeiten (keine Wortzeiten) → kein Export mit geratenen Zeiten."""
    no_words = recording([{"start": 0.0, "end": 2.0, "text": "nur segmentzeiten",
                           "words": []}])
    with pytest.raises(NoWordTimestamps):
        generate_ass(no_words, "classic")


def test_words_without_duration_raise_too():
    """Wörter mit start == end (kein Alignment) sind keine brauchbaren Zeiten."""
    flat = recording([{"start": 0.0, "end": 2.0, "text": "Hallo Welt",
                       "words": [{"start": 0.0, "end": 0.0, "text": "Hallo"},
                                 {"start": 0.0, "end": 0.0, "text": "Welt"}]}])
    with pytest.raises(NoWordTimestamps):
        generate_ass(flat, "classic")


def test_recording_without_segments_raises():
    with pytest.raises(NoWordTimestamps):
        generate_ass(recording([]), "classic")


def test_segment_without_words_is_distributed_and_reported():
    """Mischfall: echte Wortzeiten vorhanden, ein Segment nur mit Segmentzeit.

    Das untimed Segment wird über seine Segmentgrenzen verteilt (Text geht
    nicht verloren) und der Export als ``mixed`` gemeldet.
    """
    mixed = recording([
        seg(0.0, 2.0, [("echt", 0.0, 0.5), ("zeitlich", 0.6, 1.0)]),
        {"start": 2.0, "end": 4.0, "text": "zwei wörter ohne zeit", "words": []},
    ])
    result = generate_ass(mixed, "classic")
    assert result.timing == "mixed"
    assert "fallback_timing_words" in result.warnings
    assert result.words == 6  # 2 echte + 4 verteilte Wörter
    texts = " ".join(visible_text(e["text"])
                     for e in parse_events(result.content))
    assert "zwei wörter ohne zeit" in texts
    # Verteilt heisst: die Wörter liegen im Segment-Zeitfenster (2.0-4.0 s).
    events = parse_events(result.content)
    assert events[-1]["start_ms"] >= 2_000
    assert events[-1]["end_ms"] >= 4_000


def test_uniform_timing_is_flagged():
    """Gleichverteilte Wortdauern sind ein Fallback-Artefakt → Warnung."""
    words = [("w%d" % i, i * 0.5, i * 0.5 + 0.4) for i in range(8)]
    result = generate_ass(recording([seg(0.0, 4.0, words)]), "classic")
    assert "uniform_timing" in result.warnings


def test_skipped_segment_is_reported_not_silently_dropped():
    data = recording([
        seg(0.0, 1.0, [("ok", 0.0, 0.5)]),
        {"text": "ohne jede zeit", "words": []},  # kein start/end
    ])
    result = generate_ass(data, "classic")
    assert any(w.startswith("skipped_segments:") for w in result.warnings)


def test_overlapping_words_are_clamped_monotone():
    overlapping = recording([seg(0.0, 3.0, [
        ("eins", 0.0, 1.0), ("zwei", 0.5, 1.5), ("drei", 1.4, 2.0),
    ])])
    words = parse_events(generate_ass(overlapping, "classic").content)
    assert len(words) == 1  # eine Caption-Zeile
    events = parse_events(generate_ass(overlapping, "highlight").content)
    for prev, cur in zip(events, events[1:]):
        assert cur["start_ms"] >= prev["end_ms"]


def test_speaker_change_breaks_the_line():
    data = recording([
        seg(0.0, 1.0, [("Hallo", 0.0, 0.4), ("Welt", 0.45, 0.9)], speaker="A"),
        seg(1.0, 2.0, [("Nein", 1.0, 1.4), ("doch", 1.45, 1.9)], speaker="B"),
    ])
    result = generate_ass(data, "classic")
    assert result.lines == 2
    names = {e["name"] for e in parse_events(result.content)}
    assert names == {"A", "B"}


def test_speaker_commas_do_not_break_the_event_line():
    data = recording([seg(0.0, 1.0, [("Hi", 0.0, 0.5)], speaker="Müller, Anna")])
    ev = parse_events(generate_ass(data, "classic").content)[0]
    assert ev["name"] == "Müller Anna"


def test_preset_templates_reference_only_known_parameters():
    """Jeder ``params.X``-Verweis einer Vorlage muss ein bekannter Parameter sein.

    Ein Tippfehler in einer Vorlage fällt sonst erst zur Laufzeit auf
    (StrictUndefined → 500 beim Export statt Fehler im Test).
    """
    from app.ass_export.presets import PARAM_SPECS, template_param_refs, used_params

    for preset in list_presets():
        refs = template_param_refs(preset)
        unknown = [r for r in refs if r not in PARAM_SPECS]
        assert not unknown, f"{preset.name}: unbekannte Parameter in der Vorlage: {unknown}"
        assert refs, f"{preset.name}: Vorlage benutzt keinen einzigen Parameter"
        assert used_params(preset), f"{preset.name}: keine benutzten Parameter erkannt"


def test_used_params_tell_the_ui_what_to_show():
    """Die UI blendet Regler anhand von ``used_params`` aus — das muss stimmen.

    klassisch kennt nur eine Schriftfarbe, Hervorhebung zusätzlich die
    Akzentfarbe (aus dem ``style``-Block, nicht aus der Vorlage!); beides muss
    sich in ``used_params`` widerspiegeln, sonst stehen wirkungslose Regler im
    Dialog — oder, schlimmer, ein Regler mit Wirkung fehlt.
    """
    classic = set(load_preset("classic").as_dict()["used_params"])
    highlight = set(load_preset("highlight").as_dict()["used_params"])
    assert "text_color" in classic
    assert "accent_color" not in classic
    assert "accent_color" in highlight and "dim_color" in highlight
    assert "pop_scale" not in highlight
    assert "pop_scale" in set(load_preset("kinetic").as_dict()["used_params"])
    # Generator-Parameter (Zeilenbildung, Zeiten) wirken in JEDEM Preset.
    for name in ALL_PRESETS:
        used = set(load_preset(name).as_dict()["used_params"])
        assert {"words_per_line", "sentence_breaks", "tail_ms", "uppercase"} <= used
        assert "font_size" in used and "position" in used


#: Testwerte je Parameter (Deltas groß genug, dass sie sicher in der Ausgabe
#: ankommen — 1 ms Unterschied verschwindet z. B. in der Zentisekunden-Rundung).
_PROBE_DELTA = {
    "font_size": 7,
    "margin_v": 31,
    "lead_ms": 37,
    "tail_ms": 41,
    "fade_ms": 60,
    "outline_width": 1,
    "shadow": 1,
    "pop_scale": 9,
    "pop_ms": 23,
    "active_scale": 7,
    "play_res_x": 120,
    "play_res_y": 120,
    "words_per_line": 1,
}
_PROBE_VALUE = {
    "font_name": "DejaVu Sans",
    "text_color": "#123456",
    "accent_color": "#00FF00",
    "dim_color": "#010203",
    "outline_color": "#654321",
    "position": "top",
}


def _probe_recordings():
    """Zwei Aufnahmen, weil ein Parameter nur in der passenden Lage sichtbar wird.

    * ``plain`` — acht Wörter ohne Satzzeichen: nur hier wird sichtbar, wie
      viele Wörter pro Zeile gruppiert werden.
    * ``sentences`` — Satzende früh in der Wortliste: nur hier wirkt der
      Schalter „am Satzende umbrechen" (mit Satzende am Zeilenende fällt er
      mit dem Zeilenumbruch zusammen und ist nicht messbar).
    """
    plain = recording([seg(0.0, 3.0, [
        ("eins", 0.0, 0.3), ("zwei", 0.35, 0.65), ("drei", 0.7, 1.0),
        ("vier", 1.05, 1.35), ("fuenf", 1.4, 1.7), ("sechs", 1.75, 2.05),
        ("sieben", 2.1, 2.4), ("acht", 2.45, 2.8),
    ])])
    sentences = recording([seg(0.0, 3.0, [
        ("Ein", 0.0, 0.2), ("Satz.", 0.25, 0.6), ("Danach", 0.7, 1.0),
        ("geht", 1.05, 1.3), ("es", 1.35, 1.55), ("weiter", 1.6, 1.8),
        ("und", 1.85, 2.0), ("weiter.", 2.05, 2.4),
    ])])
    return [plain, sentences]


@pytest.mark.parametrize("name", ALL_PRESETS)
def test_used_params_match_the_rendered_output(name):
    """`used_params` muss die WIRKUNG beschreiben, nicht die Herkunft.

    Drei Fehler, die dieser Test verhindert:

    1. Farben kommen nicht aus der Vorlage, sondern aus dem Stil-Bauer in
       Python — eine reine Textsuche in der Vorlage hätte sie übersehen und die
       GUI hätte die Farbregler versteckt, obwohl sie etwas bewirken.
    2. Parameter können einander bedingen: bei „Social Media" wirkt die
       Grau-Farbe nur, wenn „noch nicht gesprochene Wörter ausblenden" aus ist.
    3. Parameter wirken nur in der passenden Textsorte (Wörter pro Zeile nur
       ohne Satzzeichen, „am Satzende umbrechen" nur mit frühem Satzende).

    Deshalb wird jede Einstellung über mehrere Aufnahmen und Konfigurationen
    geprüft. Ergebnis: Jeder gelistete Parameter ändert in mindestens einer
    Kombination die Ausgabe, jeder nicht gelistete ändert sie in keiner.
    """
    from app.ass_export.presets import PARAM_SPECS

    recordings = _probe_recordings()
    preset = load_preset(name)
    used = set(preset.as_dict()["used_params"])
    defaults = preset.resolve(None)
    bool_keys = [k for k, spec in PARAM_SPECS.items() if spec["type"] == "bool"]
    configs = [{}] + [{k: (not defaults[k])} for k in bool_keys]

    def probe_values(key: str) -> List[Any]:
        spec = PARAM_SPECS[key]
        default = defaults[key]
        if spec["type"] == "bool":
            return [not default]
        if spec["type"] == "int":
            delta = _PROBE_DELTA.get(key, 10)
            return [v for v in (default + delta, default - delta)
                    if spec["min"] <= v <= spec["max"] and v != default]
        if spec["type"] == "enum":
            return [v for v in spec["values"] if v != default]
        return [_PROBE_VALUE[key]]

    for key in PARAM_SPECS:
        values = probe_values(key)
        changed = False
        for rec in recordings:
            for config in configs:
                if key in config:
                    continue  # diese Konfiguration stellt den Parameter selbst um
                baseline = generate_ass(rec, name, config).content
                for value in values:
                    overrides = dict(config)
                    overrides[key] = value
                    if generate_ass(rec, name, overrides).content != baseline:
                        changed = True
                        break
                if changed:
                    break
            if changed:
                break
        if key in used:
            assert changed, (
                f"{name}: {key} steht in used_params, ändert die Ausgabe aber in "
                f"keiner geprüften Kombination — wirkungsloser Regler im Dialog"
            )
        else:
            assert not changed, (
                f"{name}: {key} fehlt in used_params, verändert die Ausgabe aber "
                f"— die GUI hätte den Regler versteckt, obwohl er wirkt"
            )


# ---------------------------------------------------------------------------
# Template-Engine-Helfer
# ---------------------------------------------------------------------------


def test_ass_escape_replaces_braces_and_linebreaks():
    assert ass_escape("a{b}c") == "a(b)c"
    assert ass_escape("a}b") == "a)b"
    assert ass_escape("kein\\Numbruch") == "kein umbruch"
    assert ass_escape("kein\\numbruch") == "kein umbruch"
    assert ass_escape(None) == ""


def test_timecode_format():
    assert tc(0) == "0:00:00.00"
    assert tc(3661230) == "1:01:01.23"
    assert tc(-5) == "0:00:00.00"
    assert tc(999) == "0:00:00.99"


def test_centiseconds_floor():
    assert cs(0) == 1
    assert cs(999) == 100
    assert cs(15) == 2


def test_unknown_template_variable_is_an_error(tmp_path):
    """Tippfehler in einer Vorlage dürfen nicht still leer rendern."""
    from app.ass_export.template_engine import AssTemplateError, render_source

    with pytest.raises(AssTemplateError):
        render_source("{{ gibts_nicht }}", {})
