# Change 045: Wort-Timing sofort (Backend/linear) + präzises Alignment im Hintergrund

**Status:** proposal
**Datum:** 2026-08-20
**Typ:** Feature

## Motivation (User-Anforderung, wörtlich)

> „…nach der transkription erstmal temporaer das wort-timing / alignment von
> parakeet nehmen (oder wenn das model keins liefert: linear verteilen) und
> das 'gute' präzise alignment im Hintergrund starten, während der User
> bereits die transkription sehen kann."

Heute blockiert die Forced-Alignment-Phase (`_run_align_phase`, service.py
Z. 543, Aufruf Z. 1006) den Job **synchron** vor dem Status „done" — bei
langen Audios 10–25 min Wartezeit, bis die Transkription sichtbar wird.

## Lösung

1. **Job-Fluss ändern**: `_run_align_phase` aus dem synchronen Pfad
   herauslösen. Nach ASR (+Diar) wird der Job sofort `done` mit den
   **Backend-Word-Timestamps** bzw. der **linearen Verteilung**
   (`_build_word_stream`, existiert bereits, Z. 111 — exakt die
   User-Kaskade: vorhandene TS → Uniform-Verteilung → kein Mapping).
2. **Hintergrund-Alignment**: direkt nach „done" startet ein Worker-Thread
   `_run_align_phase` mit dem gespeicherten Audio. Ergebnis (präzise
   Word-Timestamps) wird in die DB geschrieben.
3. **Statusanzeige**: Recording bekommt ein Feld
   `alignment: "pending" | "running" | "done" | "skipped"` (Default
   `done` bei ALIGN_WORDS=false / Aligner down). Die UI zeigt einen
   dezente Hinweis „Präzises Alignment läuft im Hintergrund…", solange
   `running` ist.
4. **UI-Update**: Beim Polling / Recording-Refresh werden die neuen
   Segmente (mit verifizierten Word-Timestamps) übernommen — kein Reload
   nötig, kein Fake-Progress: Der Hinweis ist ehrlich, die Werte kommen
   aus dem echten Worker.

## Details

- **Audio-Verfügbarkeit**: Der Worker liest die Datei von der Platte
  (`stored_path`) — kein Speicher-Handover nötig. VAD-Trim-Offset: die
  gespeicherte Datei ist die getrimmte? Nein — heute läuft align auf
  `audio_bytes` (verarbeitet, nach Trim/Enhance). Der Worker muss den
  gleichen Pfad nehmen: ggf. Trim/Enhance erneut anwenden ODER besser:
  die verarbeiteten Bytes beim Job-Ende als Temp-Cache ablegen
  (`/data/.align-cache/<rec_id>.wav`), damit der Worker exakt die
  Zeitbasis hat. Einfachste robuste Variante: Worker rechnet VAD-Trim +
  Enhance erneut (deterministisch, gleiche Parameter aus der DB) und
  nutzt dieselben Segment-Offsets wie der Job (trim_offset_s wird in
  den Segment-Zeiten bereits kompensiert gespeichert — Achtung: der
  Aligner braucht Zeiten relativ zur Audio-Basis, die Segment-Zeiten
  sind aber schon +offset → der Worker muss den Offset abziehen und
  nachher wieder draufrechnen; identisch zu heute, wo trim_offset_s
  nach dem Align aufgeschlagen wird).
- **Cancel/Concurrency**: Hintergrund-Alignment ist non-blocking. Läuft
  ein Re-Transcribe/Re-Align, darf der alte Worker nicht in die neuen
  Segmente schreiben → Versions-Guard (rec.segments-Version oder
  Timestamp-Vergleich vor dem Write; der spätere Write gewinnt).
- **Failure**: Aligner down / Fehler → `alignment: "skipped"` + Log,
  Backend-Timestamps bleiben (nie ein Job-Fail, wie heute).
- **Aktivierung**: Immer aktiv wenn ALIGN_WORDS_ENABLED; Admin kann via
  Env `POLYSCHNACK_ALIGN_BACKGROUND=false` auf synchron zurückfallen.

## Tests

- Job wird `done` OHNE Align-Phase (Timestamp/Status-Timing)
- Worker aktualisiert Segmente mit Aligner-Wörtern (Mock-Aligner)
- `alignment`-Status in Serialisierung (`_recording_to_dict`)
- Trim-Offset-Kompensation identisch zu heute
- Versions-Guard: alter Worker überschreibt neue Segmente nicht

## Checkliste

- [ ] proposal.md
- [ ] tasks.md
- [ ] Modell-Feld `alignment`
- [ ] Job-Fluss-Umbau (align raus aus synchron)
- [ ] Hintergrund-Worker + Versions-Guard
- [ ] Serialisierung + UI-Hinweis
- [ ] Tests
- [ ] Commit + Push
