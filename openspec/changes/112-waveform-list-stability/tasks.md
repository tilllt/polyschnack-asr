# Tasks — Change 112

## Phase 1 — Befund & Doku
- [x] Proposal (Befund Android-Chrome: Blinken + Aw-Snap, zwei Mechanismen)

## Phase 2 — Code (Frontend)
- [x] **Punkt 1 (Crash-Fix):** `LARGE_FILE_THRESHOLD_S` 7200 → 1800 (30 min) —
      alle Aufnahmen > 30 min nutzen das MediaElement-Backend (Streaming per
      Range-Request statt WebAudio-Voll-Dekode). 95-min-Datei: ~180 MB PCM
      pro Karte → ~0 RAM. Kurze Dateien bleiben WebAudio (Präzision).
- [x] **Punkt 2 (Blink-Fix):** Load-Effekt hängt jetzt an einer
      `peaksSignature` (length:first:last) statt an der peaks-Referenz —
      Polls drehen die Referenz bei gleichem Inhalt (kein Reload mehr),
      echte Peaks-Nachlieferungen (Change 059) ändern die Signatur (Reload
      bleibt). resolveAudioUrl war bereits deterministisch stabil.

## Phase 3 — Tests (Frontend)
- [x] Test: Poll-Referenz-Drehung (gleicher Inhalt) → KEIN neuer Load
- [x] Test: echter Inhalt-Wechsel → Re-Init bleibt (Change 059-Regression)
- [x] resolveBackend-Tests an 30-min-Schwelle angepasst (95-min → MediaElement)
- [ ] Bestehende Frontend-Suite bleibt grün (läuft gerade)

## Phase 4 — CI & Deploy
- [ ] tsc 0 Fehler, Frontend-Suite grün
- [ ] Commit + Push → CI (test-frontend, test-webapp)
- [ ] Deploy-Anleitung: `selfupdate && update` (mit 106-Fix zusammen)
- [ ] Live-Verifikation: Startseite auf Android-Chrome mit 95-min-Datei —
      Kurve stabil, kein Tab-Crash; Play funktioniert

## Optionale Folge (nicht Teil von 112)
- [ ] Punkt 3: Preview für lange Dateien auf 32 kbps mono (Backend, 1 Zeile) —
      halbiert Decode-Last zusätzlich
