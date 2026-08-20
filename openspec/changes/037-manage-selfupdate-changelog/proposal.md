# Change 037: polyschnack-manage.sh — Update-Check + selfupdate-Changelog

**Status:** in Arbeit · **Datum:** 2026-08-20

## Problem

1. `polyschnack-manage.sh selfupdate` ersetzt das Skript still — der Nutzer
   erfährt nicht, WAS sich geändert hat.
2. Es gibt keinen Hinweis, wenn eine neuere Version des Skripts existiert —
   die Box läuft mit einer alten Version, ohne dass das auffällt.

## Entscheidung

- **Versionierung über Commit-SHA:** Die Datei trägt `SELFUPDATE_SHA="<sha>"`
  (Commit, der die Datei zuletzt im Repo änderte). Deterministisch, kein
  Versionsnummern-Pflegen.
- **Update-Check bei jedem Lauf:** Nach dem .env-Load wird (außer bei
  `selfupdate`/`help`) die Remote-Version geholt (gleiche Quelle wie
  selfupdate: GitHub-Mirror default, GitLab-API mit `POLYSCHNACK_GITLAB_BASE`)
  und `SELFUPDATE_SHA` verglichen → Hinweis auf neue Version.
  Deaktivierbar per `POLYSCHNACK_SELFUPDATE_CHECK=off` in der .env.
  Netzwerkfehler werden still ignoriert (nie blockieren).
- **selfupdate-Changelog:** Vor dem Ersetzen wird `OLD_SHA` gelesen; danach
  werden die Commit-Titel der Datei (`path=polyschnack-manage.sh`) seit
  `OLD_SHA` aus der Commits-API (GitHub bzw. GitLab) ausgegeben.

## Tasks

- [x] `SELFUPDATE_SHA` im Kopf + Doku
- [x] `selfupdate_check()` (stiller Check, Disable-Env) + Aufruf in der Hauptlogik
- [x] selfupdate: OLD_SHA lesen + Change-History ausgeben
- [x] Committen (Feature + SHA-Bump), CI prüfen
- [x] benchmark: Existenz-Check für compose.benchmark.yml mit Anleitung (Box-Fehler
  „open ...: no such file or directory" → klare Meldung + Fix-Weg)
