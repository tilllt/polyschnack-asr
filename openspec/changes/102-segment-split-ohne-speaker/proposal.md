# Change 102 — Segment-Split ohne Speaker-Auswahl + Anzeige/Persist-Entkopplung

## Problem

User-Auftrag: „Segmente einfügen muss mit oder ohne Speaker-Auswahl
funktionieren." Live-Repro zeigte: Der Split-Confirm sendete einen PUT mit
EINEM Segment, `text: ""` → Backend 400 („segment … empty text") — 7×.

Zwei Wurzeln (per fetch-Stack-Trace + Live-Repro bewiesen):

1. **resegmentByDuration verschmolz kurze unmarkierte Segmente**: Die
   Bucket-Logik sammelte Wörter ÜBER Segmentgrenzen hinweg (Flush nur bei
   > Ziel-Länge oder Sprecherwechsel). Zwei kurze ASR-Segmente (zusammen
   < Ziel) wurden in der ANZEIGE zu EINEM 14-Wörter-Segment — Anzeige ≠
   DB-Zustand.
2. **Yjs-Autosave persistierte die Anzeige**: useYjsTranscription bekam
   `displaySegments` (die Vorschau!) als Base. Beim Laden (geteilte
   Aufnahmen) schrieb der Autosave (Mount- + Unmount-Flush) das
   verschmolzene Segment zurück → PUT mit leerem/verschmolzenem Zustand →
   400 + Datenverlust-Risiko. Der Speaker-Fallback in `confirmSplit`
   (`splitSpeaker || orig || "SPEAKER_00"`) war bereits vorhanden — der
   Split scheiterte VORHER an der Anzeige-Verschmelzung.

## Fix

1. **resegment.ts**: Bucket wird vor jedem neuen Segment geschlossen
   (`flush()` am Anfang des words-Blocks). Kurze Segmente bleiben
   eigenständige Buckets; nur Riesen-Chunks (> Ziel) teilen sich.
2. **SegmentList/RecordingCard**: neue Prop `persistBase` — der Yjs-Hook
   nutzt die DB-Segmente als Struktur-Base für lastSaved/Init/Autosave,
   nie die abgeleitete Anzeige.

## Tests

- resegment.test.ts: 2 kurze Segmente ohne _manual → 2 Buckets (keine
  Verschmelzung); deriveSegments mit Länge → 2; Split auf Segment 0
  (Wörter 0-3) → 3 Segmente mit korrekten Texten + Speaker.
- Live (Playwright, Recording 100): 2 DOM-Segmente, 0 PUTs beim Laden,
  Markierung + „Insert" ohne Speaker-Auswahl → PUT 200 mit 3 Segmenten,
  erstes Segment speaker SPEAKER_00.
