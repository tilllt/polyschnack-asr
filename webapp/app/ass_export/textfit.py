"""Textbreite mit der echten Schrift messen (Change 201).

Warum gemessen und nicht geschätzt: der Modus ``fit_mode=balanced`` soll die
Schrift so gross machen, dass die Zeile die verfuegbare Breite ausfuellt. Eine
Schaetzung (z. B. Zeichenzahl x mittlere Breite) liegt bei Namen, Zahlen,
Grossschreibung und fetter Schrift daneben — die Zeile liefe dann ueber den
Rand oder liesse Platz liegen. Gemessen wird deshalb mit derselben Schrift, die
der Renderer benutzt: ``fc-match`` loest den Namen auf (Arial -> Liberation
Sans, genau wie im Render-Container), gerastert wird mit FreeType ueber Pillow.

Alle Breiten sind in **PlayRes-Pixeln** (also in derselben Einheit wie
``font_size`` im ASS-Stil). Eine Referenzgroesse dient zum Vergleichen: Breiten
skalieren linear mit der Schriftgroesse.
"""

from __future__ import annotations

import shutil
import subprocess
from functools import lru_cache
from typing import Any, Dict, Optional

try:  # Pillow ist die Messgrundlage; fehlt es, wird das gemeldet (nicht verschluckt)
    from PIL import ImageFont
except Exception:  # pragma: no cover - haengt vom Image ab
    ImageFont = None  # type: ignore

#: Groesse, bei der gemessen wird. Beliebige Zahl, aber fest — Vergleiche
#: laufen ueber das Verhaeltnis.
REFERENCE_SIZE = 100.0

#: Zuschlag, den die Kontur nach aussen braucht (halbe Kontur je Seite) und der
#: Schatten nach rechts. Wird von der verfuegbaren Breite abgezogen.
def _extra_px(params: Dict[str, Any]) -> float:
    return 2.0 * float(params.get("outline_width", 0) or 0) + float(params.get("shadow", 0) or 0)


@lru_cache(maxsize=32)
def font_path(font_name: str, bold: bool = False) -> Optional[str]:
    """Schriftdatei zu einem Namen — ueber fontconfig, wie der Renderer.

    Gibt ``None`` zurueck, wenn fontconfig fehlt oder nichts findet; der
    Aufrufer meldet das dann als ``fit_unavailable`` statt still zu raten.
    """
    if not shutil.which("fc-match"):
        return None
    muster = f"{font_name}:bold" if bold else font_name
    try:
        res = subprocess.run(
            ["fc-match", "-f", "%{file}", muster],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    pfad = (res.stdout or "").strip()
    return pfad or None


@lru_cache(maxsize=4096)
def _width(text: str, path: str, size: int) -> float:
    if ImageFont is None:  # pragma: no cover - Aufrufer prueft vorher
        raise RuntimeError("Pillow fehlt")
    font = ImageFont.truetype(path, int(size))
    return float(font.getlength(text))


@lru_cache(maxsize=1)
def kann_messen() -> bool:
    """Ist die Schriftmessung in dieser Umgebung überhaupt möglich?

    Wird gefragt, bevor ein Regler angeboten wird: ein Regler ohne Wirkung im
    Dialog ist schlimmer als kein Regler (dieselbe Regel wie beim Render-Dienst,
    der Formate ohne Encoder nicht anbietet).
    """
    fehlt: list = []
    if not available(fehlt):
        return False
    return font_path("Arial", True) is not None


def available(missing: list) -> bool:
    """Kann gemessen werden? Sammelt den Grund in *missing* (fuer die Meldung)."""
    if ImageFont is None:
        missing.append("pillow")
        return False
    if not shutil.which("fc-match"):
        missing.append("fontconfig")
        return False
    return True


def text_width(text: str, *, font_name: str, bold: bool = False,
               size: float = REFERENCE_SIZE) -> Optional[float]:
    """Breite von *text* in PlayRes-Pixeln — ``None``, wenn nicht messbar."""
    if not text:
        return 0.0
    if ImageFont is None:
        return None
    path = font_path(font_name, bold)
    if not path:
        return None
    try:
        return _width(text, path, round(REFERENCE_SIZE)) * (size / REFERENCE_SIZE)
    except Exception:
        return None


def available_width(params: Dict[str, Any]) -> float:
    """Breite, die eine Zeile hoechstens belegen darf (PlayRes-Pixel).

    ``play_res_x`` minus beider Stil-Raender minus Kontur/Schatten-Zuschlag.
    """
    play_res_x = float(params.get("play_res_x", 1920) or 1920)
    margin_l = float(params.get("margin_l", 40) or 0)
    margin_r = float(params.get("margin_r", 40) or 0)
    return max(1.0, play_res_x - margin_l - margin_r - _extra_px(params))
