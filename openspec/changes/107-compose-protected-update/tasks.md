# Tasks — Change 107 (compose.yml-Schutz beim Update)

## Phase 1 — sync-compose im Manage-Skript ✅
- [x] `_compose_files`/`_repo_url`-Helfer + `sync_compose` (Vergleich, Diff, Backup, interaktive Bestätigung j/N mit Default N, `--force`)
- [x] Kein TTY → kein Überschreiben (nur Hinweis + Diff)
- [x] `update` (ohne .git): sync-compose statt nur Warnung; Git-Pfad: Hinweis bei lokal modifizierten compose-Dateien
- [x] Blind-`curl -o compose.yml`-Empfehlungen (2 Stellen) auf sync-compose umgestellt
- [x] Case-Eintrag `sync-compose` + Usage-Zeile
- [x] Bugfix: `diff -u ... | head` braucht `|| true` (set -e killte die Funktion vor Backup/Bestätigung — im Funktionstest gefunden)

## Phase 2 — Tests & Verifikation ✅
- [x] `bash -n` OK
- [x] Funktionstest (isolierter Harness mit Fake-curl):
  - Pipe/kein TTY → lokale Version bleibt (kein Overwrite) ✅
  - `--force` → Backup + Übernahme ✅
  - identische Datei → „bereits aktuell", kein Backup ✅
- [ ] CI grün (nach Push)
