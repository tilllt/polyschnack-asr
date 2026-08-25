# Tasks — Change 122 (Tag-Filter-Falle: Leer-Zustand behält Filterleiste)

## Done

- [x] Proposal: openspec/changes/122-tag-filter-empty-state/proposal.md
- [x] mergeChipTags in sortState.ts (aktive Tags bleiben sichtbar)
- [x] RecordingList: Filterleiste als Einheit, im Leer-Zustand eingebettet
- [x] i18n-Keys tag_add_hint/tag_remove_hint (de/en/pt)
- [x] Tests: sortState +4 (12/12), Frontend-Suite 328/328, tsc + Build grün
- [x] GUI: 0-Treffer-Fall zeigt Sort-Badges + aktiven Tag-Chip, Abwahl
      bringt Liste zurück

## Verifikation

- [ ] Backend-Suite komplett grün (Change 121 + 122 zusammen)
- [ ] Push main → CI success
- [ ] Prod-Deploy durch User; Post-Deploy-Check
