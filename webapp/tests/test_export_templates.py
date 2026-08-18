"""Change 008: Template-basierter Export (Subtitle-Edit-kompatibel).

- render_template: Platzhalter (Header/Paragraph), SE-TimeCode-Syntax,
  Loop über format_paragraph, Header/Footer, NewLine-Ersetzung
- Golden-Tests: eingebautes srt/vtt/txt-Template erzeugt Byte-gleiche
  Ausgabe wie die früheren hartkodierten to_srt/to_vtt/to_txt
- API: GET /api/export-templates; download?format=<template>;
  unbekanntes Template → 404; kaputtes Template → 500 mit Meldung
- Eigene Templates (YouTube-Transcript-Stil) ohne Code-Änderung
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from sqlmodel import SQLModel, create_engine

    from app import db as db_module
    from app.config import settings
    from app.main import app

    eng = create_engine(f"sqlite:///{tmp_path / 'exp.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(settings, "AUDIO_DIR", audio_dir)
    # Change 008: Templates landen im Test-DATA_DIR (nicht /data).
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(settings, "OIDC_ENABLED", False)

    with TestClient(app) as c:
        yield c


def _make_done_recording(client, segments, text=None) -> str:
    resp = client.post(
        "/api/recordings",
        files={"file": ("template-test.mp3", b"fake-audio-bytes", "audio/mpeg")},
    )
    assert resp.status_code == 201, resp.text
    rid = resp.json()["uid"]

    from app.db import engine
    from app.models import Recording
    from sqlmodel import Session, select

    with Session(engine) as s:
        rec = s.exec(select(Recording).where(Recording.uid == rid)).first()
        assert rec is not None
        rec.status = "done"
        rec.segments = segments
        rec.text = text if text is not None else " ".join(str(x["text"]) for x in segments)
        s.add(rec)
        s.commit()
    return rid


def _seg(start, end, text, speaker=None, words=None):
    seg = {"start": start, "end": end, "text": text}
    if speaker:
        seg["speaker"] = speaker
    if words:
        seg["words"] = words
    return seg


# ---------------------------------------------------------------------------
# render_template — Platzhalter + SE-TimeCode-Syntax
# ---------------------------------------------------------------------------


def test_render_placeholders_and_timecode():
    from app.export import render_template

    tpl = {
        "name": "Test",
        "extension": "txt",
        "format_header": "{title} | {#lines} Zeilen | {#total-words} Wörter | {#total-characters} Zeichen\n",
        "format_paragraph": "{number}. {start}–{end} [{actor}] {text} | dur={duration} | csv={text-csv} | L1={text-line-1} L2={text-line-2} | len={text-length} | gap={gap} | bm={bookmark} | orig={original-text}\n",
        "format_footer": "{media-file-name} ({media-file-name-with-ext}) {tab}Ende",
        "format_timecode": "hh:mm:ss,zzz",
        "format_newline": "[Do not modify]",
    }
    segs = [
        _seg(0, 5, "Hallo Welt", "SPEAKER_01"),
        _seg(5, 7.5, "zweite\nZeile", None),
    ]
    meta = {"title": "Titel", "media_file_name": "test", "media_file_name_with_ext": "test.mp3", "text": "Hallo Welt zweite Zeile"}

    out = render_template(tpl, segs, meta)
    lines = out.split("\n")
    assert lines[0] == "Titel | 2 Zeilen | 4 Wörter | 23 Zeichen"
    assert "1. 00:00:00,000–00:00:05,000 [SPEAKER_01] Hallo Welt" in out
    assert "dur=00:00:05,000" in out
    assert 'csv="Hallo Welt"' in out
    assert "L1=zweite L2=Zeile" in out
    assert "len=12" in out  # "zweite\nZeile" = 12 Zeichen
    # gap zwischen Segment 1 (end 5) und Segment 2 (start 5) = 0
    # zweites Segment: gap zum Ende = "" (kein nächster)
    assert out.strip().endswith("test (test.mp3) \tEnde")
    assert "orig=" in out  # {original-text} = leer


def test_render_unknown_placeholder_stays_literal():
    from app.export import render_template

    tpl = {
        "name": "T", "extension": "x", "format_header": "{kaputt} bleibt",
        "format_paragraph": "{text} {unbekannt}", "format_footer": "",
        "format_timecode": "", "format_newline": "[Do not modify]",
    }
    out = render_template(tpl, [_seg(0, 1, "Hi")], {"text": "Hi"})
    assert "{kaputt}" in out and "{unbekannt}" in out
    assert "Hi" in out


def test_timecode_ss_zzz_gesamtform():
    """SE-Syntax: führender s/z-Lauf = Gesamt-Sekunden/-Millisekunden."""
    from app.export import _format_timecode

    assert _format_timecode(61.16, "ss.zzz") == "61.160"
    assert _format_timecode(61.16, "zzz") == "61160"
    assert _format_timecode(61.16, "hh:mm:ss,zzz") == "00:01:01,160"
    assert _format_timecode(61.16, "hh:mm:ss.zzz") == "00:01:01.160"
    assert _format_timecode(61.16, "mm:ss,ff") == "01:01,04"  # 25 fps
    assert _format_timecode(3661.5, "hh:mm:ss,zzz") == "01:01:01,500"


def test_newline_replacements():
    """SE-Semantik: format_newline ersetzt Zeilenumbrüche IM Text."""
    from app.export import render_template

    def _render(spec: str) -> str:
        tpl = {
            "name": "T", "extension": "x",
            "format_header": "", "format_paragraph": "{text}",
            "format_footer": "", "format_timecode": "",
            "format_newline": spec,
        }
        return render_template(tpl, [_seg(0, 1, "a\nb")], {"text": "a\nb"})

    assert _render("[Do not modify]") == "a\nb"   # unverändert
    assert _render("{lf}") == "a\nb"              # → \n (System-Newline)
    assert _render("{newline}") == "a\nb"
    assert _render("{cr}") == "a\rb"              # → \r
    assert _render("{tab}") == "a\tb"             # → \t


# ---------------------------------------------------------------------------
# Golden-Tests: eingebaute Templates byte-gleich zu den alten Funktionen
# ---------------------------------------------------------------------------


def test_bundled_srt_byte_equal_to_old_to_srt():
    """Das eingebaute srt.json erzeugt exakt die frühere to_srt-Ausgabe."""
    from app.export import BUNDLED_TEMPLATES_DIR, load_template, render_template
    from app.service import to_srt

    segs = [
        _seg(0, 5, "Hallo Welt", "SPEAKER_01", [{"word": "Hallo", "start": 0, "end": 1}, {"word": "Welt", "start": 1, "end": 2}]),
        _seg(5, 9, "zweiter Satz", None),
        _seg(9, 12.5, "Grüße mit Ümlauten", "SPEAKER_02"),
    ]
    tpl = load_template("srt", BUNDLED_TEMPLATES_DIR)
    rendered = render_template(tpl, segs, {"text": "x"})
    assert rendered == to_srt(segs)
    # Stichprobe: erste Zeile + Leerzeile zwischen Cues (alte Semantik)
    assert rendered.startswith("1\n00:00:00,000 --> 00:00:05,000\n[SPEAKER_01] Hallo Welt\n\n2\n")


def test_bundled_vtt_byte_equal_to_old_to_vtt():
    from app.export import BUNDLED_TEMPLATES_DIR, load_template, render_template
    from app.service import to_vtt

    segs = [
        _seg(0, 5, "Hallo Welt", "SPEAKER_01"),
        _seg(5, 9, "zweiter Satz"),
    ]
    tpl = load_template("vtt", BUNDLED_TEMPLATES_DIR)
    rendered = render_template(tpl, segs, {"text": "x"})
    assert rendered == to_vtt(segs)
    # VTT nutzt den PUNKT als Dezimaltrenner (00:00:05.000)
    assert rendered.startswith("WEBVTT\n\n00:00:00.000 --> 00:00:05.000\n[SPEAKER_01] Hallo Welt\n")


def test_bundled_txt_byte_equal_to_old_to_txt():
    from app.export import BUNDLED_TEMPLATES_DIR, load_template, render_template
    from app.service import to_txt

    text = "  Hallo Welt zweiter Satz  "
    tpl = load_template("txt", BUNDLED_TEMPLATES_DIR)
    rendered = render_template(tpl, [], {"text": text})
    assert rendered == to_txt(text)


# ---------------------------------------------------------------------------
# API: /api/export-templates + download?format=<template>
# ---------------------------------------------------------------------------


def test_export_templates_list_endpoint(client):
    r = client.get("/api/export-templates")
    assert r.status_code == 200
    names = {t["name"] for t in r.json()["templates"]}
    exts = {t["extension"] for t in r.json()["templates"]}
    assert {"SubRip (SRT)", "WebVTT", "Plain Text"} <= names
    assert {"srt", "vtt", "txt"} <= exts


def test_download_srt_template_matches_old_output(client):
    segs = [
        _seg(0, 5, "Hallo Welt", "SPEAKER_01"),
        _seg(5, 9, "zweiter Satz"),
    ]
    rid = _make_done_recording(client, segs)

    r = client.get(f"/api/recordings/{rid}/download?format=srt")
    assert r.status_code == 200, r.text
    assert "charset=utf-8" in r.headers.get("content-type", "").lower()
    # Change 015: Text-Exporte als UTF-8 mit BOM (Notepad/Excel-kompatibel).
    assert r.content.startswith(b"\xef\xbb\xbf")
    body = r.content.decode("utf-8-sig")
    assert body.startswith("1\n00:00:00,000 --> 00:00:05,000\n[SPEAKER_01] Hallo Welt\n\n2\n")
    # Content-Disposition nutzt die Template-Endung
    assert 'filename="template-test.srt"' in r.headers.get("content-disposition", "")


def test_download_vtt_and_txt(client):
    segs = [_seg(0, 5, "Hallo Welt", "SPEAKER_01")]
    rid = _make_done_recording(client, segs)

    r = client.get(f"/api/recordings/{rid}/download?format=vtt")
    assert r.status_code == 200
    assert r.content.startswith(b"\xef\xbb\xbfWEBVTT")
    assert r.content.decode("utf-8-sig").startswith("WEBVTT\n\n00:00:00.000 --> 00:00:05.000\n[SPEAKER_01] Hallo Welt")

    r = client.get(f"/api/recordings/{rid}/download?format=txt")
    assert r.status_code == 200
    assert r.content.startswith(b"\xef\xbb\xbf")
    assert r.content.decode("utf-8-sig") == "Hallo Welt\n"


def test_download_txt_umlauts_have_bom(client):
    """Change 015 (User-Report): Umlaute im TXT-Download — BOM + korrekte
    UTF-8-Sequenz, damit Notepad/Excel sie anzeigen statt „Ã¤\"-Artefakten."""
    segs = [_seg(0, 5, "Grüße aus Köln: ÄÖÜ äöü ß München")]
    rid = _make_done_recording(client, segs, text="Grüße aus Köln: ÄÖÜ äöü ß München")

    r = client.get(f"/api/recordings/{rid}/download?format=txt")
    assert r.status_code == 200, r.text
    raw = r.content
    assert raw.startswith(b"\xef\xbb\xbf"), "UTF-8-BOM fehlt"
    # „ä\" als korrektes UTF-8-Byte (C3 A4) statt Latin-1-Artefakt (C3 83 C2 A4)
    assert b"Gr\xc3\xbc\xc3\x9fe" in raw
    assert b"\xc3\x83\xc2\xa4" not in raw
    assert raw.decode("utf-8-sig") == "Grüße aus Köln: ÄÖÜ äöü ß München\n"


def test_download_json_no_bom(client, tmp_path):
    """Change 015: JSON bleibt reines UTF-8 (kein BOM — strikte Parser)."""
    from app.config import settings

    tdir = settings.DATA_DIR / "export_templates"
    tdir.mkdir(parents=True, exist_ok=True)
    (tdir / "json.json").write_text(json.dumps({
        "name": "JSON",
        "extension": "json",
        "format_header": "",
        "format_paragraph": "{text}",
        "format_footer": "",
        "format_timecode": "",
        "format_newline": "[Do not modify]",
    }), encoding="utf-8")

    rid = _make_done_recording(client, [_seg(0, 5, "Grüße")], text="Grüße")
    r = client.get(f"/api/recordings/{rid}/download?format=json")
    assert r.status_code == 200, r.text
    assert not r.content.startswith(b"\xef\xbb\xbf")
    assert "Grüße" in r.content.decode("utf-8")


def test_download_max_duration_still_works(client):
    segs = [_seg(0, 10, " ".join(f"w{i}" for i in range(10)),
                 words=[{"word": f"w{i}", "start": float(i), "end": float(i + 1)} for i in range(10)])]
    rid = _make_done_recording(client, segs)

    r = client.get(f"/api/recordings/{rid}/download?format=srt&max_duration_s=4")
    assert r.status_code == 200
    cues = r.content.decode("utf-8-sig").strip().split("\n\n")
    assert len(cues) > 1  # 10-s-Segment in ≤4-s-Blöcke


def test_download_unknown_format_404(client):
    rid = _make_done_recording(client, [_seg(0, 5, "Hallo")])
    r = client.get(f"/api/recordings/{rid}/download?format=gibt-es-nicht")
    assert r.status_code == 404


def test_download_custom_template_youtube_style(client, tmp_path):
    """Eigenes Template (YouTube-Transcript-Stil) ohne Code-Änderung."""
    from app.config import settings

    tdir = settings.DATA_DIR / "export_templates"
    tdir.mkdir(parents=True, exist_ok=True)
    (tdir / "youtube.json").write_text(json.dumps({
        "name": "YouTube-Transcript",
        "extension": "txt",
        "format_header": "",
        # Kein abschließendes \n: der Renderer verbindet die Paragraphen
        # mit "\n" → exakt eine Zeile pro Segment (Spec-Szenario).
        "format_paragraph": "{start} {end}\n{text}",
        "format_footer": "",
        "format_timecode": "hh:mm:ss",
        "format_newline": "[Do not modify]",
    }), encoding="utf-8")

    rid = _make_done_recording(client, [_seg(0, 5, "Hallo Welt"), _seg(5, 9, "zweiter Satz")])

    # In der Template-Liste?
    r = client.get("/api/export-templates")
    assert any(t["name"] == "YouTube-Transcript" for t in r.json()["templates"])

    r = client.get(f"/api/recordings/{rid}/download?format=youtube")
    assert r.status_code == 200, r.text
    # Eine Zeile pro Segment, kein abschließendes Newline (Template ohne \n)
    assert r.content.decode("utf-8-sig") == "00:00:00 00:00:05\nHallo Welt\n00:00:05 00:00:09\nzweiter Satz"


def test_download_broken_template_500(client, tmp_path):
    """Kaputtes Template → 500 mit Fehlermeldung (kein stiller Download)."""
    from app.config import settings

    tdir = settings.DATA_DIR / "export_templates"
    tdir.mkdir(parents=True, exist_ok=True)
    (tdir / "kaputt.json").write_text("{ kein json", encoding="utf-8")

    rid = _make_done_recording(client, [_seg(0, 5, "Hallo")])
    r = client.get(f"/api/recordings/{rid}/download?format=kaputt")
    assert r.status_code == 500
    assert "kaputt" in r.json()["detail"]

    # Fehlende Pflichtfelder ebenfalls 500 mit Meldung
    (tdir / "kaputt.json").write_text(json.dumps({"name": "x"}), encoding="utf-8")
    r = client.get(f"/api/recordings/{rid}/download?format=kaputt")
    assert r.status_code == 500
    assert "missing fields" in r.json()["detail"]


def test_ensure_standard_templates_idempotent(tmp_path):
    """Standard-Templates werden geschrieben; eigene bleiben erhalten."""
    from app.export import BUNDLED_TEMPLATES_DIR, ensure_standard_templates

    target = tmp_path / "export_templates"
    ensure_standard_templates(target)
    assert (target / "srt.json").exists()
    assert (target / "vtt.json").exists()
    assert (target / "txt.json").exists()

    # Eigene Datei + erneuter Lauf → nichts überschrieben
    mine = target / "mine.json"
    mine.write_text(json.dumps({"custom": True}), encoding="utf-8")
    ensure_standard_templates(target)
    assert mine.exists()
    assert json.loads(mine.read_text(encoding="utf-8")) == {"custom": True}
    assert (target / "srt.json").exists()


# ---------------------------------------------------------------------------
# Change 015: neue Standard-Templates (csv, youtube, ass, transcript, jsonl,
# srt-words) + Word-Level-Renderer (format_paragraph_word)
# ---------------------------------------------------------------------------


def test_ensure_standard_templates_includes_change015(tmp_path):
    from app.export import ensure_standard_templates

    target = tmp_path / "export_templates"
    ensure_standard_templates(target)
    for name in ("csv", "youtube", "ass", "transcript", "jsonl", "srt-words"):
        assert (target / f"{name}.json").exists(), f"{name}.json fehlt"


def test_word_level_srt_renders_per_word():
    """Change 015: format_paragraph_word → ein Cue pro Wort (mit Timings)."""
    from app.export import BUNDLED_TEMPLATES_DIR, load_template, render_template

    tpl = load_template("srt-words", BUNDLED_TEMPLATES_DIR)
    segs = [
        _seg(0, 5, "Hallo Welt", "SPEAKER_01",
             words=[{"word": "Hallo", "start": 0, "end": 1},
                    {"word": "Welt", "start": 1, "end": 2}]),
        _seg(5, 9, "zweiter Satz", None),
    ]
    out = render_template(tpl, segs, {"text": "x"})
    # 4 Wörter → 4 Cues mit fortlaufender Nummer
    assert out.count("\n\n") == 3  # 4 Paragraphen, 3 Leerzeilen
    assert out.startswith("1\n00:00:00,000 --> 00:00:01,000\nHallo")
    assert "2\n00:00:01,000 --> 00:00:02,000\nWelt" in out
    assert "3\n00:00:05,000 --> 00:00:09,000\nzweiter" in out
    assert "4\n00:00:05,000 --> 00:00:09,000\nSatz" in out


def test_word_level_srt_fallback_without_words():
    """Keine Word-Timings → identische Ausgabe wie normales srt."""
    from app.export import BUNDLED_TEMPLATES_DIR, load_template, render_template

    tpl = load_template("srt-words", BUNDLED_TEMPLATES_DIR)
    segs = [_seg(0, 5, "Hallo Welt", "SPEAKER_01")]
    out = render_template(tpl, segs, {"text": "x"})
    assert out == "1\n00:00:00,000 --> 00:00:05,000\n[SPEAKER_01] Hallo Welt\n"


def test_csv_template_escapes_text():
    from app.export import BUNDLED_TEMPLATES_DIR, load_template, render_template

    tpl = load_template("csv", BUNDLED_TEMPLATES_DIR)
    segs = [_seg(0, 5, 'Sag "Hallo", sagte er', "SPEAKER_01")]
    out = render_template(tpl, segs, {"text": "x"})
    lines = out.strip().split("\n")
    assert lines[0] == "number,start,end,duration,speaker,text"
    assert '1,00:00:00.000,00:00:05.000,00:00:05.000,SPEAKER_01,"Sag ""Hallo"", sagte er"' in lines[1]


def test_youtube_template_timestamped():
    from app.export import BUNDLED_TEMPLATES_DIR, load_template, render_template

    tpl = load_template("youtube", BUNDLED_TEMPLATES_DIR)
    segs = [_seg(0, 5, "Hallo Welt"), _seg(5, 65, "zweiter Satz")]
    out = render_template(tpl, segs, {"text": "x"})
    # h:mm:ss — 65 s → 1:05 (keine führende Null bei Stunden=0)
    assert out == "0:00  Hallo Welt\n0:05  zweiter Satz"


def test_ass_template_dialogue_lines():
    from app.export import BUNDLED_TEMPLATES_DIR, load_template, render_template

    tpl = load_template("ass", BUNDLED_TEMPLATES_DIR)
    segs = [_seg(0, 5, "Hallo Welt", "SPEAKER_01")]
    out = render_template(tpl, segs, {"text": "x"})
    assert out.startswith("[Script Info]\nScriptType: v4.00+")
    assert "[Events]\nFormat: Layer, Start, End, Style" in out
    # h:mm:ss.cc (Zentisekunden) — ASS-Zeitformat
    assert "Dialogue: 0,0:00:00.00,0:00:05.00,Default,,0,0,0,,[SPEAKER_01] Hallo Welt" in out


def test_transcript_template_speaker_prefix():
    from app.export import BUNDLED_TEMPLATES_DIR, load_template, render_template

    tpl = load_template("transcript", BUNDLED_TEMPLATES_DIR)
    segs = [_seg(0, 5, "Hallo", "SPEAKER_01"), _seg(5, 9, "Welt", None)]
    out = render_template(tpl, segs, {"title": "Mein Titel", "text": "x"})
    assert out.startswith("Mein Titel\n\n")
    assert "[SPEAKER_01] Hallo" in out
    assert "\nWelt" in out  # ohne Speaker kein Präfix


def test_jsonl_template_one_object_per_line():
    from app.export import BUNDLED_TEMPLATES_DIR, load_template, render_template

    tpl = load_template("jsonl", BUNDLED_TEMPLATES_DIR)
    segs = [_seg(0, 5, "Hallo", "SPEAKER_01"), _seg(5, 9, "Grüße")]
    out = render_template(tpl, segs, {"text": "x"})
    lines = out.strip().split("\n")
    assert len(lines) == 2
    import json as _json

    obj = _json.loads(lines[0])
    assert obj == {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_01", "text": "Hallo"}
    obj2 = _json.loads(lines[1])
    assert obj2["text"] == "Grüße" and obj2["speaker"] is None


def test_download_csv_and_jsonl_formats(client):
    segs = [_seg(0, 5, "Grüße aus Köln", "SPEAKER_01")]
    rid = _make_done_recording(client, segs, text="Grüße aus Köln")

    r = client.get(f"/api/recordings/{rid}/download?format=csv")
    assert r.status_code == 200, r.text
    # BOM (Excel) + Header
    assert r.content.startswith(b"\xef\xbb\xbf")
    assert r.content.decode("utf-8-sig").split("\n")[0] == "number,start,end,duration,speaker,text"

    r = client.get(f"/api/recordings/{rid}/download?format=jsonl")
    assert r.status_code == 200, r.text
    # jsonl ist maschinenlesbar → KEIN BOM
    assert not r.content.startswith(b"\xef\xbb\xbf")
    import json as _json

    obj = _json.loads(r.content.decode("utf-8").strip())
    assert obj["text"] == "Grüße aus Köln"


def test_download_srt_words_format(client):
    segs = [_seg(0, 5, "Hallo Welt", "SPEAKER_01",
                 words=[{"word": "Hallo", "start": 0, "end": 1},
                        {"word": "Welt", "start": 1, "end": 2}])]
    rid = _make_done_recording(client, segs)
    r = client.get(f"/api/recordings/{rid}/download?format=srt-words")
    assert r.status_code == 200, r.text
    body = r.content.decode("utf-8-sig")
    assert body.startswith("1\n00:00:00,000 --> 00:00:01,000\nHallo")
    assert "2\n00:00:01,000 --> 00:00:02,000\nWelt" in body
