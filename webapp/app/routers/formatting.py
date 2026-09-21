"""Change 228 — KI-Formatierung: Vorgaben für die Oberfläche.

Ohne Anmeldung erreichbar: die Liste enthält nur Kennungen und Erklärtexte,
keine Prompts und keine Geheimnisse. Die Auswahl selbst läuft über die
Lauf-Felder (``enable_formatting``, ``format_preset`` …).
"""
from __future__ import annotations

from fastapi import APIRouter

from ..formatting import DEFAULT_PRESET, preset_list

router = APIRouter(prefix="/api/formatting")


@router.get("/presets")
def list_format_presets() -> dict:
    """Eingebaute Vorgaben der KI-Formatierung (Reihenfolge = Anzeige)."""
    return {"presets": preset_list(), "default": DEFAULT_PRESET}
