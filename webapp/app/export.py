"""Template-basierter Export (Change 008, Subtitle-Edit-kompatibel).

Exportformate sind JSON-Template-Dateien mit Platzhaltern, über die pro
Segment geloopt wird — analog zu Subtitle Edit (``CustomFormatTemplate``
/ ``CustomTextFormatter``). Damit lassen sich neue Formate ohne Code-
Änderung hinzufügen (auch durch Admins: Datei anlegen), und Templates
aus Subtitle Edit sind theoretisch direkt nutzbar (Platzhalter-Vokabular
+ TimeCode-Syntax sind 1:1 kompatibel).

Template-Struktur (Pflichtfelder fett):
- **name** — Anzeigename (z. B. "SubRip (SRT)")
- **extension** — Dateiendung (z. B. "srt")
- **format_header** — einmaliger Kopf (darf leer sein)
- **format_paragraph** — pro Segment geloopt (darf leer sein → kein Loop,
  z. B. Plain-Text-Export über den Header)
- **format_footer** — einmaliger Fuß (darf leer sein)
- **format_timecode** — Zeitformat-Zeichenkette (SE-Syntax, s. u.)
- format_newline — Zeilenumbruch-Ersetzung (optional, Default unverändert)

Platzhalter (Header/Footer):
{title}, {media-file-name}, {media-file-name-with-ext}, {#lines},
{#total-words}, {#total-characters}, {tab}; zusätzlich (App-Erweiterung,
dokumentiert in Req 6): {full-text} = Gesamt-Transkript.

Platzhalter (Paragraph, pro Segment):
{start}, {end} (im format_timecode-Format), {text}, {text-csv}
(CSV-escaped), {number} (1-basiert), {number-1} (0-basiert), {duration},
{actor} (Sprecher-Label), {actor-colon-space} ("SPEAKER_01: "),
{actor-upper-brackets-space} ("[SPEAKER_01] "), {text-line-1},
{text-line-2}, {text-length}, {gap}, {bookmark} ("*"), {tab}.
Nicht unterstützt (kein Übersetzungspaar): {original-text} → leer.
Unbekannte Platzhalter bleiben literal (kein stummer Fehler).

TimeCode-Syntax (SE-kompatibel):
- h/m/s = Stunden/Minuten/Sekunden (Doppelbuchstabe = zweistellig),
  z = Millisekunden-Bruchteil, f = Frames
- Führender Lauf aus s/z (≥2 Zeichen) = Gesamt-Sekunden/-Millisekunden
  ("ss.zzz" → "61.160", "zzz" → "61160"); "ff" allein = Gesamt-Frames
- Beispiele: "hh:mm:ss,zzz" (SRT), "hh:mm:ss.zzz" (VTT), "mm:ss,ff"

NewLine (format_newline): "{newline}" = System-Newline, "{lf}" = \\n,
"{cr}" = \\r, "{tab}" = \\t; Sonderwert "[Do not modify]" = unverändert.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

#: Eingebaute Standard-Templates (im Repo gebündelt) — werden beim Start
#: nach DATA_DIR/export_templates/ kopiert, falls dort nicht vorhanden.
BUNDLED_TEMPLATES_DIR = Path(__file__).parent / "export_templates"

#: Pflichtfelder eines Templates (fehlen sie → TemplateInvalid).
REQUIRED_FIELDS = ("name", "extension", "format_paragraph",
                   "format_timecode")

_PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")
_FRAMES_PER_SECOND = 25  # App kennt keine Video-FPS → SE-Default


class TemplateNotFound(Exception):
    """Angefragtes Export-Template existiert nicht (→ 404)."""


class TemplateInvalid(Exception):
    """Template-Datei kaputt (fehlende Felder / ungültiges JSON → 500)."""


# ---------------------------------------------------------------------------
# Verwaltung
# ---------------------------------------------------------------------------


def ensure_standard_templates(target_dir: Path) -> None:
    """Kopiert die gebündelten Standard-Templates nach *target_dir*, falls
    dort nicht vorhanden (idempotent; eigene Templates bleiben erhalten)."""
    if not BUNDLED_TEMPLATES_DIR.is_dir():
        return
    target_dir.mkdir(parents=True, exist_ok=True)
    for src in sorted(BUNDLED_TEMPLATES_DIR.glob("*.json")):
        dst = target_dir / src.name
        if not dst.exists():
            shutil.copyfile(src, dst)


def export_templates_dir() -> Path:
    """DATA_DIR/export_templates — Ablage für Export-Templates (Change 008).

    Standard-Templates werden beim Start nachgeschrieben (falls fehlend),
    eigene Templates = Datei anlegen (kein Code-Rebuild, auch durch Admin).
    """
    from .config import settings

    d = settings.DATA_DIR / "export_templates"
    ensure_standard_templates(d)
    return d


def list_templates(templates_dir: Path) -> List[Dict[str, str]]:
    """Name + Endung aller verfügbaren Templates (für das UI-Dropdown)."""
    out: List[Dict[str, str]] = []
    if not templates_dir.is_dir():
        return out
    for f in sorted(templates_dir.glob("*.json")):
        try:
            data = _load_json(f)
        except TemplateInvalid:
            continue  # kaputte Template-Datei nicht im Dropdown listen
        out.append({"name": data.get("name", f.stem),
                    "extension": data.get("extension", f.stem)})
    return out


def load_template(name: str, templates_dir: Path) -> Dict[str, Any]:
    """Lädt ein Template; wirft TemplateNotFound (404) bzw.
    TemplateInvalid (500) mit aussagekräftiger Meldung."""
    # Sicherheits-Härtung: nur einfache Namen, kein Pfad-Traversal.
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name):
        raise TemplateNotFound(name)
    path = templates_dir / f"{name}.json"
    if not path.is_file():
        raise TemplateNotFound(name)
    data = _load_json(path)
    missing = [k for k in REQUIRED_FIELDS if k not in data]
    if missing:
        raise TemplateInvalid(
            f"template '{name}' missing fields: {', '.join(missing)}"
        )
    return data


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        raise TemplateInvalid(f"template '{path.name}' unreadable: {exc}") from exc
    if not isinstance(data, dict):
        raise TemplateInvalid(f"template '{path.name}' must be a JSON object")
    return data


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_template(
    template: Dict[str, Any],
    segments: List[Dict[str, Any]],
    meta: Dict[str, Any],
) -> str:
    """Rendert Header, dann pro Segment eine Instanz von format_paragraph,
    dann Footer (Paragraphen mit \\n verbunden — gleiche Semantik wie die
    früheren hartkodierten to_srt/to_vtt: Cues durch Leerzeile getrennt).

    Change 015: optionales ``format_paragraph_word`` — wenn gesetzt UND die
    Segmente Word-Timings (``words[]`` mit start/end/text) enthalten, wird
    pro WORT ein Paragraph gerendert (z. B. Word-Level-SRT); ohne Words
    fällt der Renderer auf den Segment-Loop zurück (identische Ausgabe).
    """
    header = _expand(template.get("format_header", ""),
                     _header_values(meta, segments))
    para_tpl = template.get("format_paragraph", "")
    word_tpl = template.get("format_paragraph_word", "")
    paragraphs: List[str] = []
    if para_tpl:
        tc = template.get("format_timecode", "")
        if word_tpl and _has_word_timings(segments):
            word_segs = _word_rows(segments)
            for i, seg in enumerate(word_segs):
                paragraphs.append(_expand(
                    word_tpl,
                    _para_values(i, seg, word_segs, tc),
                ))
        else:
            for i, seg in enumerate(segments):
                paragraphs.append(_expand(
                    para_tpl,
                    _para_values(i, seg, segments, tc),
                ))
    footer = _expand(template.get("format_footer", ""),
                     _header_values(meta, segments))
    content = header + "\n".join(paragraphs) + footer
    return _apply_newline(content, template.get("format_newline", ""))


def _has_word_timings(segments: List[Dict[str, Any]]) -> bool:
    """Mindestens ein Segment mit brauchbaren Word-Timings? (Change 015)

    Whisper-Wörter tragen das Feld ``word`` (nicht ``text``) — beides wird
    akzeptiert, damit Word-Level-Exporte auch für ASR-Wörter funktionieren.
    """
    for seg in segments:
        words = seg.get("words") or []
        for w in words:
            if isinstance(w, dict) and (w.get("text") or w.get("word")):
                return True
    return False


def _word_rows(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Flacht Segment-Words zu Cue-Dicts ab (start/end/text/speaker).

    - Wörter mit eigenen Timings (``words[]`` mit start/end) behalten sie.
    - Segmente OHNE Words (oder Wörter ohne Timing) werden per Text-Split
      in Wörter zerlegt und erben die SEGMENT-Grenzen (Fallback) — so geht
      im Word-Level-Export kein Wort verloren.
    """
    rows: List[Dict[str, Any]] = []
    for seg in segments:
        seg_start = float(seg.get("start") or 0.0)
        seg_end = float(seg.get("end") or seg_start)
        words = seg.get("words") or []
        timed: List[Dict[str, Any]] = []
        for w in words:
            if not isinstance(w, dict):
                continue
            text = str(w.get("text") or w.get("word") or "").strip()
            if not text:
                continue
            timed.append({
                "start": float(w.get("start", seg_start)),
                "end": float(w.get("end", seg_end)),
                "text": text,
                "speaker": seg.get("speaker"),
            })
        if timed:
            rows.extend(timed)
            continue
        # Fallback: Segment-Text splitten, Segment-Grenzen vererben.
        for token in str(seg.get("text") or "").split():
            rows.append({
                "start": seg_start,
                "end": seg_end,
                "text": token,
                "speaker": seg.get("speaker"),
            })
    return rows


def _expand(tpl: str, values: Dict[str, str]) -> str:
    """Ersetzt bekannte Platzhalter; unbekannte bleiben literal."""

    def _repl(m: "re.Match[str]") -> str:
        key = m.group(1)
        return values.get(key, m.group(0))

    return _PLACEHOLDER_RE.sub(_repl, tpl)


def _header_values(meta: Dict[str, Any], segments: List[Dict[str, Any]]) -> Dict[str, str]:
    text = str(meta.get("text") or "")
    words = text.split()
    chars = len(text)
    return {
        "title": str(meta.get("title") or ""),
        "media-file-name": str(meta.get("media_file_name") or ""),
        "media-file-name-with-ext": str(meta.get("media_file_name_with_ext") or ""),
        "#lines": str(len(segments)),
        "#total-words": str(len(words)),
        "#total-characters": str(chars),
        "tab": "\t",
        # App-Erweiterung (Req 6): Gesamt-Transkript für Plain-Text-Export.
        "full-text": str(meta.get("text") or "").strip(),
    }


def _para_values(
    i: int,
    seg: Dict[str, Any],
    all_segs: List[Dict[str, Any]],
    timecode_fmt: str,
) -> Dict[str, str]:
    text = str(seg.get("text") or "").strip()
    speaker = str(seg.get("speaker") or "")
    start = float(seg.get("start") or 0.0)
    end = float(seg.get("end") or start)
    lines = text.split("\n")
    gap = ""
    if i + 1 < len(all_segs):
        nxt = float(all_segs[i + 1].get("start") or 0.0)
        gap = _format_timecode(max(nxt - end, 0.0), timecode_fmt)
    return {
        "start": _format_timecode(start, timecode_fmt),
        "end": _format_timecode(end, timecode_fmt),
        "text": text,
        "text-csv": '"' + text.replace('"', '""') + '"',
        # Change 015: maschinenlesbares Segment-Objekt (JSON-Lines-Template).
        "json": json.dumps({
            "start": round(float(seg.get("start") or 0.0), 3),
            "end": round(float(seg.get("end") or 0.0), 3),
            "speaker": speaker or None,
            "text": text,
        }, ensure_ascii=False),
        "number": str(i + 1),
        "number-1": str(i),
        "duration": _format_timecode(max(end - start, 0.0), timecode_fmt),
        "actor": speaker,
        "actor-colon-space": f"{speaker}: " if speaker else "",
        "actor-upper-brackets-space": f"[{speaker}] " if speaker else "",
        "text-line-1": lines[0] if lines else "",
        "text-line-2": "\n".join(lines[1:]) if len(lines) > 1 else "",
        "text-length": str(len(text)),
        "gap": gap,
        "bookmark": "*",
        "original-text": "",  # kein Übersetzungspaar in der App
        "tab": "\t",
    }


def _apply_newline(content: str, spec: str) -> str:
    """Wendet die NewLine-Definition (format_newline) auf den gerenderten
    Text an — SE-Semantik: Zeilenumbrüche IM Text werden ersetzt.

    - ``[Do not modify]`` (oder leer): Newlines bleiben unverändert.
    - ``{newline}``/``{lf}``: Zeilenumbruch → ``\\n`` (System-Newline).
    - ``{cr}``: Zeilenumbruch → ``\\r``.
    - ``{tab}``: Zeilenumbruch → ``\\t``.
    """
    if not spec or spec == "[Do not modify]":
        return content
    target = {
        "{newline}": "\n",
        "{lf}": "\n",
        "{cr}": "\r",
        "{tab}": "\t",
    }.get(spec.strip(), None)
    if target is None:
        return content
    return content.replace("\n", target)


# ---------------------------------------------------------------------------
# TimeCode (SE-Syntax)
# ---------------------------------------------------------------------------


def _format_timecode(seconds: float, fmt: str) -> str:
    """Formatiert *seconds* nach SE-TimeCode-Syntax (s. Modul-Docstring)."""
    if not fmt:
        return ""
    seconds = max(0.0, seconds)

    # Gesamt-Sekunden/-Millisekunden: führender Lauf aus s/z (≥2 Zeichen).
    m = re.match(r"^(s{2,}|z{2,})", fmt)
    if m:
        run = m.group(1)
        if run[0] == "s":
            total_s = int(round(seconds))
            frac = ""
            rest = fmt[len(run):]
            fm = re.match(r"^[.,](z+)$", rest)
            if fm:
                width = len(fm.group(1))
                ms = int(round((seconds - int(seconds)) * 1000))
                frac = rest[0] + f"{ms:0{width}d}"
            return f"{total_s:0{len(run)}d}{frac}"
        return str(int(round(seconds * 1000)))

    # "ff" allein = Gesamt-Frames.
    if re.fullmatch(r"f{2,}", fmt):
        return str(int(round(seconds * _FRAMES_PER_SECOND)))

    # Uhr-Komponenten + Trennzeichen.
    out: List[str] = []
    i = 0
    n = len(fmt)
    while i < n:
        ch = fmt[i]
        if ch in "hms":
            j = i
            while j < n and fmt[j] == ch:
                j += 1
            width = j - i
            if ch == "h":
                val = int(seconds // 3600)
            elif ch == "m":
                val = int((seconds % 3600) // 60)
            else:
                val = int(seconds % 60)
            out.append(f"{val:0{width}d}" if width >= 2 else str(val))
            i = j
        elif ch == "z":
            j = i
            while j < n and fmt[j] == "z":
                j += 1
            width = j - i
            ms = int(round((seconds - int(seconds)) * 1000))
            out.append(f"{ms:0{width}d}"[:width])
            i = j
        elif ch == "c":
            # Change 015: Zentisekunden (0-99) — ASS/SSA-Timecode h:mm:ss.cc.
            j = i
            while j < n and fmt[j] == "c":
                j += 1
            width = j - i
            cs = int(round((seconds - int(seconds)) * 100))
            out.append(f"{cs:0{width}d}"[:width])
            i = j
        elif ch == "f":
            j = i
            while j < n and fmt[j] == "f":
                j += 1
            width = j - i
            frames = int(round((seconds - int(seconds)) * _FRAMES_PER_SECOND))
            out.append(f"{frames:0{width}d}"[:width])
            i = j
        else:
            out.append(ch)
            i += 1
    return "".join(out)
