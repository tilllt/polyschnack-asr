"""Sandboxed Jinja2-Engine für ASS-Caption-Templates (Change 193).

Warum Jinja2 mit ``SandboxedEnvironment``:

* Caption-Templates werden später auch von Usern geschrieben (Template-
  Marktplatz, Phase 3) — ``SandboxedEnvironment`` verbietet Attribut-Zugriffe
  auf ``__class__``/``__globals__`` und damit den Ausbruch aus der Vorlage.
* Der Loader ist auf ``ass_export/presets/`` festgenagelt: Templates können
  ``_base.ass.j2`` importieren, aber keine Dateien ausserhalb lesen.

Empirisch belegte libass-Regeln (ffmpeg 7.1.5, libass, gerendert und
pixelweise verglichen — siehe ``tests/test_ass_export_render.py``), die die
Filter dieses Moduls begründen:

* ``A{B}C`` rendert wie ``AC`` — ein ``{...}``-Block wird von libass
  **verschluckt**. Geschweifte Klammern im Transkript müssen deshalb ersetzt
  werden, sonst verschwinden Wörter aus dem fertigen Video.
* ``A\\B`` rendert wie ``AB`` — ein Backslash im Fliesstext verschwindet.
  ``\\N``/``\\n`` werden als Zeilenumbruch interpretiert und deshalb zu einem
  Leerzeichen normalisiert.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional

from jinja2 import FileSystemLoader, StrictUndefined, TemplateError
from jinja2.sandbox import SandboxedEnvironment

#: Verzeichnis der Standard-Presets (Loader-Wurzel, auch für User-Templates).
PRESET_DIR = Path(__file__).parent / "presets"

_COLOR_RE = re.compile(r"^#?([0-9A-Fa-f]{6})$")
#: libass interpretiert "\N"/"\n" als harten/weichen Zeilenumbruch.
_LINEBREAK_RE = re.compile(r"\\[Nn]")


class AssTemplateError(Exception):
    """Template liess sich nicht rendern (kaputte Vorlage → 500)."""


# ---------------------------------------------------------------------------
# Filter
# ---------------------------------------------------------------------------


def ass_escape(text: Any) -> str:
    """Macht Fliesstext libass-sicher (ohne die ASS-Tags der Vorlage).

    * ``{`` / ``}`` → ``(`` / ``)``: libass verschluckt ``{...}``-Blöcke,
      das Wort dahinter wäre sonst im Video nicht zu sehen.
    * ``\\N`` / ``\\n`` → Leerzeichen: kein Umbruch aus Nutztext heraus.
    * Kommas bleiben erhalten — sie sind nur in Style/Event-Feldern
      (Spalte 1-9) kritisch, nicht im Text-Feld (letztes Feld).
    """
    s = "" if text is None else str(text)
    s = _LINEBREAK_RE.sub(" ", s)
    return s.replace("{", "(").replace("}", ")")


def parse_color(value: Any) -> tuple:
    """``"#RRGGBB"`` → ``(r, g, b)``; wirft ValueError bei ungültigem Wert."""
    m = _COLOR_RE.match(str(value or "").strip())
    if not m:
        raise ValueError(f"invalid color: {value!r} (expected #RRGGBB)")
    h = m.group(1)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def bgr(value: Any) -> str:
    """``"#RRGGBB"`` → ``"BBGGRR"`` für Inline-Tags ``{\\c&H..&}`` (BGR!)."""
    r, g, b = parse_color(value)
    return f"{b:02X}{g:02X}{r:02X}"


def ass_color(value: Any, alpha: int = 0) -> str:
    """``"#RRGGBB"`` → ``"&HAABBGGRR"`` für ``[V4+ Styles]``-Zeilen."""
    r, g, b = parse_color(value)
    a = max(0, min(255, int(alpha)))
    return f"&H{a:02X}{b:02X}{g:02X}{r:02X}"


def cs(ms: Any) -> int:
    """Millisekunden → Zentisekunden (ASS-Zeitbasis), nie kleiner als 1."""
    try:
        v = int(round(float(ms) / 10.0))
    except (TypeError, ValueError):
        return 1
    return max(1, v)


def tc(ms: Any) -> str:
    """Millisekunden → ASS-Zeitcode ``h:mm:ss.cc`` (Stunde einstellig)."""
    try:
        total = max(0, int(round(float(ms))))
    except (TypeError, ValueError):
        total = 0
    hours, rest = divmod(total, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    seconds, millis = divmod(rest, 1000)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{millis // 10:02d}"


# ---------------------------------------------------------------------------
# Environment + Rendering
# ---------------------------------------------------------------------------


def _environment(loader_dir: Optional[Path] = None) -> SandboxedEnvironment:
    """Sandbox-Umgebung mit ASS-Filtern.

    ``StrictUndefined``: ein Tippfehler in der Vorlage wird zum Fehler statt
    zu leerer Ausgabe — „kein stiller Fehler" gilt auch für Templates.
    """
    env = SandboxedEnvironment(
        loader=None
        if loader_dir is None
        else FileSystemLoader(str(loader_dir)),
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
        trim_blocks=False,
        lstrip_blocks=False,
    )
    env.filters.update(
        ass_escape=ass_escape,
        bgr=bgr,
        ass_color=ass_color,
        cs=cs,
        tc=tc,
    )
    env.globals.update(
        bgr=bgr,
        ass_color=ass_color,
        cs=cs,
        tc=tc,
        ass_escape=ass_escape,
    )
    return env


def render_source(
    source: str,
    context: Dict[str, Any],
    loader_dir: Optional[Path] = None,
) -> str:
    """Rendert eine Vorlage (String) mit *context*.

    ``loader_dir`` erlaubt ``{% import "_base.ass.j2" %}`` aus dem
    Preset-Verzeichnis. Fehler werden als :class:`AssTemplateError` gemeldet
    (nie stillschweigend leere Ausgabe).
    """
    env = _environment(loader_dir)
    try:
        template = env.from_string(source)
        return template.render(**context)
    except TemplateError as exc:  # Jinja2-Fehler (Syntax, Undefined, Sandbox)
        raise AssTemplateError(f"template error: {exc}") from exc


def render_preset_file(filename: str, context: Dict[str, Any]) -> str:
    """Rendert eine Vorlage aus dem Preset-Verzeichnis (Dateiname, kein Pfad)."""
    if "/" in filename or "\\" in filename or ".." in filename:
        raise AssTemplateError(f"invalid preset file: {filename!r}")
    path = PRESET_DIR / filename
    if not path.is_file():
        raise AssTemplateError(f"preset file not found: {filename}")
    return render_source(path.read_text(encoding="utf-8"), context, PRESET_DIR)
