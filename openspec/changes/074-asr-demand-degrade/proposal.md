# Change 074 — ASR-Testset mit echtem DEMAND degraden

**Status:** in Arbeit · **Datum:** 2026-08-21

## Problem

User (2026-08-21): „Wir hatten besprochen, dass wir auch das ASR-Sampleset
mit DEMAND degraden wollten.“

Belegt (Code): Die Kanal-Kategorien des ASR-Testsets (strassenlaerm, babble,
oepnv, flugzeug, auto, hubschrauber, hall, radio, schallplatte, tonband,
film — `polyschnack-benchmark/benchmark/scripts/prepare_cv_real.py`,
`KANAL_KATEGORIEN` + `_gen_noise`) sind **synthetisch** degradiert:
ffmpeg `anoisesrc` (Pink-Noise) + Filter (Lowpass, Wow/Flutter, Vinyl…).

Das VAD-Testset (V3.1, Change 062/064/065) nutzt dagegen **echtes DEMAND**
(`build_testset_v3.py` `add_snr_variants`): Küche (DKITCHEN) + Metro
(TMETRO), 300 s, 16 kHz, überlagert bei SNR 0/5/10 dB, exakte GT bleibt.
Diese Lücke schließt Change 074 für das ASR-Set: echte Umweltgeräusche
statt synthetischem Rauschen.

## Befund / Fakten

1. **Quellen lokal vorhanden:** `benchmarks/vad/assets/demand/`
   - `DKITCHEN_16k.zip` + `DKITCHEN_16k_sample.wav` (16 Kanäle, 300 s, 16 kHz)
   - `TMETRO_16k.zip` + `TMETRO_16k_sample.wav` (16 Kanäle, 300 s, 16 kHz)
2. **DEMAND-Kategorien:** DEMAND umfasst 18 Umgebungen (DKITCHEN, DLIVING,
   DWASHING, DMEETING, DOFFICE, DPARK, DRIVER, DSTATION, DTRAIN, DTRAFFIC,
   DBUS, DCAR, DMETRO, DPEDESTRIAN, DCAFE, DRESTAURANT, DTPHONE, DSTREET).
   **Kein Flugzeug, kein Hubschrauber** — diese beiden ASR-Kanalkategorien
   können nicht mit DEMAND abgedeckt werden (Scope-Frage, s. u.).
3. **Mapping-Vorschlag (ASR-Kanal → DEMAND):**
   - `strassenlaerm` → DTRAFFIC (Straßenverkehr)
   - `auto` → DCAR (Fahrzeuginnenraum)
   - `oepnv` → DTRAIN / DSTATION / DMETRO (Zug / Bahnhof / U-Bahn)
   - `babble` → DCAFE / DRESTAURANT (Stimmengewirr) oder bleibt synthetisch
   - `telefon` → bleibt (Codec-Kette, kein Geräusch)
   - `komprimiert` → bleibt (Codec-Kette, kein Geräusch)
   - `hall` / `radio` / `schallplatte` / `tonband` / `film` → bleiben
     (Effekt-Ketten, keine Umgebungsgeräusche)
4. **Auswirkung auf Ergebnisse:** Das ASR-Testset ist versioniert
   (aktuell v2, 207 Samples, 7 Backend-Ergebnisse). Echte DEMAND-Degradation
   ändert die Audios der betroffenen Kategorien → **neue Testset-Version
   (v3) + Neu-Lauf der ASR-Benchmarks** für vergleichbare Zahlen.

## Ziel

1. ASR-Kanalkategorien mit DEMAND-Abdeckung auf **echte** Umweltgeräusche
   umstellen (SNR-Mix wie im VAD-Build, exakte GT unverändert).
2. Flugzeug/Hubschrauber: entweder synthetisch belassen (dokumentiert) oder
   aus anderer Quelle (MUSAN/FSD50K) — **User-Entscheidung**.
3. Neues Testset v3 (Versionierung), Neu-Lauf der Backend-Benchmarks,
   Release-Artefakt mit Provenienz (analog VAD-Release v4).

## Offene Fragen (User)

1. **Flugzeug/Hubschrauber:** synthetisch belassen oder andere Quelle?
2. **DEMAND-Kategorien besorgen:** nur die 2 lokalen (Küche/Metro) reichen
   für strassenlaerm/auto/oepnv nicht — Download weiterer DEMAND-Kategorien
   (Zenodo/offiziell) nötig, oder Mapping auf Küche/Metro beschränken?
3. **Neu-Lauf:** alle 7 ASR-Backends neu messen (207 Samples × 7)?

## Umsetzung (Skizze)

1. `prepare_cv_real.py`: `_gen_noise`/`_add_noise` für DEMAND-Kategorien
   durch `_add_demand_snr` ersetzen (VAD-Logik übernehmen: RMS-Skalierung,
   SNR 0/5/10 dB, exakte GT).
2. Neue Testset-Version bauen (v3), Release-ZIP + SHA (analog VAD v4),
   Provenienz dokumentieren.
3. Backend-Benchmark-Läufe gegen v3 (207 Samples × 7 Backends), Submits,
   Seite zeigt aktualisierte ASR-Ergebnisse.

## Tests / Verifikation

- Degrade-Funktion: Mix = Sprache + DEMAND bei Ziel-SNR (WAV-Analyse);
  GT-Regionen unverändert (F1/GT-Integrität).
- Testset v3: Sample-Zahlen je Kategorie korrekt, Determinismus
  (gleicher Seed → gleiche WAVs).
- Nach Neu-Lauf: `/api/benchmark/results` zeigt aktualisierte ASR-Zeilen
  mit Testset-Version v3.
