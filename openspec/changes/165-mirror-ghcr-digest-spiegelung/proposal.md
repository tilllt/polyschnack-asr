# Change 165 — mirror-ghcr: deterministische Digest-Spiegelung (kein Tag-Fallback)

**Status:** Proposed

## Befund (2026-08-31, Pipelines 4752/4754 + Retry)

- `mirror-ghcr` schlug wiederholt beim Spiegeln von
  `polyschnack-asr-webapp:latest` fehl:
  `manifest list/index references multiple platform specific manifests …
  NotFound: content digest sha256:5cc4a07…: not found`.
- Nach dem Digest-Fix (resolve_digest → `sha256:42c9bc…`) blieb der Fehler:
  `5cc4a07` ist KEIN Index-Child, sondern ein **Layer-BLOB** des
  Single-Manifests (12 Layer). Der Runner-Daemon (extern, shared) sammelt
  über den Tag hinweg Images aller Pipelines; ein voller Daemon lässt
  `docker pull` Blobs unvollständig laden (Fehler wurde mit
  `>/dev/null 2>&1` verschluckt), und `docker push` scheitert dann mit
  NotFound auf dem fehlenden Layer. Der GHCR-Inhalt selbst war bereits
  korrekt (config `8e5c2b44` == Harbor).

## Lösung

1. `docker system prune -af` vor der Loop — Daemon-Zustand deterministisch
   (unbenutzte Images/Caches weg; laufende Jobs anderer Pipelines bleiben
   unberührt).
2. `resolve_digest <src> <ref>`: IMMER eine explizite Manifest-Digest —
   Index (Multi-Arch) → `linux/amd64`-Child; Single-Plattform-Manifest →
   eigene Descriptor-Digest (`--verbose`).
3. `mirror_one` pullt/taggt/pusht ausschließlich per Digest
   (`src@digest`). Kein Tag-Fallback — ein stale Daemon-Tag kann nie mehr
   gepusht werden.
4. Pull-Fehler sind NICHT mehr verschluckt: fehlgeschlagener Pull bricht
   den Job laut mit Meldung ab (kein stiller Push eines unvollständigen
   Daemons).
5. `docker rmi` nach jedem Push — die Runner-Disk reicht nicht für alle
   13 Backend-Images gleichzeitig (Befund: 12/13 gepusht, das letzte
   scheiterte an fehlendem Layer `de44b265`). `docker system df` vor der
   Loop macht den Disk-Zustand im Log sichtbar.

## Tests

- `resolve_digest` gegen echte Harbor-Images geprüft: Index (`-sep` →
   amd64-Child), Single (`-asr`, `-webapp`, `-diar` → Descriptor-Digest).
- Pipeline auf main: `mirror-ghcr` grün trotz vorhandener
   Single-Plattform-Images.
