# Change 175 — crispr-sep: htdemucs GPU-Graph aktivieren

**Status:** Proposed

## Befund (2026-08-31, Live + Code)

htdemucs läuft in CrispASR nur mit dem GPU-Graphen, wenn
`CRISPASR_HTDEMUCS_GPU=1` gesetzt ist (src/htdemucs.cpp:634-637) — der
Default ist CPU (`core_cpu_backend::init()`). Der sep-Container setzte
das Flag nie → htdemucs lief auf CPU: RTF ~7,4 auf der 3090 Ti
(25 min / 202 s Audio) trotz CUDA-Build. mel-band-roformer hat keinen
GPU-Pfad (komplett CPU-Loops, `p.use_gpu = false // Phase 1`).

## Lösung

`CRISPASR_HTDEMUCS_GPU=1` in der sep-Container-Env (compose.gpu.yml).
Upstream-PR (CrispStrobe/CrispASR) macht GPU zum Default.

## Betroffene Dateien

- `compose.gpu.yml`
