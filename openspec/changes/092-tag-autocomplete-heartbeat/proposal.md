# Change 092 — Tag-Autocomplete + Heartbeat-Position unter dem Progress-Bar

**Status:** fertig (2026-08-22)
**Vorgaben (User, 22.08.):** „wenn man in 'add tag' clickt soll es einem die
bereits existierenden Tags zur Auswahl anbieten." · „Heartbeat Anzeige liegt
unter den Progress Chips — sie sollte besser unter dem progress bar sein."

## Problem

1. TagEditor (Change 054) bot beim Hinzufügen keine Vorschläge: Jeder Tag
   musste von Hand getippt werden — bei vielen Recordings entstanden
   Duplikate/Schreibvarianten („Walzen"/„walzen").
2. Auf schmalen Screens wrappten die Phasen-Chips; die Heartbeat-/ETA-Zeile
   (Change 082) hing dadurch optisch „unter den Chips" statt unter dem
   Fortschrittsbalken.

## Lösung

**A) Tag-Autocomplete**
- Neuer Endpoint `GET /api/tags`: alle Tags des aktuellen Users über alle
  Aufnahmen — dedup case-insensitiv (erste Schreibweise gewinnt, wie PATCH),
  getrimmt, sortiert; **User-Isolation** (nur eigene Recordings).
- TagEditor: Klick/Fokus ins Feld öffnet Dropdown mit existierenden Tags,
  die noch NICHT auf dieser Aufnahme liegen; Tippen filtert live
  (Substring, case-insensitiv); Klick übernimmt Tag (PATCH); Pfeiltasten +
  Enter wählen das Highlight; Escape/Blur schließt.
- Query gecacht (staleTime 60 s), nur bei `canEdit` aktiv.

**B) Heartbeat unter dem Progress-Bar**
- Chips-Zeile enthält nur noch die Phasen-Chips.
- Ampel (Heartbeat) + „vor Xs" + % links, ETA-Rest rechts — als eigene
  schmale Zeile **unter** dem Fortschrittsbalken.

## Betroffene Dateien
- `webapp/app/routers/recordings.py` — `GET /api/tags` (User-Isoliert)
- `webapp/frontend/src/api.ts` — `fetchAllTags()`
- `webapp/frontend/src/components/TagEditor.tsx` — Dropdown/Autocomplete
- `webapp/frontend/src/components/RecordingCard.tsx` — Status-Block-Umbau
- Tests: `tests/test_sort_tags.py` (list_all_tags), `TagEditor.test.tsx`
  (5 neue Autocomplete-Tests)

## Verifikation
- Backend `test_sort_tags.py` 20/20; Frontend TagEditor 11/11,
  RecordingCard 23/23; tsc + Build sauber.
- Browser (lokale eingeloggte Ansicht, Live-Daten): DOM-Reihenfolge
  Chips (174) → Progress-Bar (176) → Heartbeat-Ampel (180) → „42%" (182) ✓
- CI: nach Push.
