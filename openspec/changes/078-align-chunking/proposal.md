# Change 078: Align-Chunking — große Segmente technisch teilen, User-Segmente bleiben

## Problem

User-Befund (2026-08-21, `68026-moissi-hamlet.mp3`, UID `52d96584…`):
Nach dem Einfügen des korrekten Original-Texts und Re-Align bekam das
Karaoke-Playback kein brauchbares Timing. Diagnose per Live-API:

- Das Audio (234 s, historische Schellack-Aufnahme) enthält den vollen
  Monolog von Sekunde 0 an (Chunk-Transkription 0–80 s = Monolog-Anfang,
  80–234 s = Fortsetzung).
- Der Forced-Aligner lief (alle 224 Wörter auf 80-ms-Bins), aber die
  Abdeckung war katastrophal: nur 79.5–148 s (30 % der Dauer) bekamen
  Wörter; die Lücken wurden zu Monster-Wörtern („oder" = 76,6 s,
  „Namen." = 80,2 s).
- **Längen-Skalierung gemessen:** Chunk 80 s → 99,8 % Abdeckung,
  Chunk 154 s → 91,6 %, Original 227 s in EINEM Request → 30 %.

Root Cause: `build_align_groups` teilt nur ZWISCHEN Segmenten. Der User
hat den Monolog in EIN Segment (0.96–228.32 s) gepackt; 227 s <
`MAX_ALIGN_GROUP_S = 380` → EINE Align-Gruppe mit dem kompletten Text.
Der qwen3-forced-aligner liefert bei so langen, verrauschten Requests
eine komprimierte Zuordnung (Monotonie-Korrektur rutscht durch).

## Ziel

GUI-Segmente und Align-Chunks entkoppeln (User-Vorgabe):
„Wenn der Aligner aus technischen Gründen 120-s-Segmente braucht,
reformatiere den Text in die technisch optimierten Segmente, füge aber
das Timing der Wörter wieder in die User-definierten Segmente ein."

1. `build_align_groups` teilt auch EINZELNE Segmente, die länger als
   `max_s` sind, in gleich große Zeit-Chunks und schneidet den Text
   proportional mit (Wort-Reihenfolge erhalten).
2. `MAX_ALIGN_GROUP_S` von 380 s auf 120 s (ASR-Chunk-Länge, gemessen
   gut: 80 s → 99,8 %).
3. Die alignierten Wörter aller Chunks werden GLOBAL gesammelt (mit
   Gruppen-Offset) und EINMAL über `apply_aligned_words` den
   Original-Segmenten zugeordnet — User-Segmentgrenzen bleiben exakt,
   nur die Wort-Timestamps werden ersetzt.

## Design

### `_split_long_segment(seg, max_s)` (neu, pure)

- Segment-Dauer > max_s → `n = ceil(dur / max_s)` Chunks.
- Wortliste = `seg.words` (Reihenfolge!) oder `seg.text.split()`.
- Wort i → Chunk `floor(i / len_words * n)` (gleichmäßig über die Zeit,
  NICHT nach kaputten alten Wortzeiten — die sind das Problem).
- Returns `[(chunk_start, chunk_end, chunk_text), …]`.

### `build_align_groups` (Umbau)

- Segment länger als max_s → offene Gruppe flushen, dann
  `_split_long_segment`-Chunks als eigene Gruppen anhängen.
- Sonst unverändert (Bündeln wie bisher).

### `_run_align_phase` (Umbau)

- Statt `segments = apply_aligned_words(segments, words, g_start)` pro
  Gruppe: alle Wörter sammeln, `w.start/end += g_start` (global
  machen), nach der Schleife EINMAL
  `apply_aligned_words(segments, all_words, 0.0)`.
- Grund: Ein in mehrere Chunks geteiltes Segment bekommt Wörter aus
  MEHREREN Gruppen; die alte Pro-Gruppe-Anwendung überschrieb sie.

### Grenzen

- Nur die Align-Pipeline ändert sich; Segment-Struktur, Text, Speaker,
  Versions-Snapshots, Frontend unberührt.
- `apply_aligned_words` selbst bleibt (Offset 0 + globale Wörter).

## Nicht-Ziel

- Kein adaptiver silence_rms für die Energie-Korrektur (separates
  Thema: Plattenrauschen; hier geht es um die Chunk-Größe).
- Keine Änderung am Aligner-Service (400-s-Limit bleibt).
- Kein Frontend-Umbau.

## Betroffene Dateien

- `webapp/app/service.py` (`_split_long_segment`, `build_align_groups`,
  `_run_align_phase`, `MAX_ALIGN_GROUP_S`)
- `webapp/tests/test_aligner.py` (angepasste + neue Tests)
- `openspec/changes/078-align-chunking/{proposal.md,tasks.md}`

## Erfolgskriterien

- [ ] 227-s-Segment → build_align_groups liefert ≥ 2 Chunks (je ≤ max_s)
- [ ] Chunk-Texte decken den Gesamttext verlustfrei ab (Reihenfolge)
- [ ] Mehrfach-Chunk-Segment behält ALLE alignierten Wörter (kein
      Überschreiben durch die letzte Gruppe)
- [ ] User-Segmente bleiben unangetastet (nur words ersetzt)
- [ ] Backend-Tests grün (test_aligner.py, test_realign.py), Vollsuite
- [ ] Live-Verifikation gegen `68026-moissi-hamlet.mp3`:
      Abdeckung >> 30 % (Ziel ≥ 90 %)
