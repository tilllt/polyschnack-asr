# Change 177 — htdemucs: GPU-Pfad braucht drei Flags (GGML+FUSED fehlten)

**Status:** Proposed

## Befund (2026-08-31, Live)

Change 175 setzte nur `CRISPASR_HTDEMUCS_GPU=1` — der Prozess lief
trotzdem auf CPU (103 % CPU, 0 % GPU-Util über 10 s dmon, RTF-Muster
25 min / 202 s Audio). Ursache im CrispASR-Code:

- `htdemucs_use_ggml()` (src/htdemucs.cpp:968-974) ist **default OFF**
  und braucht `CRISPASR_HTDEMUCS_GGML=1`
- Die GPU-Weiche: `if (want_gpu && htdemucs_use_ggml())` (Z. 647) —
  ohne GGML-Flag läuft IMMER der CPU-Pfad
- `CRISPASR_HTDEMUCS_FUSED` (default OFF, setzt _GGML voraus): ohne
  FUSED zahlen die Per-Layer-Graphen host↔device-Roundtrips und sind
  laut Code-Kommentar teils LANGSAMER als CPU+Accelerate

Zusätzlich war der Change-175-„GPU-Test" fehlinterpretiert: 30-s-Clip ×
RTF 7,4 ≈ 222 s — knapp im 240-s-Timeout durchgelaufen, also auch CPU.

## Lösung

Alle drei Flags in der sep-Container-Env (compose.gpu.yml):
`CRISPASR_HTDEMUCS_GPU=1` + `CRISPASR_HTDEMUCS_GGML=1` +
`CRISPASR_HTDEMUCS_FUSED=1`.

## Betroffene Dateien

- `compose.gpu.yml`
