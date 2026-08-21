# Tasks — Change 078: Align-Chunking (große Segmente technisch teilen)

## T1 — `_split_long_segment` (service.py)
- [x] Pure Funktion: Segment > max_s → n=ceil(dur/max_s) gleich große
      Zeit-Chunks; Text proportional (Wort-Reihenfolge) aufteilen
- [x] Wortliste aus seg.words (Reihenfolge) oder seg.text.split()
- [x] Returns [(chunk_start, chunk_end, chunk_text), …]; leere Segmente
      → leere Chunks ohne Crash

## T2 — `build_align_groups` Umbau
- [x] Langes Einzel-Segment: offene Gruppe flushen, dann Chunks anhängen
- [x] Normale Segmente: Bündel-Logik unverändert (bestehende Tests grün)
- [x] `MAX_ALIGN_GROUP_S` 380 → 120 s (ASR-Chunk-Länge, gemessen gut)

## T3 — `_run_align_phase` Wörter-Sammeln
- [x] Pro Gruppe: words global machen (w.start/end += g_start), sammeln
- [x] Nach der Schleife EINMAL apply_aligned_words(segments, all, 0.0)
- [x] Mehrfach-Chunk-Segment behält ALLE Wörter (kein Überschreiben)

## T4 — Adaptive Noisefloor-Schwelle (aligner_server.py, User-Vorgabe)
- [x] `_estimate_silence_rms`: P15×1.8 bei Kontrast (P85/P15 ≥ 2),
      sonst P15×0.8 (Kontrast-Schutz gegen Signal-Kollaps)
- [x] `_energy_refine` Default `silence_rms=None` → adaptiv pro Chunk
- [x] Pro Request/Chunk neu berechnet → Rauschen kann im Verlauf
      lauter/leiser werden, jeder Chunk bekommt seine eigene Schwelle
- [x] Test: verrauschtes WAV — adaptive findet ≥3 Lücken, feste 300 nicht

## T5 — Tests (test_aligner.py)
- [x] Angepasst: einzelnes langes Segment → mehrere Gruppen
- [x] Neu: Chunk-Texte decken Gesamttext verlustfrei ab (Reihenfolge)
- [x] Neu: apply_aligned_words mit globalen Wörtern + Offset 0
- [x] Neu: Segment in 2 Chunks → Wörter beider Chunks im Segment
- [x] Bestehende Bündel-Tests weiter grün (19/19 test_aligner+test_realign)

## T6 — Gates + Live-Verifikation
- [x] pytest test_aligner.py + test_realign.py grün (19/19)
- [x] Aligner-Service-Unittests grün (21/21)
- [ ] Backend-Vollsuite GESAMT fail=0
- [ ] Live: Re-Align auf `68026-moissi-hamlet.mp3` (UID 52d96584…);
      Abdeckung messen (Ziel ≥ 90 %, vorher 30 %)
- [ ] Test-Recordings chunk_a/chunk_b löschen
