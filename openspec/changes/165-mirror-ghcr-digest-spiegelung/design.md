# Change 165 — Design

## Problemklasse

Der Mirror-Job verlässt sich auf einen Tag-Fallback (`docker pull src:tag`
+ Push), wenn die amd64-Auflösung aus dem Index leer bleibt. Der lokale
Daemon-Zustand (stale Tags von früheren Läufen) bestimmt dann, was gepusht
wird — nicht der Registry-Ist-Zustand. Set-e-Hüllen (`|| true`) auf
inspect/pull verhindern, dass der Fehler sichtbar wird; der Push scheitert
dann erst mit kryptischer NotFound-Meldung.

## Alternativen

1. **Runner-Daemon prunen** — behandelt nur das Symptom (der Runner ist
   extern, nicht erreichbar) und verhindert die Regression nicht.
2. **Job nochmal retryen** — belegt: konsistent fehlgeschlagen
   (4752 + Retry 16948), Daemon-Zustand persistiert.
3. **Digest-only-Spiegelung (gewählt)**: Pull/Tag/Push immer per explizit
   aufgelöster Digest. Deterministisch, unabhängig vom Daemon-Zustand.
   Single-Plattform-Images (Harbor docker-built) und Multi-Arch-Indizes
   (buildx/attestation, z. B. `-sep`) werden gleich behandelt; ein Index
   wird nie als Ganzes gepusht (nur der `linux/amd64`-Child), was die
   attestation/unknown-Einträge gar nicht erst nach GHCR trägt.

## Offene Fragen

Keine. Verifikation: Parsing gegen echte Harbor-Images (Index + Single)
auf dem Hermes-Host durchgeführt; Pipeline-Lauf als End-to-End-Beweis.
