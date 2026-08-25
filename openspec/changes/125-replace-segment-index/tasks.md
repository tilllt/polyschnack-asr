# Tasks — Change 125 (Replace mit Anzeige-Index gegen Original-Segmente)

- [ ] Analyse/Root-Cause: Replace-Pfad `commitSegmentText` → PATCH mit
      Anzeige-Index gegen `rec.segments`; Live-Beweis 404 (seed01, 2
      Original-Segmente, PATCH /segments/3)
- [ ] Fix: Replace-Effect in `SegmentList.tsx` schreibt `changed`-Liste
      per `replaceSegments` (PUT, `createVersion=false`) statt PATCH je
      Segment
- [ ] Tests: `SegmentList.search.test.tsx` auf PUT umstellen; neuer Fall
      „Replace bei re-segmentierter Anzeige → genau ein PUT mit voller
      Liste"
- [ ] Verifikation: Frontend-Suite grün, `npm run build` grün
- [ ] Browser-Live-Test (Dev): segMaxDuration=1, Suche/Replace → PUT 200,
      Reload → persistiert
- [ ] Backend-Suite grün (unverändert, Regression)
- [ ] OpenSpec `tasks.md` abschließen, Commit, Push, CI
