# Change 144 — Tasks (Segment löschen „empty text")

## 1. Frontend

- [x] `RecordingCard.tsx` `persistSegmentList`: leere Segmente
      (`text.trim() === ""`) vor dem PUT entfernen; Anzeige + Cache mit
      dem bereinigten Array aktualisieren.

## 2. Verifikation

- [x] tsc `--noEmit` sauber
- [x] Vitest 378/378 grün
