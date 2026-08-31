# Change 164 — Tasks

- [x] Sandbox-Repro vor Fix: Skript kopieren, compose.yml abweichend,
      Fake-Remote (localhost-HTTP, `POLYSCHNACK_GITLAB_BASE`) →
      `sync-compose` Exit 1 (Bug belegt).
- [x] Fix in `polyschnack-manage.sh` (if-Form + `return 0`).
- [x] Sandbox nach Fix: Exit 0, lokale compose.yml unverändert.
- [x] openspec/change 164 (proposal/design/tasks) committen, push main.
- [ ] CI-Pipeline grün abwarten (ps_ci_check).
- [ ] Box: `./polyschnack-manage.sh selfupdate`; danach `update` läuft
      durch compose-Diff (lokal behalten) bis zum Start.
