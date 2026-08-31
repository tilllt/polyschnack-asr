# Change 166 — Design

## Problemklasse

Invalidations-Mechanik vorhanden, Signal fehlt: Der Learner kann die
Historie nur invalidieren, wenn der Aufrufer einen Digest liefert — keiner
tut das. Klassischer „wired, aber nie gespeist"-Gap (Audit-Befund:
`digest=None` auf allen 8 rtfestimate-Zeilen der Box).

## Alternativen

1. **Image-Label `org.opencontainers.image.revision` abfragen** —
   präziser (Commit-SHA), aber nur über `GET /images/{name}/json`
   erreichbar; der docker-socket-proxy whitelisted standardmäßig nicht
   die Images-Route. Umbau der Proxy-Whitelist = größerer Eingriff.
2. **ImageID aus `/containers/json` (gewählt)**: bereits whitelisted
   (CONTAINERS), stabil pro Image, wechselt bei Backend-Update. Der
   config-Digest ist ein ehrliches Änderungssignal — die Invalidation
   muss nicht wissen, WAS sich änderte, nur DASS.
3. **Kein Digest** (Status quo) — verworfen: Backend-Wechsel mischt
   veraltete Stichproben in die ETA-Schätzung.

## Offene Fragen

Keine. Verifikation: Unit-Tests (Mock), CI test-webapp, Live-Check der
`digest`-Spalte nach dem nächsten Backend-Deploy auf der Box.
