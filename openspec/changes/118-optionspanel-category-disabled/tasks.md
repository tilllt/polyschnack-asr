# Tasks — Change 118 (OptionsPanel: Kategorie-Disabled)

## Done

- [x] Proposal: openspec/changes/118-optionspanel-category-disabled/proposal.md
- [x] Rows: opacity-40 → opacity-25 (nicht verfügbare Optionen deutlich schwächer)
- [x] tabDis(): Kategorie-Tab disabled, wenn ALLE Optionen des Tabs bei der
      Aktion nicht verfügbar sind (rowDis + vadOk/diarOk/oidc/backends/streaming)
- [x] Tab-Optik: text-muted2 opacity-30 cursor-not-allowed, Tooltip
      „Für diese Aktion nicht verfügbar.", data-testid opt-tab-<id>
- [x] Auto-Switch: useEffect springt zum ersten verfügbaren Tab, wenn der
      aktive Tab durch den Aktion-Wechsel disabled wird
- [x] 3 neue Tests (Change 118) — 312/312 grün, tsc grün, Build grün

## Verifikation

- [ ] Push → CI muss NUR test-frontend/test-webapp/build-webapp + Mirror
      starten (Positiv-Test für Change 117)
