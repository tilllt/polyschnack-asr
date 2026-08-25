# Tasks — Change 129

- [x] Roter Test: Edit im 2. Anzeige-Bucket eines re-segmentierten
      Riesen-Segments → `updateSegment` muss mit Server-Index 0 und dem
      vollständigen Server-Segment-Text gerufen werden (nicht Anzeige-Index 1
      mit Teiltext) — **rot bestätigt** (Anzeige-Index 1 wurde gerufen)
- [x] Fix: `handleSave` bildet Anzeige-Index → Server-Segment ab und
      rekonstruiert den Gesamttext aus allen Anzeige-Stücken des Segments
      (`resolveServerTarget`, nutzt `persistBase`)
- [x] Grün: neuer Test (2/2) + SegmentList/RecordingCard-Suiten (56/56)
- [x] Frontend-Gesamtsuite (342/342) + Build grün
- [x] OpenSpec: Struktur konform (proposal + tasks; CLI lokal nicht
      vorhanden, wie bei 125–128)
- [x] Commit + Push + CI-Report
