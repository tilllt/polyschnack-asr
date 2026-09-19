"""Preset-Katalog + Parameter-Schema für den ASS-Export (Change 193).

Ein Preset besteht aus zwei Dateien in ``ass_export/presets/``:

* ``<name>.ass.j2`` — Jinja2-Vorlage, rendert das komplette ASS-Dokument.
  Sie importiert ``_base.ass.j2`` (Kopf/Stile) und füllt den Event-Block.
* ``<name>.yaml`` — Anzeigename, Beschreibung (de/en/pt), Parameter-Defaults
  und die Zuordnung, welche Parameter-Farbe in welche ASS-Stilfarbe fliesst.

Die Vorlage sieht ausschliesslich: ``meta``, ``params``, ``styles``,
``lines``, ``steps``, ``counts`` — keine Python-Objekte, keine Funktionen
ausser den Filtern (``ass_escape``, ``bgr``, ``ass_color``, ``cs``, ``tc``).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from . import textfit
from .template_engine import PRESET_DIR, parse_color

#: Anzeige-Position → ASS-Alignment (Numpad-Layout: 1-3 unten, 4-6 mitte, 7-9 oben).
POSITION_ALIGNMENT = {"bottom": 2, "center": 5, "top": 8}

#: Erlaubte Zeichen im Dateinamen eines Presets.
_NAME_RE = re.compile(r"^[a-z0-9_-]{1,40}$")


class PresetNotFound(Exception):
    """Angefragtes Preset existiert nicht (→ 404)."""


class ParamError(Exception):
    """Ungültige Export-Parameter (→ 400, mit Feld und Begründung)."""


# ---------------------------------------------------------------------------
# Parameter-Schema
# ---------------------------------------------------------------------------

#: Globale Parameter-Definitionen. Presets überschreiben nur die Defaults.
#: ``type`` steuert die UI-Eingabe (Zahl/Regler, Farbe, Schalter, Auswahl).
PARAM_SPECS: Dict[str, Dict[str, Any]] = {
    "font_name": {"type": "str", "default": "Arial", "max_len": 64},
    "font_size": {"type": "int", "default": 48, "min": 12, "max": 300},
    "bold": {"type": "bool", "default": True},
    "uppercase": {"type": "bool", "default": False},
    "text_color": {"type": "color", "default": "#FFFFFF"},
    "accent_color": {"type": "color", "default": "#FFD400"},
    "dim_color": {"type": "color", "default": "#8A8F98"},
    "outline_color": {"type": "color", "default": "#000000"},
    "outline_width": {"type": "int", "default": 3, "min": 0, "max": 12},
    "shadow": {"type": "int", "default": 1, "min": 0, "max": 12},
    "box": {"type": "bool", "default": False},
    "position": {"type": "enum", "default": "bottom",
                 "values": ["bottom", "center", "top"]},
    "margin_v": {"type": "int", "default": 60, "min": 0, "max": 900},
    "play_res_x": {"type": "int", "default": 1920, "min": 128, "max": 7680},
    "play_res_y": {"type": "int", "default": 1080, "min": 128, "max": 7680},
    "words_per_line": {"type": "int", "default": 4, "min": 1, "max": 12},
    # Change 201: Schriftgröße an die Bildschirmbreite anpassen. "balanced"
    # balanciert die Zeilen nach Breite und berechnet daraus EINE Größe, die
    # die breiteste Zeile ausfüllt. "per_line" (Change 202) lässt die Zeilen
    # bei der eingestellten Wortzahl und berechnet die Größe JE ZEILE aus
    # Breite und Höhe — die Größe springt also von Anzeige zu Anzeige.
    "fit_mode": {"type": "enum", "default": "off",
                 "values": ["off", "balanced", "per_line"]},
    # Change 202: Sicherheitsrand (Safe Title) in Prozent je Seite. Waagerecht
    # als MarginL/MarginR des ASS-Stils, senkrecht als Grenze für die Höhe der
    # Schrift. 0 = Rand wie vor Change 202 (40 px).
    "safe_margin_pct": {"type": "int", "default": 5, "min": 0, "max": 20},
    "sentence_breaks": {"type": "bool", "default": True},
    "lead_ms": {"type": "int", "default": 0, "min": 0, "max": 1500},
    "tail_ms": {"type": "int", "default": 300, "min": 0, "max": 2000},
    "fade_ms": {"type": "int", "default": 0, "min": 0, "max": 1500},
    "pop_scale": {"type": "int", "default": 130, "min": 100, "max": 250},
    "pop_ms": {"type": "int", "default": 200, "min": 40, "max": 800},
    "active_scale": {"type": "int", "default": 112, "min": 100, "max": 250},
    "hide_upcoming": {"type": "bool", "default": False},
}

#: Farb-Parameter, die die Vorlage per ``| bgr`` einsetzt (UI-Hinweis).
COLOR_PARAMS = tuple(k for k, v in PARAM_SPECS.items() if v["type"] == "color")

#: Parameter, die der GENERATOR selbst auswertet (Zeilenbildung, Event-Zeiten,
#: Groß-/Kleinschreibung) — sie stehen in keiner Vorlage, wirken aber trotzdem.
#: Quelle: ``ass_generator.build_lines`` / ``apply_timing`` / ``_line_context``.
LAYOUT_PARAM_KEYS = (
    "words_per_line",
    "fit_mode",
    "safe_margin_pct",
    "sentence_breaks",
    "lead_ms",
    "tail_ms",
    "uppercase",
)

#: Parameter, die der Stil-Bauer bzw. der Dokumentkopf liest
#: (``ass_generator._styles`` und ``meta``). Reine Farbrollen (Primär/Sekundär)
#: kommen zusätzlich aus dem ``style``-Block des Presets.
STYLE_PARAM_KEYS = (
    "font_name",
    "font_size",
    "bold",
    "outline_color",
    "outline_width",
    "shadow",
    "box",
    "position",
    "margin_v",
    "play_res_x",
    "play_res_y",
)


def _coerce(key: str, raw: Any) -> Any:
    """Wert gegen das Schema prüfen und in den Ziel-Typ wandeln."""
    spec = PARAM_SPECS[key]
    kind = spec["type"]
    if kind == "bool":
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str) and raw.strip().lower() in {"true", "1", "yes", "on"}:
            return True
        if isinstance(raw, str) and raw.strip().lower() in {"false", "0", "no", "off"}:
            return False
        raise ParamError(f"{key}: erwartet true/false, bekam {raw!r}")
    if kind == "int":
        try:
            val = int(raw)
        except (TypeError, ValueError):
            raise ParamError(f"{key}: erwartet ganze Zahl, bekam {raw!r}")
        lo, hi = spec.get("min"), spec.get("max")
        if lo is not None and val < lo:
            raise ParamError(f"{key}: {val} ist kleiner als {lo}")
        if hi is not None and val > hi:
            raise ParamError(f"{key}: {val} ist grösser als {hi}")
        return val
    if kind == "color":
        try:
            parse_color(raw)
        except ValueError as exc:
            raise ParamError(f"{key}: {exc}") from exc
        return str(raw).strip() if str(raw).strip().startswith("#") else "#" + str(raw).strip()
    if kind == "enum":
        val = str(raw).strip()
        if val not in spec["values"]:
            raise ParamError(
                f"{key}: {val!r} nicht erlaubt (erlaubt: {', '.join(spec['values'])})"
            )
        return val
    # str
    val = str(raw).strip()
    if not val:
        raise ParamError(f"{key}: darf nicht leer sein")
    if len(val) > spec.get("max_len", 128):
        raise ParamError(f"{key}: zu lang (max {spec['max_len']} Zeichen)")
    # Komma würde die Style-Zeile (CSV-artig) zerreissen.
    return val.replace(",", " ")


def validate_overrides(overrides: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Prüft/konvertiert User-Overrides; unbekannte Keys sind ein Fehler."""
    out: Dict[str, Any] = {}
    for key, raw in (overrides or {}).items():
        if key not in PARAM_SPECS:
            raise ParamError(f"unbekannter Parameter: {key}")
        out[key] = _coerce(key, raw)
    return out


# ---------------------------------------------------------------------------
# Preset
# ---------------------------------------------------------------------------


@dataclass
class Preset:
    """Ein Caption-Preset (Vorlage + Defaults)."""

    name: str
    title: str
    description: str
    description_en: str = ""
    description_pt: str = ""
    template_file: str = ""
    defaults: Dict[str, Any] = field(default_factory=dict)
    style_map: Dict[str, str] = field(default_factory=dict)

    def effective_defaults(self) -> Dict[str, Any]:
        """Alle Parameter: globale Defaults, überschrieben von den Preset-Defaults."""
        merged = {k: v["default"] for k, v in PARAM_SPECS.items()}
        merged.update(validate_overrides(self.defaults))
        return merged

    def resolve(self, overrides: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Default-Parameter + geprüfte Overrides."""
        params = self.effective_defaults()
        params.update(validate_overrides(overrides))
        return params

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "description_en": self.description_en,
            "description_pt": self.description_pt,
            "parameters": self.effective_defaults(),
            # Nur die Parameter, die die Vorlage wirklich benutzt — die UI
            # baut daraus ihre Regler (keine wirkungslosen Bedienelemente).
            "used_params": used_params(self),
        }


def _read_yaml(path: Path) -> Dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise PresetNotFound(f"preset '{path.stem}' unreadable: {exc}") from exc
    if not isinstance(data, dict):
        raise PresetNotFound(f"preset '{path.stem}' must be a YAML mapping")
    return data


@lru_cache(maxsize=64)
def load_preset(name: str) -> Preset:
    """Preset laden (YAML + Vorlagen-Datei); unbekannt → :class:`PresetNotFound`."""
    if not _NAME_RE.match(name or ""):
        raise PresetNotFound(name)
    yaml_path = PRESET_DIR / f"{name}.yaml"
    if not yaml_path.is_file():
        raise PresetNotFound(name)
    data = _read_yaml(yaml_path)
    template_file = str(data.get("template") or f"{name}.ass.j2")
    if not (PRESET_DIR / template_file).is_file():
        raise PresetNotFound(f"preset '{name}': template '{template_file}' fehlt")
    return Preset(
        name=name,
        title=str(data.get("name") or name.capitalize()),
        description=str(data.get("description") or ""),
        description_en=str(data.get("description_en") or ""),
        description_pt=str(data.get("description_pt") or ""),
        template_file=template_file,
        defaults=dict(data.get("defaults") or {}),
        style_map=dict(data.get("style") or {}),
    )


def list_preset_names() -> List[str]:
    """Namen aller mitgelieferten Presets (ohne ``_base``/YAML-Dateien)."""
    names = []
    for path in sorted(PRESET_DIR.glob("*.yaml")):
        if not path.stem.startswith("_"):
            names.append(path.stem)
    return names


#: Findet ``params.<key>``-Verweise im Vorlagen-Text.
_PARAM_REF_RE = re.compile(r"params\.([a-z_][a-z0-9_]*)")


def template_param_refs(preset: "Preset") -> List[str]:
    """Alle ``params.<key>``-Verweise der Vorlage (roh, ungefiltert).

    Grundlage für :func:`used_params` und für den Test, der Tippfehler in
    Vorlagen findet (ein Verweis auf einen nicht existierenden Parameter
    würde sonst erst zur Laufzeit als StrictUndefined-Fehler auftauchen).
    """
    try:
        text = (PRESET_DIR / preset.template_file).read_text(encoding="utf-8")
    except OSError:
        return []
    return sorted(set(_PARAM_REF_RE.findall(text)))


def used_params(preset: "Preset") -> List[str]:
    """Parameter, die DIESE Vorlage/dieses Preset tatsächlich benutzt.

    Drei Quellen, weil ein Parameter auf drei Wegen wirken kann:

    1. **Vorlage** — ``params.<key>`` im ``.ass.j2`` (z. B. ``pop_scale``).
    2. **Generator** — Zeilenbildung/Event-Zeiten (``LAYOUT_PARAM_KEYS``).
    3. **Stil-Bauer** — Schrift/Kontur/Position (``STYLE_PARAM_KEYS``) plus die
       Farbrollen aus dem ``style``-Block des Presets (Primär = gesprochen/aktiv,
       Sekundär = Rest bzw. „noch nicht gesungen" bei Karaoke).

    Die UI blendet alles aus, was hier nicht steht — sonst stünden Regler im
    Dialog, die nichts bewirken (z. B. „Farbe des aktiven Wortes" beim
    klassischen Preset, das nur eine Schriftfarbe kennt). Dass die Liste
    stimmt, prüft ``test_used_params_match_the_rendered_output`` empirisch:
    jeder gelistete Parameter muss die Ausgabe verändern, jeder nicht
    gelistete sie in Ruhe lassen.
    """
    keys = set(template_param_refs(preset)) | set(LAYOUT_PARAM_KEYS) | set(STYLE_PARAM_KEYS)
    # fit_mode wirkt nur, wenn Text wirklich gemessen werden kann. Fehlt die
    # Fähigkeit (Image ohne Schrift/Pillow), wird der Regler NICHT gelistet —
    # sonst stünde ein wirkungsloser Regler im Dialog.
    # Quelle: test_used_params_match_the_rendered_output prüft genau das.
    if "fit_mode" in keys and not textfit.kann_messen():
        keys.discard("fit_mode")
    for role in ("primary", "secondary"):
        source = preset.style_map.get(role)
        if source:
            keys.add(source)
    return sorted(key for key in keys if key in PARAM_SPECS)


def list_presets(include_internal: bool = False) -> List[Preset]:
    """Alle Presets laden; kaputte Presets werden gemeldet, nicht verschluckt."""
    out: List[Preset] = []
    for name in list_preset_names():
        try:
            out.append(load_preset(name))
        except PresetNotFound:
            if include_internal:
                raise
            continue
    return out


def parameter_specs() -> Dict[str, Dict[str, Any]]:
    """Schema für die UI (Typ, Grenzen, Auswahlwerte) — ohne Defaults."""
    return {
        k: {kk: vv for kk, vv in v.items() if kk != "default"}
        for k, v in PARAM_SPECS.items()
    }
