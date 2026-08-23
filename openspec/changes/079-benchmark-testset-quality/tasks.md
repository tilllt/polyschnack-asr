# Tasks — Change 079: Benchmark-Testset-Qualität + GUI

## T1 — PA-Fix: bandpass width_type (Q → Hz)
- [ ] `prepare.py` Z. 627: `bandpass=f=1000:w=500` →
      `bandpass=f=1000:width_type=h:w=500` (+ ggf. asoftclip anpassen)
- [ ] PA-Samples neu bauen, Messung: rms ≥ 0,02, Aktivität > 20 %

## T2 — SNR-Mechanik: RMS-basierte Skalierung
- [ ] `_mix_audio_at_snr`: Speech-RMS und Noise-RMS messen (numpy),
      Noise auf `speech_rms · 10^(−snr/20) / noise_rms` skalieren
- [ ] SNR-Verifikation: gemessene SNR ≈ Zielwert ±1 dB (Test)

## T3 — wow_flutter: echte Gleichlaufschwankung
- [ ] Periodische Pitch-Modulation implementieren (vibrato/Resampling),
      Stärke nach User-Vorgabe „viel stärker"
- [ ] Messung: F0-Modulation nachweisbar (Spektralanalyse)

## T4 — vinyl_crackle: realistische Klicks
- [ ] Impulsrate 8–12/s, Amplitude erhöhen, Klick-Kurve (schneller Abfall)
- [ ] Messung: ≥ 8 Impulse > 0,5 pro 5 s

## T5 — Natürliche DEMAND-Mixes
- [ ] auto→TCAR, strassenlaerm→STRAFFIC, oepnv→TBUS, babble→PCAFETER
- [ ] Mix über T2-Mechanik (RMS-gemessen), SNR je Kategorie definieren

## T6 — Edge Cases: härtere SNR-Stufen
- [ ] SNR 0/3 dB für Transport- und Vintage-Kategorien ergänzen

## T7 — Piper-Stimme: Ramona raus
- [x] `regenerate_tts_piper.py`: nur Thorsten-medium (Ramona-Env optional)
- [x] Korrektur: Ramona-medium EXISTIERT doch (/opt/data/piper-test/) —
      Kommentar im Skript war falsch; trotzdem Wechsel zu Thorsten (User-Vorgabe)
- [ ] TTS-WAVs neu generieren (70 × Thorsten, läuft)

## T8 — Regeneration + Verifikation
- [ ] Testset neu bauen (deterministisch), Kategorien messen
- [ ] Manifest + Hashes aktualisieren, Tests grün (`test_prepare_vintage` etc.)

## T9 — GUI-Abspielen (Deploy)
- [ ] 077-Playback-Fix ist committet → Deploy Webapp 073–078 + env
- [ ] Live-Verifikation Benchmark-Player nach Deploy

## T10 — GUI-Graphen
- [ ] Leer-Darstellung der Graphen ohne Ergebnisse prüfen/verbessern
- [ ] Nach v3-Lauf: per_category/per_sample-Daten → Graphen sichtbar
