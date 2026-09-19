# Change 211 — 80-ms-Untergrenze auf den Fallback begrenzen sich

**Nutzer-Entscheidung 19.09.2026 (wörtlich):**

> „In der transkriptionsansicht ist es egal wie klein die Wörter sind, wir können sie dort nicht
> bearbeiten."

Damit ist der ursprüngliche Zweck der Untergrenze (sichtbares Rechteck in der Timeline der
Transkriptionsansicht) entfallen. Bearbeitet wird ausschließlich im Timing-Tab, und dort ist der Zoom
wortzentriert.

## Befund (Produktions-DB, 19.09.2026)

- `recording.segments` (Editor-Kopie): 165 506 Wörter — **ohne Zeit: 0**, Dauer 0: 228, < 80 ms: 15 828
- `transcriptionresult` (Ergebnisse): 244 710 Wörter — **ohne Zeit: 0**, Dauer 0: 352, < 80 ms: 14 561
- **21 686 Wörter sitzen exakt auf 80 ms** (±0,5 ms) — häufigste: `die` 451, `ich` 361, `und` 306,
  `das` 304, `der` 252, `in` 224, `ist` 211. Eine Sprechverteilung hat dort keinen Zacken: das sind
  künstlich verlängerte Wörter.
- Ursache im Code: `enforce_min_word_durations` (Change 190) verlängert **jedes** Wort unter 80 ms auf
  `start + 80 ms` und unterscheidet nicht zwischen „keine echte Zeit" (Fallback) und „echte, kurze
  Messung". Aufruf direkt nach dem Align (`service.py:1448`) und im Reconcile-Pfad
  (`segments.py:301-302`).
- Zoom im Timing-Tab ist **nicht** das Problem: `timingPps` zielt auf 30 % der Breite pro Wort
  (bei 1200 px ≈ 360 px für ein 20-ms-Wort), Deckel `MAX_TIMING_PPS = 48000`; die einzige Grenze ist
  die maximale Elementbreite des Browsers (`2^25 / Dauer`, bei 4,4 h noch ≈ 46 px).
- Eine Mindestbreite in der *Anzeige* wurde verworfen (Nutzer-Einwand, berechtigt): sie würde Zeit
  beanspruchen, die den Nachbarn gehört, und deren Marker überlappen.

## Änderung

1. **Untergrenze nur noch für Wörter ohne echte Zeit** (Fallback-Interpolation, Change 168/190).
   Echte Werte von Aligner/ASR/manueller Bearbeitung bleiben unverändert — auch wenn sie 20 ms
   betragen.
2. Die drei bestehenden Stufen bleiben in dieser Reihenfolge: fehlende Werte interpolieren (168),
   `end == start` auflösen (152), und erst danach die Untergrenze **nur auf die interpolierten**
   Wörter anwenden (190, eingeschränkt).
3. Keine Anzeige-Mindestbreite; kein Aufblasen von Zeiten.
4. Meldung im Frontend korrigieren: „Wort ohne eigene Zeit" ist nachweislich ein Zustand, den es
   nicht gibt (0 von 165 506). Ersetzt durch eine ehrliche Beschreibung des tatsächlichen Falls.
5. **Kein automatisches Zurückschreiben** der 21 686 bereits verlängerten Wörter: ob ein Wert echt
   oder künstlich ist, lässt sich in der Editor-Kopie nicht sicher unterscheiden (die echten
   Endwerte wurden überschrieben). Ein Massen-Restore könnte manuelle Zeiten zerstören. Ein
   Rückweg wird nur dort angeboten, wo die Rohwerte belegt vorliegen (Align-Cache, 44 Dateien) —
   und nur auf ausdrückliche Anweisung.

## Nachweis

- Tests: Untergrenze greift nur beim Fallback (echte 20-ms-Wörter bleiben 20 ms); keine Untergrenze
  bei echten Werten; Fallback-Wörter weiterhin ≥ 80 ms.
- Gegenprobe an der Datei des Nutzers (`4aed45f6…`): 19 Wörter, kürzestes 160 ms, Median 560 ms — muss
  nach der Änderung identisch bleiben.

## Offen (eigener Fund, nicht Teil dieses Changes)

- Einträge wie ein `das` mit 90 480 ms Dauer — eigener Datenfehler, separat zu untersuchen.
- Editor-Kopie und Ergebnis weichen für dieselbe Aufnahme voneinander ab (19 Wörter, kürzestes 101 ms
  vs. 160 ms) — Quelle der Abweichung klären.
