# Change 088 — Default-Re-Segmentierung der Transkriptions-Anzeige

**Status:** proposed → in Arbeit (2026-08-22)
**Problem:** ASR liefert chunk-bedingte Riesen-Segmente (95-min-Aufnahme =
48 Segmente, Ø 119 s, max 287 Wörter/Zeile). Die Segmentlängen-Wahl
(Feature 2026-08-15) existiert, hat aber KEINEN Default — ohne aktive
User-Eingabe zeigt die Anzeige die rohen Riesen-Blöcke (UX-Problem auf
Mobile, siehe Change 087).

## Lösung (User-OK 2026-08-22, Variante A — Anzeige-Default)

1. `segMaxDuration`-State in RecordingCard: Default **25 s** statt null
   (RecordingCard.tsx Z. 316). Jede Aufnahme zeigt automatisch
   re-segmentierte Segmente ≤ 25 s (Sprecherwechsel trennt weiterhin).
2. Kein Daten-Eingriff: gespeicherte Segmente bleiben unverändert;
   `segments_manual == true` (gezogene Grenzen) hat weiterhin Vorrang
   (deriveSegments, Z. 617).
3. User kann das Feld leeren → Original-Segmente (bisheriges Verhalten).
4. Export (SRT/VTT): nutzt denselben Wert (bestehende Übergabe) — Default
   greift damit automatisch auch beim Export.

## Erwartete Wirkung

- 95-min-Aufnahme: 48 Riesen-Zeilen → ~228 Zeilen ≤ 25 s — handliche
  Blöcke auf Mobile, präzisere Navigation (Suche/Sprung), bessere
  Zusammenarbeit mit der Virtualisierung (087) (kleine, schnell messbare
  Zeilen).
- Alt-Aufnahmen profitieren sofort (reine Anzeige-Transformation).
