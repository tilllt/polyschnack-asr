# Change 030 — Benchmark-Selbstbedienung: Paket-Download, Ergebnis-Submit, Auto-Run, echte CV-Samples, qwen3/ark

## Problem

1. **Benchmark-Daten müssen manuell eingespielt werden:** Das Webapp-Volume
   (`versions/vN`) ist auf der Box leer; Ergebnisse (`latest.json`) kommen
   nur über manuelles `docker compose run benchmark` oder händisches
   Einspielen von Tarballs (Zipline). Es gibt keinen Weg für ein Backend,
   sich das Benchmark-Set selbst zu holen und seine Ergebnisse selbstständig
   zurückzumelden.
2. **Keine Integritätsprüfung:** Niemand kann nachweisen (oder prüfen), dass
   ein gemeldetes Ergebnis wirklich gegen das aktuelle Benchmark-Set gelaufen
   ist. Für die Glaubwürdigkeit der Vergleichs-Matrix (und gegen
   „Benchmark-Gaming") fehlt ein Hash des getesteten Pakets.
3. **qwen3 und ark sind die vielversprechendsten Backends (User-Bewertung:
   „zwei der besten ASR-Modelle"), laufen aber nicht:** qwen3
   (qwen3-asr-0.6b, Server kam auf vast 2× nicht hoch — 1500 s Timeout,
   Container-Logs nie gesehen) und ark (ark-asr-3b, Server läuft, liefert
   aber ~80 % leere/englische Halluzinationen und bricht mit
   `'utf-8' codec can't decode byte 0x8e` ab).
4. **Die „CommonVoice"-Kategorien im Benchmark-Set sind TTS:** Die 24
   `common_voice/cv_*.wav` sind synthetisch (edge-tts de-DE-KatjaNeural —
   eine Stimme), kein einziges SHA-Match mit den echten MDC-Downloads in
   `data/cv/` (46 Clips, Auswahl `cv_selection_v1.json`, 46/46 deckungs-
   gleich). 136 der 210 Samples basieren damit auf TTS statt auf echten
   Sprecherstimmen. Alle bisher gemessenen WER-Werte gelten für synthetische
   Sprache.

## Ziel

1. **Selbstbedienungs-Endpunkte in der Webapp** (`routers/benchmark.py`):
   - `GET /api/benchmark/package` — Tarball der aktuellen Version
     (manifest.json + audio/*.wav + preview/*.mp3) mit SHA-256 im Header
     `X-Benchmark-SHA256`.
   - `GET /api/benchmark/package/sha256` — nur der Hash (leichtgewichtig,
     für Vorab-Prüfung).
   - `POST /api/benchmark/submit` — Backend meldet Ergebnisse selbstständig
     (erstmal **offen**, Security später): validiert `manifest_version` +
     `manifest_sha256` gegen die aktuelle Version (Mismatch → 409),
     schreibt Detail-Zeilen nach `results/runs/<backend>_<ts>.json` und
     aktualisiert `results/latest.json` + `pricing.json`.
2. **Auto-Run-Parameter** im Benchmark-Container: `benchmark_selfservice.py`
   — zieht Paket (`--submit-url`/`BENCH_SUBMIT_URL`), transkribiert über
   eine OpenAI-kompatible Backend-URL, berechnet WER/CER/RTF und submitet
   das Ergebnis inkl. Paket-Hash. Ein neues Backend startet damit:
   `run --rm benchmark --backend <name> --url <backend-url> --submit <webapp-url>`.
3. **qwen3 + ark ans Laufen bringen** (GPU-Debugging auf vast mit
   Container-Logs): Server-Start fixen (qwen3), leere/englische Ausgaben +
   UTF-8-Bruch fixen (ark, vermutl. Sprach-/Response-Parameter), dann beide
   als aktive Backends in `backends.yaml` belassen (bereits registriert).
4. **Echte CV-de-Samples ins Benchmark-Set:** Kategorien neu bauen aus den
   46 echten Clips (`cv/common_voice_de_*.mp3` + `cv_selection_v1.json`):
   clean (8) + 13 Kanal-Kategorien (telefon, strassenlaerm, babble,
   komprimiert, oepnv, flugzeug, auto, hubschrauber, hall, radio,
   schallplatte, tonband, film — je 8, via Degradation aus den 15
   clean-Clips, 2-Achsen-Prinzip), akzent (8 aus 19), kinder (8 aus 12
   jugend-Näherung). Die 7 TTS-Inhalts-Kategorien (schnell, zahlen, medizin,
   jura, mixed, funk, pa) bleiben (CV-de liefert keine Fachtexte).
5. **Kompletter Benchmark-Neulauf für ALLE Backends** (ps-pk-onnx,
   crispr-pk-cpp, crispr-moonshine-de, crispr-canary, crispr-voxtral,
   crispr-whisper, crispr-qwen3, crispr-ark) gegen das neue Set — die
   Backends submitten dabei über den neuen Endpunkt (realer End-to-End-Test).
   Ergebnis: neues Webapp-Paket (Zipline + Hermes-Verzeichnis) + frische
   WER-Tabelle.

## Was sich für Nutzer/Entwickler ändert (Verhaltens-Delta)

- Benchmark-Container: neue Parameter (`--submit-url`, `BENCH_SUBMIT_URL`,
  `BENCH_AUTO_SUBMIT`); nach einem Lauf werden Ergebnisse automatisch an die
  Webapp gepostet statt nur ins Volume geschrieben.
- Neue öffentliche Routen: `GET /api/benchmark/package[/sha256]`,
  `POST /api/benchmark/submit` (Submit vorerst ohne Auth — Sicherheit
  eigener Change, User-Entscheid).
- Benchmark-Set: 194 Samples (statt 210), davon 128 aus echten
  CommonVoice-de-Stimmen; WER-Werte ändern sich (echte Stimmen sind für ASR
  i. d. R. schwerer als TTS).
- Bekanntmachung im `/benchmark`-Frontend: Methodik-Text aktualisiert
  („CommonVoice-de echte Sprecher + TTS-Inhaltskategorien").

## Abgrenzung / Ehrlichkeit

- Kein Auth für Submit in diesem Change (offen laut User: „die security
  relevanten überlegungen regeln wir später"). Kein neues Frontend für die
  Submit/Download-Routen (nur API). Keine Walzen in die Kategorien
  (Vintage bleibt eigener Change; Walzen haben keine Referenztexte).
- qwen3/ark-Fixes sind empirisch (GPU-Instanz) — falls ein Backend trotz
  Debugging nicht lauffähig wird, wird das im Change transparent berichtet
  und das Backend auf `status: disabled` gesetzt (nicht gelöscht).
- Der Hash ist ein SHA-256 über das deterministisch sortierte Paket
  (manifest.json-Bytes + je Audio-Datei sha256, verkettet) — Version
  vN-gebunden, kein kryptografischer Zertifizierungs-Dienst.

## Specs-Delta

`ADDED` — `specs/engineering/spec.md`: REQ-WEB-039 (Package-Download),
REQ-WEB-040 (SHA-256), REQ-WEB-041 (Submit), REQ-WEB-042 (Auto-Run),
REQ-WEB-043 (CV-Samples), REQ-WEB-044 (qwen3/ark-Lauffähigkeit).
