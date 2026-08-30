# Change 161 — Chunk-Overlap-Dopplungen präventiv an der ASR-Eingangsstufe entfernen

**Status:** Proposed

## User-Regel (2026-08-30, bei Recording 8976aa1b beobachtet)

„Kann man nicht verhindern, dass die Dopplungen entstehen, statt sie zu
entfernen?" — Doppelte Wortfolgen dürfen gar nicht erst in die DB gelangen;
kein post-hoc Reconciliation.

## Befund (Recording 8976aa1b, Segment 8:40)

Text: „Im anliegenden Ort **Im anliegenden Ort** erzählt man sich, dass…"

- **v115** (28.08.): Phrase 1× (sauber)
- **v116** (29.08. 10:44, Retranscribe): Phrase 2× — die Dopplung entstand
  hier, nicht durch Drags (v172–v189 heute: alle Diffs „same")
- Audio-Hörbeweis (faster-whisper, 512–552 s) + frischer ps-pk-onnx-Lauf
  (mit/ohne Diarization, 40-s- und 120-s-Clip): die Phrase kommt im Audio
  **einmal** vor
- Wort-Zeiten der zweiten Kopie: exakt 0,08 s (Change-159-Mindestdauer) =
  von `reconcile_words_to_text` interpolierte Wörter; die erste Kopie trägt
  Zeiten in der Stille (519–529 s, kein akustisches Signal)

## Root Cause

- ps-pk-onnx verarbeitet lange Audios in **120-s-Chunks** (backends.yaml).
  An einer Chunk-Grenze wird dieselbe Wortfolge doppelt transkribiert
  (Overlap der Fenster).
- `process_recording` übernimmt `result["segments"]` **1:1 ungeprüft**
  (service.py, direkt nach der ASR). Diarization-Merge, Aligner
  (`build_align_groups` → `apply_aligned_words`) und `reconcile_words_to_text`
  behandeln den doppelten Text als Wahrheit: der Aligner legt die erste
  Kopie akustisch haltlos in die Stille, reconcile interpoliert die zweite
  mit Mindestdauer.
- Change 160 (live) verhindert NUR Drag-bedingte Desyncs — er heilt keine
  bestehende Text-Dopplung, weil der Text die Wahrheit ist.

## Lösung

**Präventive Deduplizierung direkt nach der ASR** (bevor Diarization, Align
und DB den Text sehen): `dedupe_repeated_word_runs(segments)` erkennt
Chunk-Overlap-Dopplungen und entfernt die zweite Kopie.

Erkennungs-Signatur (deterministisch, auf dem Wort-Stream):
- zwei direkt aufeinanderfolgende Wortfolgen mit **identischem Text**
  (n ≥ 2 Wörter)
- **und** zeitlicher Chunk-Overlap: die zweite Kopie beginnt innerhalb der
  ersten oder unmittelbar danach (start₂ < end₁ + 1,0 s) — echte
  rhetorische Wiederholungen sind zeitlich getrennt und bleiben erhalten
- ohne Wort-Zeiten (Fallback): identische Folge direkt benachbart, n ≥ 3

Die Funktion entfernt die zweite Kopie aus Segment-Wörtern **und**
Segment-Texten und baut den Gesamttext neu. Einziges Invarianz-Ziel:
`join(segment words) == rec.text`, keine Dopplung mehr im Text.

Einbauort: `process_recording`, direkt nach `segments = result["segments"]`
— vor VAD-Offset, Diarization, Align-Cache und `crud.update_result`.

## Tests

1. Synthetische Chunk-Overlap-Segmente (doppelte Wortfolge, überlappende
   Zeiten) → nach Dedup genau eine Kopie, Text == join(words).
2. Echte zeitlich getrennte Wiederholung („Ich liebe dich. Ich liebe
   dich." mit Abstand) → bleibt unangetastet.
3. Fallback ohne Zeiten: „A B C A B C" → dedupliziert; „ja ja" (n=2, keine
   Zeiten) → bleibt.
4. Regression: konsistente Segmente ohne Dopplung → bitte-identisch.
