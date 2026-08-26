# Change 130: diarize_embedder für foxnose auf `auto` (Server löst Alias `wespeaker` nicht auf)

## Problem

Seit Change 126 sendet die Webapp bei `diarize_method=foxnose` den Embedder-Wert
`DIARIZE_FOXNOSE_EMBEDDER` (Default: `wespeaker`). Der CrispASR-Server behandelt
`--diarize-embedder` aber **nicht als Registry-Alias**, sondern als **Dateipfad**:
`gguf_init_from_file: failed to open GGUF file 'wespeaker' (No such file or directory)`.
Der Embedder lädt nie → das globale Re-Clustering bleibt aus → alle Segmente
fallen auf `SPEAKER_00`.

Belegt (2026-08-26):

- Lokal reproduziert auf **beiden** Versionen: Box-Artefakt v0.8.28-ort-poc1 UND
  lokaler Build v0.8.29: `--diarize-embedder wespeaker` → „failed to load embedder
  'wespeaker'"; `--diarize-embedder auto` → lädt das Wespeaker-GGUF
  („using cached wespeaker-resnet34-lm.gguf") und clustert **6 Speaker** auf dem
  Teamtreffen-Clip.
- Box-Log (konsolidiert vom User): `gguf_init_from_file: failed to open GGUF file
  'wespeaker'` — der Server empfängt den Wert also und scheitert daran.
- Prod-API-Test 2026-08-26 (5-min-Clip): foxnose → 2/2 SPEAKER_00, pyannote →
  2/2 SPEAKER_00, vad-turns → 3 Speaker (Server kann prinzipiell diarisieren).
- CLI foxnose + voller Wespeaker-Pfad (lokal): 3 Speaker, saubere Turns (54/23/18 %).

## Lösung

`DIARIZE_FOXNOSE_EMBEDDER`-Default von `wespeaker` → `auto`. `auto` ist der einzige
Wert, den der Server zuverlässig serverseitig auflöst (für foxnose lädt er damit
nachweislich das Wespeaker-GGUF, für pyannote TitaNet). Ein expliziter GGUF-Pfad
bleibt per Env-Override möglich (`DIARIZE_FOXNOSE_EMBEDDER=/models/.crispasr-cache/wespeaker-resnet34-lm.gguf`).

Der diar-Server auf der Box startet bereits mit `--diarize-embedder auto`
(entrypoint.sh) — der Webapp-Request hatte den Startwert mit `wespeaker`
überschrieben. Mit `auto` im Request ist der Wert konsistent.

## Ausblick / bewusst NICHT in diesem Change

- Der Aligner (`aligner-service`) basiert auf qwen3-asr.cpp, NICHT auf CrispASR —
  kein Basis-Update nötig (frischer `git clone` pro Build).
- Ein Update der diar-Service-CrispASR-Basis (v0.8.28-ort-poc1 → neuer Release)
  löst den Alias ebenfalls nicht (v0.8.29 lokal getestet: gleicher Pfad-Fehler)
  und ist daher kein Ersatz für diesen Fix. Optional separat, falls neue
  Diarize-Features gewünscht sind.
- pyannote liefert auf dem Teamtreffen-Clip nur 1 Cluster (Modellgrenze der
  Segmentierung auf diesem Audio, lokal reproduziert) — foxnose bleibt Default.
