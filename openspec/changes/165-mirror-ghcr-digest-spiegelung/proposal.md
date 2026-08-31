# Change 165 — mirror-ghcr: deterministische Digest-Spiegelung (kein Tag-Fallback)

**Status:** Proposed

## Befund (2026-08-31, Pipeline 4752 + Retry 16948)

- `mirror-ghcr` schlug zweimal fehl beim Spiegeln von
  `polyschnack-asr-webapp:latest`:
  `manifest list/index references multiple platform specific manifests …
  NotFound: content digest sha256:5cc4a07…: not found`.
- Ursache: Bei Single-Plattform-Images (`polyschnack-asr`, `-webapp`;
  Harbor liefert `application/vnd.docker.distribution.manifest.v2+json`)
  hat `docker manifest inspect` kein `manifests`-Feld → die
  amd64-Auflösung bleibt leer → Fallback `docker pull src:tag` +
  Tag-Push. Ist der Runner-Daemon-Tag stale (älterer Multi-Arch-Index
  mit attestation/unknown-Child), pusht das Skript diesen Index; GHCR
  lehnt ab, weil ein Child-Manifest dort fehlt. Der eigentliche Inhalt
  war bereits korrekt gespiegelt (GHCR-config `8e5c2b44` == Harbor).
- Gleiche Klasse wie Change 164: stiller Fallback verdeckt den
  Ist-Zustand und pusht ggf. veralteten Stand.

## Lösung

1. Neue Helper-Funktion `resolve_digest <src> <ref>`: liefert IMMER eine
   explizite Manifest-Digest —
   - Index (Multi-Arch): `linux/amd64`-Child-Digest;
   - Single-Plattform-Manifest: eigene Descriptor-Digest
     (`docker manifest inspect --verbose`).
2. `mirror_one` pullt/taggt/pusht ausschließlich per Digest
   (`src@digest`). Kein `docker pull src:tag`-Fallback mehr — ein stale
   Daemon-Tag kann nie mehr gepusht werden.
3. Keine auflösbare Digest → Job bricht laut mit Fehlermeldung ab
   (statt still weiterzulaufen).

## Tests

- `resolve_digest` gegen echte Harbor-Images geprüft: Index (`-sep` →
   amd64-Child), Single (`-asr`, `-webapp`, `-diar` → Descriptor-Digest).
- Pipeline auf main: `mirror-ghcr` grün trotz vorhandener
   Single-Plattform-Images.
