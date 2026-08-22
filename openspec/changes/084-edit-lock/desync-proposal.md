# Change 084 — Kollaborations-Lock für Segment-Edit + Edit-Desync-Fixes

## Problem

1. **User-Befund (22.08.):** „Wenn man die segment Edge verstellt und dann
   in edit mode geht zeigt die edit box Teilweise noch den 'alten' Text
   vorm justieren."

2. **User-Anforderung (22.08., Kollaboration):** „Checke auch was passiert
   wenn zwei User gleichzeitig bearbeiten, der eine im edit mode ist und
   der andere das Segment verschiebt oder ein neues einfügen will. Das
   muss gesperrt sein während ein Segment im edit mode ist, aber mit
   einem kleinen Lock Symbol und Rollover wer Grade bearbeitet."

## Root Causes (analysiert im Code)

- **A — localTexts-Hänger (SegmentList):** Ist beim Grenz-Drag ein
  Edit-Save noch pending (`localTexts` gesetzt, `localPendingRef=true`),
  bleibt `localTexts` nach dem Drag **dauerhaft** gesetzt: Der
  Fingerprint-Guard wartet auf eine Bestätigung mit identischem
  Text-Fingerprint, die nach dem Drag nie eintrifft (die Drag-Änderung
  verändert die Segment-Texte) → `shown = dragPreview ?? localTexts ?? …`
  zeigt für immer die alten Texte — auch die Edit-Box
  (`setEditText(shown[i].text)`).

- **B — Edit-PUT-Race (Solo):** `handleSave` (SegmentList) übernimmt die
  Server-Antwort von `updateSegment` ungeprüft. Liegt ein neuerer
  Struktur-Commit (Grenz-Drag, +/−) zwischen Save-Start und Antwort,
  überschreibt die verspätete Edit-Antwort die neuere Anzeige — der
  „alte Text" kehrt zurück. (Das Change-007-Muster „monotone Sequenz,
  letzter gewinnt" existiert in RecordingCard, aber NICHT für handleSave.)

- **C — Kein Kollaborations-Lock:** Das `editing`-Awareness-Flag ist nur
  ein boolean (Name + „bearbeitet gerade"-Leiste). Strukturoperationen
  (Grenz-Drag, Insert, Delete, Split) anderer Clients laufen ungehindert
  weiter, während ein Segment editiert wird → Desync/Wort-Gerüst-Races.

## Scope

- Awareness-Feld `editing` = Segment-Index (`number`) oder `false`;
  Hook liefert zusätzlich `editLock {index, name}` (fremder Editor).
- SegmentList: Sperre für Strukturoperationen bei aktivem fremden Edit,
  fremd-editiertes Segment nicht editierbar, Lock-Symbol + Tooltip
  („Bearbeitet von <Name>") an gesperrten Elementen.
- Solo-Fixes A (Drag-Commit verwirft localTexts) + B (commitSeq-Guard).
- Sperre ist Awareness-basiert (best effort, Client-seitig konsistent;
  kein Server-Lock — Awareness verschwindet bei Client-Crash von selbst).
