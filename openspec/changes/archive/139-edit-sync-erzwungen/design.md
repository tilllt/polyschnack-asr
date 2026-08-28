# Change 139 — Design-Entscheidungen (Edit-Sync erzwungen)

## 1. Warum der volle Listen-PUT statt PATCH

Der alte Pfad (updateSegment-PATCH mit Change-129-Index-Mapping) war
server-seitig korrekt, aber: (a) `onEdited` kam erst nach der
Server-Antwort → Desync-Fenster; (b) bei Wortanzahl-Änderungen verschoben
sich die re-segmentierten Bucket-Grenzen → der Fingerprint-Guard behielt
`localTexts` (Anzeige = lokale alte Buckets) oder verwarf sie (Anzeige =
alter Cache) — in beiden Fällen kippte die Anzeige vom Edit-Inhalt weg.
Der volle Listen-PUT (Change 125/068-Muster) persistiert die ANZEIGE als
Wahrheit: keine Index-Probleme, atomar, `segments_manual=true` friert die
sichtbare Aufteilung ein → Anzeige == DB == Edit-Inhalt, erzwungen.

## 2. Wort-Neubau (rebuildWordsFromText)

Die Anzeige rendert Wort-Spans aus `seg.words`. Beim Text-Edit mit
geänderter Wortzahl zeigten die Spans sonst die alten Wörter. Die pure
Funktion verteilt die neuen Wörter gleichverteilt über die Segment-Zeit
(Backend-Fallback `_distribute_words`); die Zeiten sind Schätzwerte — ein
Re-Align verfeinert sie akustisch (dokumentierter Trade-off, wie beim
Text-Edit Change 010).

## 3. Fehlerpfad: ehrlicher Rollback

Bei Server-Fehler: `onEdited(prevShown, …)` (Anzeige zurück auf den Stand
VOR dem Edit) + Toast `edit_save_error`. Kein stilles Zurückkippen OHNE
Meldung (der ursprüngliche Desync-Bug) und kein Fake-Erfolg (Anzeige neu,
obwohl nicht gespeichert). Der User sieht sofort, dass der Save fehlschlug.

## 4. manual=true beim optimistischen Update

Weil der volle Listen-PUT `segments_manual=true` setzt, bekommt das
optimistische `onEdited` ebenfalls `manual=true` — sonst würde die Anzeige
(noch auto-re-segmentierend) vom persistierten Stand abweichen. Die
sichtbare Aufteilung wird damit eingefroren (gewollt: eine Wahrheit).

## 5. Abgrenzung

- Yjs/Collab-Pfad bleibt unverändert (setSegmentText + Autosave,
  Change 068) — dort ist die Index-Semantik die Anzeige und der Autosave
  persistiert die volle Liste.
- Der Change-129-`resolveServerTarget` wurde entfernt (nicht mehr genutzt).
