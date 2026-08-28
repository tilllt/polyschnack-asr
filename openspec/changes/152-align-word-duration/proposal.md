# Change 152 — Wort-Dauern aus Folgewort ableiten (Aligner end=start)

**Status:** Proposed (Umsetzung läuft)

## Problem (User-Befund 2026-08-28)

Die Länge der alignierten Wörter ist immer 0 oder max 2 — das Wort wird
auf der gezoomten Timeline nie markiert. Ursache: Der Forced-Aligner
liefert für die meisten Wörter `end=start` (Dauer 0) oder unplausibel
kurze Werte; `apply_aligned_words` und die Sammel-Schleife übernehmen
`end` unverändert.

## Lösung

In `apply_aligned_words` (zentrale Zuordnung, Change 078): Wörter mit
Dauer ≤ 50 ms bekommen ihre Endzeit aus dem Start des **Folgeworts**
(die Lücke wird dem ersten Wort zugeschlagen); das letzte Wort der
Liste erhält eine Mindestdauer von 100 ms. Plausible Dauern (> 50 ms)
bleiben unberührt.

Kein Einheiten-Bug (die Startpositionen stimmen) — nur fehlende
Endzeiten vom Aligner.
