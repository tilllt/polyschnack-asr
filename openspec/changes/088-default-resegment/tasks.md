# Tasks — Change 088: Default-Re-Segmentierung

## Umsetzung
- [x] OpenSpec-Change dokumentiert (proposal/design/tasks)
- [x] RecordingCard: `segMaxDuration` Default null → 25 (Z. 319), bei
      segments_manual startet das Feld leer (kein irreführender Default)
- [x] Kommentar aktualisiert (Default erklärt)
- [x] Export-Link hängt `max_duration_s` an (Preview = Export-Aufteilung)
- [x] „× ≤ X s"-Info nur bei aktiver Re-Segmentierung (kein Fake)

## Verifikation
- [x] Frontend-Suite grün (290 Tests) + `tsc --noEmit` + `vite build`
- [x] Browser-Verifikation (Live-Daten): Anzeige zeigt **136 × ≤ 25 s**
      (statt 48 Riesen-Segmente); Zeilen 25 Wörter/134 px statt 287/3000 px;
      Expand 48,2 FPS, Scroll 49 FPS (CPU 4×, Mobile 390×844)

## Abschluss
- [x] Commit + Push + CI-Check

## Design-Notizen
- `deriveSegments(segments, segMaxDuration, !!r.segments_manual)` —
  segments_manual = true → manuelle Grenzen haben Vorrang (kein
  Resegment, bestehende Semantik).
- Feld leer (User löscht Zahl) → null → Original-Segmente (bisheriges
  Verhalten bleibt als Opt-out erhalten).
- Frontend-resegment.ts Bucket-Logik = Backend resegment_by_duration
  (service.py Z. 1843) — 1:1 identisch, keine neue Logik nötig.
