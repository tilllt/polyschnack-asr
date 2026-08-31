# Change 164 — Design

## Problemklasse

Letzte Anweisung einer unter `set -euo pipefail` aufgerufenen Funktion ist
eine `[ test ] && …`-Liste: schlägt der Test fehl, wird die Liste mit Exit 1
beendet und die Funktion gibt 1 zurück → `set -e` beendet das Skript.
Gleiche Klasse wie der Change-107-diff-Bug (dort mit `|| true`
entschärft, Kommentar in `sync_compose`). Audit: nur Zeile 460 hat diese
Klasse im Skript — die übrigen `[ ] &&`-Zeilen stehen in Loops
(`continue`/`return`) oder sind nicht die letzte Zeile einer Funktion.

## Alternativen

1. `[ "$changed" = "0" ] && echo … || true` — minimal, verdeckt aber die
   Ursache: Die Funktion bleibt davon abhängig, dass die letzte Zeile nie
   ein Test ist (nächster Test = nächster Abbruch).
2. `if`-Form + explizites `return 0` (gewählt): macht die Invariante
   „sync_compose meldet Abweichungen, bricht aber nie ab" sichtbar und
   dauerhaft — unabhängig davon, was später in der Funktion landet.

## Offene Fragen

Keine. Verifikation als Sandbox-Repro (Exit-Codes deterministisch).
