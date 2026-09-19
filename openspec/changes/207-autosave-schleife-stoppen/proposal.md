# Change 207 — Kollaborations-Autosave: Schleife beendet, Fehler sichtbar

## Warum

Am 19.09.2026 fielen im Webapp-Log **1090 abgewiesene `PUT …/segments`** auf — alle für
**dieselbe** Aufnahme, in Bursts von bis zu 675 Anfragen in 7 Sekunden, und **keine einzige
erfolgreiche Speicherung**. Der Nutzer hatte in der Aufnahme bearbeitet; in der Datenbank stand
weiterhin der Stand vom Vortag. Seine Änderung war nie gespeichert worden — und nichts sagte es ihm.

Drei Ursachen greifen ineinander:

1. **Der Kreislauf (Ursache der Bursts).** `save` ist ein `useCallback` mit `saving` in den
   Abhängigkeiten; der Provider-Effekt hängt an `save`. Damit bekam `save` bei **jedem**
   Speicherversuch eine neue Identität → der Effekt lief neu → Yjs-Provider und
   WebSocket-Verbindung wurden neu aufgebaut → beim Verbinden wird das Doc befüllt → Doc-Update →
   Autosave → Speicherversuch → … Eine sich selbst antreibende Schleife.
2. **Ein Payload, den der Server immer ablehnt.** Enthält der Stand ein Segment mit leerem Text
   (Zwischenstand beim Tippen), antwortet der Endpunkt mit 400 (`segment N empty text`).
   Zusammen mit (1) konvergiert die Schleife nie — sie hämmert weiter.
3. **Der Fehler wurde still geschluckt** (`catch { return false }`). Der Nutzer tippte weiter,
   ohne zu wissen, dass nichts ankam.

## Was sich ändert

**Frontend (`hooks/useYjsTranscription.ts`)**

- Der Schutz gegen paralleles Speichern läuft über eine Ref (`savingRef`) statt über den State:
  `save` behält seine Identität → der Provider wird **nicht** mehr pro Speicherversuch neu
  aufgebaut. `failuresRef` zählt Fehlversuche.
- Ein Stand mit leerem Segment wird **gar nicht erst gesendet**. Statt den 400 zu provozieren,
  wartet der Autosave auf den nächsten Doc-Update (also bis Text da ist).
- Fehler sind sichtbar: neuer Parameter `onSaveError`; er wird **einmal je Fehlerserie** gerufen
  (nicht je Versuch). `SegmentList` zeigt daraus einen Hinweis in der Oberfläche.
- **Backoff:** nach einem Fehlversuch wartet der Autosave die vierfache Debounce-Zeit statt
  anderthalb Sekunden — kein Hämmern mehr.

**Backend (`routers/segments.py`)**

- Die Ablehnungsgründe werden **protokolliert** (leere Liste / Segment ohne `start`/`end` mit
  Feldnamen / Segment mit leerem Text mit Index und Segmentzahl). Vorher stand im Log nur die
  Zahl 400 — die Fehlersuche musste raten.

**Sprachen**: neuer Schlüssel `collab_save_empty_text` in Deutsch, Englisch, Portugiesisch.

## Abgrenzung

- Der Server bleibt streng (leerer Text wird weiterhin nicht gespeichert) — das ist
  Datenhygiene. Geändert hat sich nur, dass die Oberfläche solche Zwischenstände nicht mehr
  sendet und dass Fehler nicht mehr verschwiegen werden.
- Kein Eingriff in Grenz-Drag, Split, Einfügen/Löschen (die nutzen weiter ihre eigenen, bereits
  bereinigten Pfade).
- Keine Migration, keine Änderung am Datenmodell.

## Nachweis

- Vier neue Tests (`frontend/src/hooks/useYjsTranscription.test.tsx`): Provider wird genau einmal
  aufgebaut; leerer Stand wird nicht gesendet, aber gemeldet; gefüllter Stand genau einmal
  gespeichert; nach einem Fehler kein Sekundentakt.
- `tsc --noEmit` ohne Befund, komplette Frontend-Suite grün.
