# Change 068 — Atomarer Autosave ohne Versions-Spam, Diff beim Edit-Mode-Ende

**Status:** in Arbeit · **Datum:** 2026-08-21

## Problem

Die Yjs-Kollaboration (Change 053) schreibt Textänderungen nur live in den
Yjs-Doc; die DB-Persistenz erfordert einen manuellen Klick auf
„In DB speichern" (finalize). User-Befund (2026-08-21): Der Button ist
unerwünscht — er suggeriert, dass ohne Klick nichts gespeichert wird, und
verleitet zu Datenverlust. Gewünscht: **atomarer Autosave**. **Zweite
User-Vorgabe:** Nicht für jede Buchstabenänderung eine Version — der
**Diff/Version entsteht erst beim Verlassen des Edit-Mode**.

## Ziel

1. **Autosave statt Button**: Nach jeder Textänderung (lokal oder remote)
   startet ein Debounce-Timer (1500 ms). Läuft er ab, wird der komplette
   Yjs-Doc-Stand atomar per `PUT /recordings/{rid}/segments` gespeichert —
   **ohne neue Version** (nur DB-Stand + updated_at). Der
   „In DB speichern"-Button entfällt.
2. **Atomar**: Ein Autosave ersetzt die komplette Segmentliste in einem
   Request/Transaktions-Commit — nie segmentweises PATCH.
3. **Version erst beim Edit-Mode-Ende**: Wird der Edit-Mode verlassen
   (Textfeld geschlossen, editingIdx → null), wird — nur wenn sich der Text
   seit der letzten Version geändert hat — eine **eine** Version angelegt
   (snapshot kind=edit). Kein Versions-Spam durch Tippen.
4. **Keine Leer-Writes**: Autosave und Versionierung feuern nur bei
   tatsächlicher Textänderung (Vergleich gegen lastSaved).
5. **Solo-Modus unverändert**: ohne Kollaboration speichert der Edit weiter
   direkt — kein Autosave-Pfad.
6. Unmount/Seitenwechsel: pending Änderungen sofort flushen (best-effort,
   mit Version, falls Änderung vorliegt — „Edit-Mode verlassen" = Seite
   verlassen).

## Verhaltens-Delta (IST → SOLL)

- **IST:** Kollaborations-Edits leben nur im Yjs-Doc; „In DB speichern"
  persistiert sie manuell (eine Version je Klick).
- **SOLL:** Tippen → debounced Autosave (1500 ms, ohne Version, atomar);
  Edit-Mode-Ende → genau eine Version (bei Änderung); kein Button; DB ist
  jederzeit aktuell; Kollaboration bleibt live.

## Umsetzung (Skizze)

1. `app/routers/segments.py::replace_segments`: Query-Param
   `create_version: bool = True` — bei False kein snapshot (nur DB-Write).
   Abwärtskompatibel (Default True).
2. `api.ts replaceSegments`: optionales `createVersion` durchreichen.
3. `useYjsTranscription.ts`:
   - Autosave: Debounce 1500 ms auf doc-update; `replaceSegments(
     createVersion=false)`; lastSavedRef-Vergleich (kein Write bei
     unverändertem Text); Fehler still schlucken (nächster Retry beim
     nächsten Update); Unmount-Flush.
   - `setEditingActive`: beim Übergang aktiv → inaktiv einmalig
     `replaceSegments(createVersion=true)` (nur bei Änderung).
4. `SegmentList.tsx`: Button-Zeile entfernen; Kollaborations-Leiste zeigt
   nur noch den aktiven-Editoren-Hinweis (Change 067-Fix), kein Button.
5. Tests: Autosave ohne Version; Version nur bei Edit-Mode-Ende; keine
   Writes bei unverändertem Text; Unmount-Flush mit Version; Backend
   create_version=False erzeugt keine TranscriptVersion.

## Referenzen

- Change 053 (Yjs-Kollaboration), Change 067-Fix (Leiste nur bei aktiven
  Editoren), `app/routers/segments.py::replace_segments` (atomarer Write),
  `app/versions.py::snapshot` (Version kind=edit)
