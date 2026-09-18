"""Zeilen ausbalancieren und die Schriftgroesse berechnen (Change 201).

Reine Rechnung auf Breiten — keine Kenntnis von ASS oder vom Aufnahme-Modell,
damit es einzeln pruefbar bleibt.

Zwei Aufgaben:

1. :func:`balanced_split` — Wörter so auf Zeilen verteilen, dass die Zeilen
   **moeglichst gleich breit** sind und keine Zeile die verfuegbare Breite
   ueberschreitet. Die Zahl der Zeilen kommt aus der **Breite** (wie oft passt
   die Gesamtbreite in die Zeile), nicht aus einer festen Wortzahl;
   ``max_words`` bleibt als Obergrenze je Zeile erhalten.
2. :func:`font_size_for` — EINE Groesse fuer den ganzen Export, so dass die
   breiteste Zeile die verfuegbare Breite ausfuellt, begrenzt auf einen
   sinnvollen Bereich um die eingestellte Groesse. Eine Groesse je Zeile waere
   bei unterschiedlich langen Woertern sprungartig (mal riesig, mal klein).
"""

from __future__ import annotations

import math
from typing import List, Sequence, Tuple

#: Grenzen, um die die eingestellte Schriftgroesse verschoben werden darf.
MIN_FACTOR = 0.5
MAX_FACTOR = 3.0


def _min_lines(widths: Sequence[float], start: int, max_words: int,
               available: float) -> int:
    """Wie viele Zeilen braucht der Rest mindestens? (gierig, harte Grenzen)

    Ein einzelnes zu breites Wort zählt als eigene Zeile (es wird nicht
    zerschnitten) — der Überlauf wird später gemeldet.
    """
    i, count = start, 0
    while i < len(widths):
        breite, k = 0.0, 0
        while i + k < len(widths) and k < max_words:
            if k > 0 and breite + widths[i + k] > available:
                break
            breite += widths[i + k]
            k += 1
        i += max(1, k)
        count += 1
    return count


def balanced_split(widths: Sequence[float], max_words: int,
                   available: float = 0.0) -> List[List[int]]:
    """Wort-Indizes auf Zeilen verteilen — ausbalanciert nach Breite.

    * ``max_words`` ist eine Obergrenze je Zeile (nie mehr Wörter).
    * *available* ist die verfügbare Breite in PlayRes-Pixeln. Ist sie
      angegeben, richtet sich die Zahl der Zeilen nach der Breite und **keine
      Zeile wird breiter als erlaubt** (außer ein einzelnes Wort ist selbst zu
      breit — dann steht es allein, und der Aufrufer meldet es).
    * Ohne *available* wird wie früher nach Wortzahl geteilt.
    * Jede Zeile bekommt mindestens ein Wort; leere Zeilen entstehen nie.
    """
    n = len(widths)
    if n == 0:
        return []
    max_words = max(1, int(max_words))

    if available <= 0:
        return [list(range(i, min(i + max_words, n))) for i in range(0, n, max_words)]

    # Zielbreite aus der kleinstmöglichen Zeilenzahl: dadurch werden die Zeilen
    # gleichmäßig, ohne die harte Grenze zu verletzen.
    zeilen = _min_lines(widths, 0, max_words, available)
    ziel = sum(widths) / zeilen

    out: List[List[int]] = []
    i = 0
    while i < n:
        rest_zeilen = _min_lines(widths, i, max_words, available)
        if rest_zeilen <= 1:
            out.append(list(range(i, n)))
            break
        current: List[int] = []
        breite = 0.0
        while len(current) < max_words and i + len(current) < n:
            j = i + len(current)
            neu = breite + widths[j]
            if current and neu > available:
                break
            if current and neu > ziel:
                # Früh aufhören (ausbalancieren) — aber nur, wenn der Rest mit
                # den verbleibenden Zeilen noch hineinpasst. Sonst liefe der
                # Schwanz über den Rand.
                if _min_lines(widths, j, max_words, available) <= rest_zeilen - 1:
                    break
            current.append(j)
            breite = neu
        if not current:  # Sicherheitsnetz: wenigstens ein Wort, nie leer
            current.append(i)
        out.append(current)
        i += len(current)
    return out


def font_size_for(available_px: float, line_widths: Sequence[float],
                  base_size: float, min_factor: float = MIN_FACTOR,
                  max_factor: float = MAX_FACTOR) -> Tuple[int, int]:
    """Eine Schriftgroesse, die die breiteste Zeile auf *available_px* bringt.

    *line_widths* sind Breiten bei :data:`textfit.REFERENCE_SIZE`.

    Die Groesse wird **abgerundet**: aufgerundet wuerde die Zeile um bis zu
    einen Pixel je Einheit ueber den Rand laufen (gemessen: ideal 34,5 px,
    gerundet 35 → 1859 px bei 1833 px verfuegbar).

    Rueckgabe: ``(groesse, ueberlauf)`` — *ueberlauf* ist die Zahl der Zeilen,
    die auch bei der Untergrenze zu breit bleiben. Sie werden gemeldet statt
    still ueber den Rand geschrieben.
    """
    base = float(base_size)
    if not line_widths or available_px <= 0:
        return max(1, int(base)), 0

    breiteste = max(line_widths)
    if breiteste <= 0:
        return max(1, int(base)), 0

    ideal = available_px / breiteste * 100.0
    groesse = max(base * min_factor, min(base * max_factor, ideal))
    groesse = max(1, math.floor(groesse))

    ueberlauf = sum(1 for w in line_widths if w * groesse / 100.0 > available_px + 0.5)
    return groesse, ueberlauf
