# Change 079 — Benchmark-Testset-Qualität + Benchmark-GUI

## Problem

Der User meldet (2026-08-21) eine Liste von Defiziten am Benchmark-Testset
und an der Benchmark-GUI:

1. **PA-Kategorie komplett stumm**: alle 18 `pa_*.wav` haben rms ≈ 0,0005–0,002
   (praktisch Stille, 0 % Aktivität).
2. **Auto**: synthetische Degradation teils entfernt, keine natürliche
   stattdessen → `auto_cv_clean_*` klingen clean.
3. **Tonband**: Gleichlaufschwankungen fehlen (`wow_flutter` ist nur ein
   Resampling, keine echte Wow/Flutter-Modulation) und müssten stärker sein.
4. **Schallplatte**: kein Knacken mehr (peaks > 0,5: 0–3 statt erwarteter ~15
   Impulse bei 3/s × 5 s).
5. **Mixes mit natürlichen Geräuschen**: Störgeräusch-Lautstärke muss aus der
   **gemessenen RMS des Samples** abgeleitet werden (nicht aus ungeprüften
   ffmpeg-amix-Weights).
6. **Synthetische Störungen insgesamt zu dezent** — Ziel sind Edge Cases.
7. **Piper-Stimme „Ramona"** (LOW-Modell) spricht viele Begriffe falsch und
   ist kaum verständlich.
8. **Benchmark-GUI**: viele Samples lassen sich nicht abspielen.
9. **Statistik-Graphen fehlen** (pro Kategorie und pro Sample — gab es früher).

## Root Causes (gemessen, nicht geraten)

- **PA stumm** (`prepare.py` Z. 627): `bandpass=f=1000:w=500` — ffmpeg
  interpretiert `w` standardmäßig als **Q-Faktor** (`width_type` Default
  `q`), nicht als Bandbreite in Hz → ultra-schmaler Filter → −45 dB.
  Messung: `pa_distortion` allein reduziert rms 0,1475 → 0,0008;
  mit `width_type=h:w=500` bleibt rms 0,032 (hörbar).
- **wow_flutter** (Z. 648): `asetrate=44100,aresample=48000,atempo=1.088`
  = reines Resampling (Pitch+Speed), **keine** periodische
  Gleichlaufschwankung. Messbar: keine F0-Modulation.
- **vinyl_crackle** (Z. 641/756): nur 3 Impulse/s bei Amplitude 0,3,
  gemischt mit SNR 12 → messbar fast keine Klicks.
- **SNR-Mix** (`_mix_audio_at_snr` Z. 366): amix `weights=` setzt SNR nur
  voraus; die tatsächliche SNR hängt von der RMS beider Signale ab, die
  nie gemessen wird → SNR weicht vom Zielwert ab.
- **Ramona**: `scripts/regenerate_tts_piper.py` nutzt das Piper-LOW-Modell
  „Ramona" für ungerade Indizes (Kommentar im Skript: kein
  Ramona-medium im offiziellen Modellbaum).
- **GUI-Abspielen**: Produktions-Webapp läuft auf Stand `4810331` — der
  Playback-Fix aus Change 077 (`interact:false` + `canPlayRef`-Gate) ist
  **nicht deployed** → „Cursor läuft, kein Ton"-Bug tritt weiterhin auf.
- **Graphen**: `CategoryQualityChart`/`CategoryQualityCharts` + Sample-Mini-
  Balken **existieren im Code** (Change 039/040/051), aber das Produktions-
  `results`-Artefakt ist leer (190 B, kein `per_category`/`per_sample`) →
  Graphen rendern „Noch keine Kategorie-Ergebnisse". Daten fehlen, nicht Code.

## Lösung

### Testset (polyschnack-benchmark, `benchmark/prepare.py`)

- **T1 PA**: `bandpass` mit explizitem `width_type=h:w=500` (Bandbreite in
  Hz statt Q) + leichter `asoftclip` — PA-Samples wieder hörbar.
- **T2 SNR-Mechanik**: `_mix_audio_at_snr` misst die RMS von Sprache UND
  Rauschen (numpy/ffmpeg-volumedetect) und skaliert das Rauschen auf
  `speech_rms · 10^(−snr/20)` — exakte Ziel-SNR statt amix-Weights-Raten.
- **T3 wow_flutter**: echte periodische Pitch-Modulation (z. B. via
  ffmpeg `vibrato` auf einer resampleten Kopie oder numpy-Resampling mit
  modulierter Abtastrate), Stärke ~0,5–1 % Wow + leichter Flutter, nach
  User-Vorgabe „viel stärker als vorher".
- **T4 vinyl_crackle**: mehr Impulse (z. B. 8–12/s), höhere Amplitude,
  realistische Klick-Kurve (schneller Abfall), exakteres Mischen über die
  neue SNR-Mechanik.
- **T5 natürliche DEMAND-Mixes**: auto→TCAR, strassenlaerm→STRAFFIC,
  oepnv→TBUS, babble→PCAFETER (Assets liegen in `data/demand/`), SNR nach
  T2-Mechanik gemessen+skaliert.
- **T6 Edge Cases**: zusätzliche/härtere SNR-Stufen (0/3 dB statt nur
  8–15 dB) für Transport- und Vintage-Kategorien.
- **T7 Stimme**: Piper „Ramona" durch Thorsten-medium ersetzen (alle
  Kategorien konsistent), `regenerate_tts_piper.py` anpassen.
- **T8 Regeneration + Verifikation**: Testset neu bauen, jede Kategorie
  messen (rms/Aktivität/Impulse/Wow-Spektrum), Manifest+Hash aktualisieren,
  Tests (`test_prepare_vintage` etc.) grün.

### GUI (pk-asr)

- **T9 Abspielen**: Playback-Fix 077 ist Code-seitig fertig → Deploy
  Webapp-Code 073–078 auf Produktion (User-Aktion/Deploy-Plan), dann
  Live-Verifikation der Benchmark-Player.
- **T10 Graphen**: Ergebnisse erzeugen (ASR-v3-Neu-Lauf 207×7) → füllt
  `per_category`/`per_sample` → Graphen erscheinen. Zusätzlich prüfen, ob
  die Graphen auch ohne Ergebnisse eine sinnvolle Leer-Darstellung zeigen.

## Erfolgskriterien

- [ ] `pa_*.wav`: rms ≥ 0,02, Aktivität > 20 % (vorher 0,0005/0 %)
- [ ] `auto_*`/`strassenlaerm_*`/`oepnv_*`: nachweislich DEMAND-Rauschen
      (TCAR/STRAFFIC/TBUS) im Mix, gemessene SNR ≈ Zielwert ±1 dB
- [ ] `tonband_*`: messbare F0-Modulation (Wow) statt nur Resampling
- [ ] `schallplatte_*`: ≥ 8 Klick-Impulse > 0,5 Amplitude pro 5 s
- [ ] Piper-Samples: keine Ramona-Stimme mehr (alle Thorsten)
- [ ] Testset-Tests grün, Manifest/Hash konsistent
- [ ] Benchmark-GUI: Player läuft nach Deploy (077-Fix live), Graphen
      zeigen Daten nach v3-Lauf
