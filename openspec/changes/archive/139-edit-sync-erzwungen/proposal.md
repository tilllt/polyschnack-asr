# Change 139: Edit-Sync erzwungen (Anzeige == Edit-Inhalt)

**Status:** Archived (auf specs/ angewendet, 2026-08-28)

## Problem

User-Befund (Chrome/Android, 2026-08-28, seit Juli bekannt): „Änderungen an
der Transkription — sobald man den Edit-Mode verlässt, wird wieder die alte
Version gezeigt. Geht man wieder in den Edit-Mode zurück, sind die
Änderungen wieder da."

Die Anzeige und der Edit-Inhalt sind ZWEI Ebenen: `shown` (Anzeige) =
`dragPreview ?? localTexts ?? segmentsProp` in SegmentList, `segmentsProp` =
abgeleitete Anzeige aus dem React-Query-Cache. Der alte Save-Pfad
(handleSave) setzte `onEdited` erst NACH der Server-Antwort — zwischen
Edit-Ende und Bestätigung (bzw. bei Fehlern/Desync) kippte die Anzeige auf
den alten Cache-Stand zurück, während der Edit-Inhalt neu blieb.

Zusätzlich: Die Anzeige rendert die Wort-Spans aus `seg.words` — der alte
PATCH-Pfad ließ die Wörter nach einem Text-Edit mit geänderter Wortzahl
alt (Wort-Spans zeigten den alten Text, obwohl `seg.text` neu war).

## Ziel

**Erzwungener Sync:** Die Anzeige wird beim Edit-Save SOFORT auf den
lokalen Edit-Stand gesetzt (optimistisches `onEdited` VOR dem Server-Write)
— Anzeige und Edit-Inhalt können nie divergieren. Inklusive Wort-Neubau
(die Wort-Spans zeigen den neuen Text). Bei Server-Fehler: ehrlicher
Rollback + sichtbarer Fehler-Toast (kein stilles Zurückkippen).

## Nicht-Ziel

- Kein Yjs/Collab-Umbau (der Collab-Pfad hat eigene Sync-Semantik via
  Autosave, Change 068).
- Kein Re-Align/Re-Transcribe (verfeinert Wort-Zeiten später akustisch).

## Kontext

- `SegmentList.handleSave` (Solo-Zweig) nutzte `updateSegment`-PATCH mit
  Change-129-Index-Mapping; `onEdited` erst nach Server-Antwort.
- `shown = dragPreview ?? localTexts ?? segmentsProp`; Fingerprint-Guard
  (Change 077) verwirft `localTexts` bei Prop-Bestätigung.
- `replaceSegments` (PUT /segments, Change 125/068) = etablierter
  Listen-Persistenzweg; `rebuildWordsFromText` (neu, resegment.ts) baut
  Wörter gleichverteilt über die Segment-Zeit (Backend-Fallback-Muster).

## Changes

- **handleSave (Solo):** (1) `next` = Anzeige mit editiertem `text` UND neu
  gebauten `words` (`rebuildWordsFromText`); (2) `onEdited(next, text,
  manual=true)` SOFORT — Cache == Edit-Inhalt; (3) Edit schließen;
  (4) `replaceSegments(recordingId, next, false)` (voller Listen-PUT,
  atomar, persistiert die Anzeige als Wahrheit); (5) Server-Bestätigung
  via `onEdited(result...)`; (6) Fehler → Rollback auf `prevShown` +
  Toast `edit_save_error` (kein stiller Verlust).
- **resegment.ts:** `rebuildWordsFromText(seg, text)` — pure, getestet.
- **Tests:** editindex.test.tsx (PUT-Liste statt PATCH, sofortiges onEdited
  mit Edit-Inhalt, Words im optimistischen Stand), annotate.test.tsx
  (Anzeige zeigt neuen Text nach Edit-Save).
- **OpenSpec:** Req-Delta in `transcription-view` (Req 7 Text-Edit).

## Downgrade

- handleSave zurück auf PATCH + onEdited nach Server-Antwort (Stand 138);
  `rebuildWordsFromText` entfernen.
