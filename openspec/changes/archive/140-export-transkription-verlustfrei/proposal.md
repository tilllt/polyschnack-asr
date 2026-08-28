# Change 140: Transkription & Export verlustfrei (Text/Wort-Invariante)

**Status:** Archived (auf specs/ angewendet, 2026-08-28)

## Problem

1. **Export unvollständig (User-Befund 2026-08-28, ec98bfdf):** Bei
   gesetzter Segmentlänge baute der Export (`resegment_by_duration`) die
   Bucket-Texte NUR aus den Wörtern. Bei Text/Wort-Desync fehlten Teile
   (~1011 Zeichen von 6978).
2. **Wurzel (sorgfältig analysiert):** Der Forced-Aligner ordnet Wörter
   NUR nach Startzeit zu (`apply_aligned_words`, Change 078). Weichen die
   Zeitbasen ab (Chunk-Offsets, Segment-Lücken) oder alignt eine Gruppe nur
   teilweise, werden Wörter verworfen (Text ⊃ Wörter) oder aus
   Nachbar-Chunks zugeordnet (Wörter ⊃ Text). Beleg ec98bfdf: 8/28
   Segmente mit groben Abweichungen (Text 1113 vs. Wörter 202 Zeichen).
   **Es darf NIE passieren, dass Teile der Transkription verschluckt
   werden** — der bisherige Export-Fix war nur eine Schutzschicht.
3. **Speaker-Rename zu weit gefasst:** `_speaker_key` (Change 138) nutzte
   Substring-Regex + Buchstaben-Fallback → Fehlmatches möglich („1" vs.
   „11", kaputte Labels wie SPEAKER_A matchten fälschlich).

## Ziel

- **Text/Wort-Invariante erzwungen:** Nach jeder Verarbeitungsphase gilt
  `" ".join(seg.words[].word) == seg.text` (für Segmente mit Wörtern) —
  der Text ist unantastbar, nichts wird verschluckt oder erfunden.
- Export verliert nie Text (zweite Verteidigungslinie).
- Speaker-Rename matcht sauber (vollständiges Parsen).

## Nicht-Ziel

- Kein Backfill bestehender Recordings (der User kann Re-Align nutzen —
  der neue Code verhindert den Desync bei allen NEUEN Läufen).
- Keine Änderung an den ASR-/Aligner-Containern.

## Kontext

- `apply_aligned_words` (service.py) ordnet Aligner-Wörter nach Zeit;
  Segment-Texte (ASR) und Wörter (Aligner) sind zwei Quellen.
- `_align_words` (segments.py, Change 010): LCS-Angleich der Wortliste an
  einen Text — unveränderte Wörter behalten Zeiten, fehlende interpolieren,
  Fremdwörter entfallen. Wird zur Heilung wiederverwendet.
- `resegment_by_duration` (service.py + resegment.ts): Export/Anzeige-
  Aufteilung bei gesetzter Segmentlänge (Change 088).
- `_speaker_key` (segments.py, Change 138): Sprecher-Rename-Matching.

## Changes

- **Backend — `reconcile_words_to_text` (segments.py, neu):** gleicht je
  Segment die Wortliste per `_align_words` an den Segment-Text an.
  Aufruf in `_run_align_phase` (nach apply + override-Restore) und als
  Sicherheitsnetz in `update_result` (crud.py, vor dem Persistieren —
  nie den Job-Abschluss brechen). Erzwingt `join(words) == text`.
- **Backend + Frontend — `resegment_by_duration` / `resegmentByDuration`:**
  bei Desync den Segment-Text proportional über die Buckets verteilen
  (Wortgrenzen-Snap, letzter Bucket bekommt den Rest) — verlustfrei.
- **Backend — `_speaker_key` sauber:** vollständiges Parsen
  (SPEAKER_-Präfix + komplette Ziffernfolge, nackte Zahl, einzelner
  Buchstabe); „1" matcht nie „11"; kaputte Labels → kein Match.
- **Tests:** test_reconcile_words.py (neu, 5), test_resegment.py (+2
  Desync), test_speaker_rename.py (+3 sauberes Parsen).
- **OpenSpec:** Req-Deltas in transcription-view (Req 7) + transcription.

## Downgrade

- Reconcile-Aufrufe entfernen (Verhalten wie vor 140); Export-Schutz
  entfernen; `_speaker_key` auf Change-138-Stand zurücksetzen.
