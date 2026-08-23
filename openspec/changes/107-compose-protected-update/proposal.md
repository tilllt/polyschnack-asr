# Change 107 — compose.yml-Schutz beim Update (interaktiver Abgleich)

## Problem

`polyschnack-manage.sh update` behandelt die compose-Dateien auf der Box
unsicher:

1. **Box ohne `.git`:** `git pull` wird übersprungen → die neue compose.yml
   (z. B. mit `crispr-sep` aus Change 106) kommt dort nie an. Der Deploy
   wirkt dann nicht, ohne dass jemand es merkt.
2. **Blind-Überschreiben:** Das Skript empfiehlt in zwei Pfaden
   (`benchmark_key_status`, `benchmark`-Fehlerpfad) direkt
   `curl -fsSL -o compose.yml …` — das **überschreibt eine manuell
   angepasste compose.yml ohne Rückfrage** (lokale Änderungen: Ports,
   Envs, REGISTRY, GPU-Overlay-Referenzen … sind weg).

Regel (User, 23.08.2026): „Du kannst das compose.yml von Leuten nicht
einfach überschreiben … höchstens interaktiv mit manueller Bestätigung
patchen."

## Lösung

Neuer Mechanismus `sync-compose` (und Einbau in `update` ohne Git):

- Remote-Stand der compose-Dateien laden (GitHub raw / GitLab-API, Quelle
  wie `selfupdate_check`)
- **Nur wenn abweichend:** `diff -u` anzeigen, Backup
  `compose.yml.bak-<timestamp>` anlegen, dann **interaktiv fragen**
  (`Anwenden? [j/N]`, Default **N**)
- **Ohne TTY (automatisiert): kein Überschreiben** — nur Hinweis mit dem
  Diff, `--force` für explizite Bestätigung
- Betroffen: `compose.yml`, `compose.backends.yml`, `compose.benchmark.yml`
  (die Box-Overlays `compose.gpu.yml`/`compose.oidc.yml` sind lokal heikel —
  werden NIE automatisch angetastet)
- Die zwei blinden `curl -o`-Empfehlungen im Skript auf `sync-compose`
  umstellen

## Verifikation

- `bash -n polyschnack-manage.sh`
- Funktions-Test: lokale Dummy-compose.yml, Remote simulieren → Diff +
  Bestätigung; „n" behält lokale Version; „j" legt Backup + übernimmt;
  ohne TTY (Pipe) → kein Überschreiben
- Deploy-Anweisung Change 106 bleibt `selfupdate && update` — `update`
  fragt jetzt interaktiv nach der neuen compose.yml
