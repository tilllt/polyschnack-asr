# Tasks — Change 117 (CI: changes-Filter)

## Done

- [x] Proposal: openspec/changes/117-ci-changes-filter/proposal.md
- [x] .gitlab-ci.yml: alle 20 Jobs auf `rules:` + `changes:` umgestellt
      (build-*/test-*/pages/compose-validate auf ihre Quellverzeichnisse;
      mirror-github/mirror-ghcr laufen weiter bei jedem main-Push)
- [x] Alle `needs:` auf `optional: true` (47×) — Builds laufen auch, wenn
      der Test-Job wegen fehlender Änderungen übersprungen wurde; Mirror
      wartet nur auf existierende Jobs
- [x] YAML lokal validiert (pyyaml), kein `only:` mehr in der Datei

## Verifikation

- [ ] Push → Pipeline bei reinem CI-Change muss `skipped` sein
- [ ] Nächster echter Code-Push: nur betroffene Jobs
