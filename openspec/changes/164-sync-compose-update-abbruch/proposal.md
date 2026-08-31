# Change 164 — sync-compose bricht `update` bei compose-Abweichung ab

**Status:** Proposed

## Befund (2026-08-31, Deploy auf KI-Box)

- Auf der KI-Box (kein `.git`) läuft `update` = `sync_compose` → pull →
  models → start.
- `sync_compose` endet mit `[ "$changed" = "0" ] && echo "-> Alle
  compose-Dateien aktuell."` als letzter Zeile. Weicht eine compose-Datei
  vom Repo-Stand ab (auf der Box gewollt: `WEBAPP_PORT:-8090` wegen
  llama.cpp auf :8088), ist `changed=1`, der Test liefert Exit 1 → unter
  `set -euo pipefail` bricht das Skript ab, BEVOR pull/models/start laufen.
- Folge: `./polyschnack-manage.sh update` ist auf jeder Box mit lokal
  angepasster compose.yml unbenutzbar — auch interaktiv, auch ohne
  `--force`.

## Lösung

1. `sync_compose` endet mit `if [ "$changed" = "0" ]; then echo …; fi` und
   explizitem `return 0`: Die Funktion meldet Abweichungen, bricht aber
   nie ab. Diff-/Backup-/Bestätigungs-Logik (Change 107) bleibt
   unverändert — lokale manuelle Anpassungen werden weiterhin geschützt.
2. `SELFUPDATE_SHA` wird aktualisiert, damit die Box das neue Skript per
   `./polyschnack-manage.sh selfupdate` übernehmen kann.

## Tests

- Reproduktion (Sandbox, vor Fix): `sync-compose` mit abweichender
  compose.yml (Fake-Remote per localhost-HTTP, `POLYSCHNACK_GITLAB_BASE`)
  → Exit 1.
- Nach Fix: Exit 0, lokale Datei NICHT überschrieben, Ausgaben unverändert.
- Box: `selfupdate`; danach läuft `update` durch den compose-Diff (lokal
  behalten) bis zum Start.
