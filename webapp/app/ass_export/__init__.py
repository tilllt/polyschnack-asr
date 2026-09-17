"""ASS-Caption-Export (Change 193).

Öffentliche API:

* :func:`generate_ass` — Recording → ``.ass``-Inhalt (Preset + Parameter).
* :func:`list_presets` / :func:`load_preset` — Preset-Katalog.
* :class:`NoWordTimestamps` — Recording ohne brauchbare Wortzeiten (→ 409).
"""
from __future__ import annotations

from .ass_generator import (  # noqa: F401
    AssResult,
    NoWordTimestamps,
    build_lines,
    extract_words,
    generate_ass,
)
from .presets import (  # noqa: F401
    ParamError,
    Preset,
    PresetNotFound,
    list_preset_names,
    list_presets,
    load_preset,
    parameter_specs,
)
from .template_engine import AssTemplateError, ass_escape  # noqa: F401

__all__ = [
    "AssResult",
    "AssTemplateError",
    "NoWordTimestamps",
    "ParamError",
    "Preset",
    "PresetNotFound",
    "ass_escape",
    "build_lines",
    "extract_words",
    "generate_ass",
    "list_preset_names",
    "list_presets",
    "load_preset",
    "parameter_specs",
]
