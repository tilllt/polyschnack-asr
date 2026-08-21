# Change 065 — Webapp-Benchmark auf V3.1-Testset: Paket-Import + Testset-Version

**Status:** in Arbeit · **Datum:** 2026-08-21

## Problem

- Die Webapp generiert ihr VAD-Benchmark-Paket (`build_vad_package`)
  weiterhin **aus dem ASR-Manifest** (`versions/v{N}/audio/`) mit eigener
  Stille-Insertion (lead2/trail2/both2/mid1) — das ist die V2-Methodik
  (Change 062). Das **V3.1-Testset** (Change 064: 235 public Samples mit
  Common-Voice-Basis + DEMAND-SNR-Mixen + Noise/Musik-FP) ist nur im
  `benchmarks/`-Bereich und als GitHub-Release v4 verfügbar.
- Submitter-Container laden das Paket über `/api/benchmark/vadpackage` —
  sie messen also gegen ein **anderes Set** als die offiziellen
  V3.1-Ergebnisse (Silero public F1 0,995). Ein Submit gegen das echte
  V3.1-Set würde heute mit **409 (manifest mismatch)** abgelehnt.
- Die Benchmark-Seite zeigt keine **Testset-Version/Provenienz** — externe
  User können nicht erkennen, auf welchem Set ein Ergebnis basiert.

## Ziel

1. **VAD-Paket = V3.1-public**: `build_vad_package` importiert das
   GitHub-Release-Artefakt v4 (`vad-benchmark-v3.1-public.zip`, SHA256
   verifiziert) statt aus dem ASR-Manifest zu generieren. Download-Fallback
   (Release) mit lokalem Cache; held-out-Samples sind im Artefakt nicht
   enthalten (Guard bereits in `assemble_release_zip.py`).
2. **`testset_version`-Feld**: Run-JSON + `_vad_summary` + UI tragen die
   Testset-Version (z. B. `v3.1-public`, Release-Link, Sample-Anzahl) —
   Submitter müssen nichts ändern, die Webapp setzt das Feld aus dem Paket.
3. **UI**: VadResultsTable zeigt Testset-Version + Link auf Release
   (tilllt/vad-benchmark-data) + PROVENANCE.md; weiterhin Lizenz-Hinweis.
4. ASR-Pool bleibt unberührt (kind-Trennung, Change 062).

## Verhaltens-Delta (IST → SOLL)

- `GET /api/benchmark/vadpackage` liefert künftig das **V3.1-public-Paket**
  (235 Samples, CV + SNR + FP) statt des ASR-Manifest-basierten Pakets;
  `X-Benchmark-SHA256` = Hash des neuen Pakets.
- `GET /api/benchmark/vadpackage/sha256` → zusätzlich
  `testset_version: "v3.1-public"` + `release_url`.
- `_vad_summary` aggregiert wie gehabt (kind=="vad", manifest_sha256),
  ergänzt aber `testset_version` je Run.
- Frontend-Benchmark-Seite: VAD-Sektion zeigt Version/Link; Leer-Hinweis
  bleibt („Noch keine VAD-Ergebnisse").

## Umsetzung (Skizze)

1. `benchmark_service.py`: `build_vad_package` → lädt ZIP vom Release v4
   (urllib, SHA256-Check gegen bekannten Hash; Cache unter
   `versions/v{N}/vad/v3.1/`), mappt `testset.json`-Samples auf das
   vad-manifest-Schema (id, source, variant, gt), kopiert WAVs;
   `testset_version` aus dem Release-Tag; `vad_package_sha256` unverändert
   (Hash über Manifest + WAVs).
2. `routers/benchmark.py`: `vadpackage/sha256` + `vadpackage` Header um
   `testset_version`/`release_url` ergänzen; Submit-Schema akzeptiert
   `testset_version` (optional, aus Paket gesetzt).
3. `benchmark.ts`/`BenchmarkPage.tsx`: VadResultRow + `testset_version`/
   `release_url`; Anzeige über der Tabelle.
4. Tests: Backend (Paket-Import, SHA-Konstanz, testset_version im
   Summary), Frontend (Anzeige) — Vollsuite + tsc + build.
5. Commit + Push + CI; danach echte VAD-Submits (BENCHMARK_API_KEY jetzt
   lokal vorhanden) gegen das V3.1-Paket.

## Referenzen

- V3.1-Artefakt: `tilllt/vad-benchmark-data` Release v4,
  `vad-benchmark-v3.1-public.zip` (SHA256 `b48bb9e9…`), PROVENANCE.md
- Change 062: VAD-Paket-Flow (vadpackage-Endpoint, kind-Trennung)
- Change 064: Testset-Builder, Split, ZIP-Assembly
- **Live-Befund (2026-08-21, whisper.cia-spandau.de):** `GET
  /api/benchmark/vadpackage/sha256` → **HTTP 500** im Produktionsstand
  (Change 062, alter `build_vad_package`: ffmpeg-Generierung je Sample aus
  dem ASR-Manifest). Vermutlich crasht eine kaputte/fehlende Sample-WAV
  oder ein ffmpeg-Fehler den Endpoint → VAD-Submitter können das Paket
  nicht holen, VAD-Sektion bleibt leer. Change 065 ersetzt die Generierung
  durch ZIP-Import (kein Sample-Konvertierungs-Risiko) → behebt den 500er.
