# Tasks — Change 088: Default-Re-Segmentierung

## Umsetzung
- [x] OpenSpec-Change dokumentiert (proposal/design/tasks)
- [x] RecordingCard: `segMaxDuration` Default 25 (auch bei segments_manual)
- [x] resegment.ts: OP-Funktionen (moveBoundary/insert/delete/split)
      markieren betroffene Segmente mit `_manual: true`
- [x] deriveSegments/resegmentByDuration: Hybrid — `_manual`-Segmente
      bleiben exakt, unmarkierte werden nach Ziel-Länge geteilt
- [x] Backend service.resegment_by_duration: `_manual`-Segmente ebenso
      durchreichen (Export = Anzeige); Segmente ohne Wort-Timestamps
      bleiben Original
- [x] Export-Link hängt `max_duration_s` an (Preview = Export-Aufteilung)
- [x] Kommentare aktualisiert (resegment.ts, models.py, segments.py-Semantik)

## Verifikation
- [x] Frontend-Suite grün (290 Tests) + `tsc --noEmit`; resegment-Tests
      auf Hybrid umgestellt + neue _manual-Fälle
- [x] Backend test_resegment.py grün (12 Tests, inkl. 2 neue _manual)
- [x] Browser-Verifikation (Live-Daten, segments_manual=true):
      ohne Flag 136 × ≤ 25 s; mit markiertem 400-s-Segment (287 Wörter)
      → 120 × ≤ 25 s (Segment bleibt ganz, Rest teilt sich)

## Abschluss
- [x] Commit + Push + CI-Check

## Design-Notizen
- `_manual`-Flag wird von PUT /segments 1:1 persistiert (keine
  Feld-Whitelist in segments.py; tiefe Kopie).
- Bestandsaufnahmen ohne Flags: alle Riesen teilen sich (gewünscht).
- In-place-Mutation von JSON-Spalten wird von SQLAlchemy nicht erkannt —
  Änderungen nur via Listen-Zuweisung (Test-Setup-Falle, Dokumentation
  für künftige Seeds).
