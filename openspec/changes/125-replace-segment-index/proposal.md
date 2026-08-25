# Change 125 — Ersetzen schreibt mit Anzeige-Index gegen Original-Segmente

## Problem

User-Befund (2026-08-25, nach Deploy von Change 124): **Suchen findet den
String, aber „Replace" ersetzt ihn nicht.**

Lokal reproduziert (Dev-Instanz, Browser): Die SegmentList bekommt als
`segments`-Prop die **re-segmentierte Anzeige** (`displaySegments`,
Change 088 — Default 25 s, Frontend-seitig berechnet). Suchen/Ersetzen
(Change 124) arbeitet korrekt gegen die Anzeige (`shown`), aber der
Schreibpfad `commitSegmentText` ruft `updateSegment(recordingId, idx, text)`
→ `PATCH /recordings/{rid}/segments/{idx}` — und der Server adressiert
`idx` gegen das **Original-Array** (`rec.segments`, ASR-Chunks).

Bei aktiver Re-Segmentierung hat die Anzeige deutlich mehr Segmente als die
DB (bei langen ASR-Segmenten der Regelfall). Sobald der Treffer in einem
Anzeige-Segment mit `idx >= len(rec.segments)` liegt, antwortet der Server
mit `404 segment not found`; die Anzeige wechselt nur optimistisch
(`localTexts`) und kippt beim nächsten Refetch zurück → „es passiert
nichts". Beweis im Live-Test: `PATCH /api/recordings/seed01/segments/3`
gegen ein Recording mit nur 2 Original-Segmenten → 404.

Gleiche Fehlklasse beim manuellen Edit (`handleSave` → PATCH mit
Anzeige-Index) — dort nicht Teil dieses Changes (kein User-Report; wird in
der Analyse dokumentiert).

## Lösung

Der Replace-Effect schreibt die geänderte **komplette Anzeige-Liste** per
`replaceSegments` (`PUT /recordings/{rid}/segments`, `SegmentListUpdate` —
derselbe Endpoint, den Draggable-Boundaries nutzen) statt eines PATCH je
Segment:

- Ein PUT mit der vollständigen `changed`-Liste (ersetzte Texte) → kein
  Index-Problem, weil die Anzeige-Aufteilung selbst persistiert wird.
- Der Server markiert `segments_manual=True` (etabliertes Verhalten bei
  Struktur-Operationen) → die Anzeige re-segmentiert danach nicht mehr
  automatisch darüber; Export/SRT/VTT nutzen dieselben Grenzen (gewollt,
  konsistent zu Boundary-Drag).
- Wörter bleiben erhalten (PUT-Validierung: nur start/end/text nötig).
- Optimistisches Verhalten + `onEdited`-Cache-Update bleiben wie gehabt;
  `localPendingRef`-Guard schützt vor Prop-Rückkippen.
- `createVersion=false` (Autosave-Semantik): Ersetzen ist eine
  einmalige Bulk-Aktion, keine Edit-Mode-Sitzung — keine
  TranscriptVersion je Klick (vermeidet Versions-Spam).

## Betroffene Dateien

- `webapp/frontend/src/components/SegmentList.tsx` (Replace-Effect:
  PATCH je Segment → ein PUT)
- `webapp/frontend/src/components/SegmentList.search.test.tsx`
  (Tests auf PUT umgestellt + neuer Fall „Re-Segmentierung")

## Verifikation

1. Frontend-Tests grün (Replace-Tests mocken jetzt `replaceSegments`/PUT).
2. Browser-Live-Test Dev-Instanz: segMaxDuration=1 (Anzeige ≫ Original),
   Suche „Suchwort", Replace → ein PUT 200, Reload → Text persistiert.
3. Backend-Suite grün (Endpoint unverändert).
