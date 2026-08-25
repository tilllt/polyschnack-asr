# Tasks — Change 120 (Recording-Liste: Tag-Filter + Sortierung)

## Done

- [x] Proposal: openspec/changes/120-sort-tag-filter-fixes/proposal.md
- [x] Backend: tag-Parameter → `Query(None)` (FastAPI erkennt ihn sonst nicht)
- [x] Backend: HTTP-Regressionstest (TestClient) für `?tag=`-Filter
- [x] Frontend: buildRenderItems respektiert Backend-Reihenfolge (Gruppe an
      Position des ersten Mitglieds)
- [x] Frontend: grouping.test.ts (neu, 7 Tests)
- [x] Frontend: AbortSignal in fetchRecordings/useRecordings + Debounce
      (~250 ms) für Sort-/Tag-Badge-Klicks in App.tsx
- [x] tsc + Build + npm test (324) + pytest tests/ (974) grün

## Verifikation

- [x] Lokale Instanz: OpenAPI zeigt `tag`; `?tag=arbeit` → 4 statt 14
- [x] GUI (Browser): Sort-Klick ändert Reihenfolge (Length desc inkl.
      NULL-Dauern ans Ende); Tag-Filter reduziert (#arbeit → 4); 10 schnelle
      Sort-Klicks ohne Hänger/Crash
- [ ] Push auf main → CI success, melden
- [ ] Prod-Deploy durch User; danach Post-Deploy-Check (OpenAPI `tag` +
      `?tag=…`-Filter live)
