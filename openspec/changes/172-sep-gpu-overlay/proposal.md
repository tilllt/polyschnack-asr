# Change 172 — crispr-sep in GPU-Overlay (htdemucs braucht CUDA)

**Status:** Proposed

## Befund (2026-08-31, Live-Test Recording 49b7b10a)

`compose.gpu.yml` vergisst `crispr-sep` → der Container läuft immer mit
`runtime: runc` (kein NVIDIA). Jeder htdemucs-Job crasht:
`crispasr: error while loading shared libraries: libcuda.so.1` →
sep-Server meldet 409, `separate_client` fällt aufs Original-Audio
zurück → Aligner verankert auf Musik/Rauschen → `alignment=skipped`.

Kette: Methode A/B liefern nie vocals → „New Word Timestamps" skipped
(„word timestamps not verified") — trotz vorhandenem skipped-Guard
(Change 37: lieber skipped als unverifizierte Zeiten).

## Lösung

`crispr-sep` in `compose.gpu.yml` mit `runtime: nvidia` ergänzen
(analog crispr-align).

## Betroffene Dateien

- `compose.gpu.yml`
