# Change 165 — Tasks

- [x] Befund: Logs 16946/16948 (Index-Push-Fehler, NotFound 5cc4a07),
      GHCR-Zustand == Harbor (config 8e5c2b44) → Inhalt bereits korrekt.
- [x] `resolve_digest` gegen echte Harbor-Images getestet: `-sep` (Index
      → amd64-Child), `-asr`/`-webapp`/`-diar` (Single → Descriptor).
- [x] `.gitlab-ci.yml` `mirror-ghcr` umgebaut (Digest-only, kein
      Tag-Fallback, lauter Abbruch ohne Digest).
- [x] openspec/change 165 committen, push main.
- [ ] Pipeline: `mirror-ghcr` grün (auch SHA-Tag-Zweig, wenn gebaut).
- [ ] Change 164-Pipeline: bleibt rot NUR am alten mirror-Job
      (GHCR-Inhalt bereits korrekt) — kein weiterer Retry mit altem Code.
