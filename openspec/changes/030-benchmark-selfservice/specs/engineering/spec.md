# Engineering-Spec — Change 030

## REQ-WEB-039 — Benchmark-Paket-Download (`GET /api/benchmark/package`)

1. Liefert einen Tarball (`.tar.gz`) der aktuellen Benchmark-Version:
   `manifest.json`, `audio/*.wav`, `preview/*.mp3` — Determinismus: Dateien
   im Tarball alphabetisch sortiert, keine Timestamps in den Member-Headern
   (mtime = 0).
2. SHA-256 des Pakets wird im Response-Header `X-Benchmark-SHA256`
   mitgeliefert (Format: `v<N>:<sha256-hex>`).
3. Ist keine Version vorhanden → 404. Der Tarball wird bei jedem Request
   frisch gebaut (kleines Set, ~40 MB); Cache ist erlaubt, solange
   `X-Benchmark-SHA256` korrekt bleibt.

## REQ-WEB-040 — Paket-Hash (`GET /api/benchmark/package/sha256`)

1. Liefert `{"version": <int>, "sha256": "<hex>", "manifest_version": <int>}`
   — leichtgewichtig, damit ein Backend vor dem Download prüfen kann, ob es
   das Set bereits hat.
2. Hash-Definition (deterministisch, version-gebunden): über die sortierten
   Member `manifest.json` (Bytes) und `audio/<id>.wav` (Bytes) wird
   SHA-256 der Verkettung `sha256(manifest) + sha256(wav1) + …` gebildet.

## REQ-WEB-041 — Ergebnis-Submit (`POST /api/benchmark/submit`)

1. Request-Body (JSON):
   `{backend, settings, manifest_version, manifest_sha256, run_id,
   generated_at, rows: [{sample_id, hyp, wer, cer, coverage_pct, rtf}],
   meta: {n_audio_s, backend_version}}` — `hyp` optional (nur fürs Log).
2. Validierung: `manifest_version` + `manifest_sha256` müssen der aktuellen
   Version entsprechen; sonst 409 mit `{ok: false, reason: "manifest
   mismatch", current: {…}}`. Unbekannter `backend` → 422 (Registry-Check
   gegen `backends.yaml`).
3. Persistenz: Detail-Zeilen nach `results/runs/<backend>_<yyyyMMdd-HHmmss>.json`;
   danach Re-Pooling von `results/latest.json` (WER/CER/coverage/RTF über
   alle Runs des Backends mit aktuellem Hash) + `pricing.json`-Update
   (RTF-basiert, `BACKEND_COST_ASSUMPTION` aus run_container.py).
4. Auth: **offen** (kein Login) — Security eigener Change (User-Entscheid).

## REQ-WEB-042 — Auto-Run: Backend führt Benchmark selbstständig aus

1. `benchmark_selfservice.py` (im Benchmark-Image):
   `--backend NAME --url <openai-kompatible-base-url> --submit
   <webapp-origin> [--workdir <tmp>]` — Ablauf: (a) `GET /api/benchmark/
   package/sha256` → lokal vorhanden? sonst Paket laden+entpacken; (b) alle
   aktiven Samples gegen `--url/v1/audio/transcriptions` transkribieren;
   (c) WER/CER/RTF berechnen (jiwer, normalisiert wie run_container.py);
   (d) `POST /api/benchmark/submit`.
2. `run_container.py` erweitert: Env `BENCH_SUBMIT_URL`/`BENCH_AUTO_SUBMIT`
   — nach lokalem Lauf werden die gemessenen `rows` (inkl. `hyp`) an den
   Submit-Endpunkt gepostet statt nur `latest.json` ins Volume zu schreiben.
3. Exit-Codes: 0 = submitet, 2 = Backend nicht erreichbar, 3 = Hash-Mismatch
   (Server 409), 4 = Abbruch durch Timeout.

## REQ-WEB-043 — Echte CommonVoice-de-Samples im Benchmark-Set

1. Quellen: `benchmark/data/cv/common_voice_de_*.mp3` (46 echte Clips aus
   dem MDC-tar, Task A1) + `benchmark/selection/cv_selection_v1.json`
   (Texte, accent/age-Labels).
2. Kategorien: clean (8) und 13 Kanal-Kategorien (telefon, strassenlaerm,
   babble, komprimiert, oepnv, flugzeug, auto, hubschrauber, hall, radio,
   schallplatte, tonband, film — je 8) aus den 15 clean-Clips (Degradation
   wie bisher: lowpass/resample, Verkehr, Babble, Kompression, …);
   akzent 8 aus 19; kinder 8 aus 12 (jugend-Näherung, Label dokumentiert).
3. Die 7 TTS-Inhalts-Kategorien bleiben unverändert (schnell, zahlen,
   medizin, jura, mixed, funk, pa). Kategorie `historisch` entfällt aus dem
   aktiven Set (Walzen ohne Referenztexte — Vintage eigener Change).
4. Manifest/Methodik: `source`-Feld je Sample (`cv`/`tts`), Methodik-Text
   nennt „CommonVoice-de (echte Sprecher) + TTS-Inhaltskategorien";
   `cv_selection_v1.json` wird referenziert (Auswahl deterministisch,
   seed 42).

## REQ-WEB-044 — qwen3 + ark lauffähig (GPU-verifiziert)

1. qwen3: Server-Start auf GPU-Instanz debuggen (Container-Logs sichern!):
   Modell-Download (OpenVoiceOS GGUF), CUDA-Backend-Wahl, Healthcheck.
   Kriterium: `/v1/audio/transcriptions` beantwortet ≥ 195/194 Samples
   innerhalb des Suite-Timeouts.
2. ark: leere/englische Ausgaben + UTF-8-Bruch beheben (CrispASR-ark-Params:
   Sprache, response_format, gguf-Wahl). Kriterium: WER < 0,30 auf dem
   CV-Set, kein `utf-8`-Decode-Fehler.
3. Beide Backends bleiben `status: active`; falls ein Backend nicht
   lauffähig wird: `status: disabled` + Begründung im Change.
