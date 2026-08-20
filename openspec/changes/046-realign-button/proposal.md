# Change 046: Re-Align-Trigger-Button (Ground-Truth-Alignment nach Korrektur)

**Status:** proposal
**Datum:** 2026-08-20
**Typ:** Feature

## Motivation (User-Anforderung)

> „Wenn der user fehlerhafte Transkriptionen korrigiert und quasi ein
> 'Ground Truth' erstellt hat, kann man auf dieses existierende Skript nochmal
> ein 're-alignment' laufen lassen?"

Der Forced-Aligner (`POST /v1/audio/align`) ist **text-agnostisch**: er
alignt (Audio, Referenztext, Sprache) → Wortgrenzen. Ein korrigierter
Transkriptionstext ist die Ground Truth und liefert ein **präziseres**
Alignment als das Original (das auf ASR-Halluzinationen basiert).

Heute macht ein Segment-Edit nur das billige Wort-Diff (Change 010:
unveränderte Wörter behalten Timestamps, neue interpolieren). Die
interpolierten Wörter sind künstlich — ein Re-Alignment würde sie
akustisch verifizieren.

## Lösung

1. **Endpoint** `POST /api/recordings/{rid}/realign` (auth: write-Zugriff):
   - liest die aktuellen Segment-Texte (nach User-Korrekturen)
   - schneidet Audio-Chunks via `build_align_groups` (existiert)
   - ruft den Aligner (`AlignerClient.align`) für jede Gruppe
   - ersetzt NUR die Word-Timestamps in den Segmenten
     (Segment-Grenzen start/end bleiben unangetastet)
   - schreibt per Versions-Guard (nur wenn seit dem Read nichts
     geändert wurde), aktualisiert `rec.alignment = "done"`
2. **Trigger-Button** in der Transkriptions-Ansicht: „Re-Align" (nur
   für User mit write-Zugriff, nur bei status=done). Während des Laufs
   Hinweis + echter Fortschritt (Gruppen-Zähler), kein Fake.
3. **Wiederverwendung**: Der Hintergrund-Worker aus Change 045 und der
   Re-Align-Endpoint teilen sich die Kernfunktion `run_align_on_segments(
   rec_id, segments, audio_bytes, language, job=None)`.

## Details

- **Audio-Basis**: gespeicherte Datei (`stored_path`); VAD-Trim/Enhance
  werden wie im Job angewendet, Offset-Kompensation wie gehabt
  (Segment-Zeiten sind bereits kompensiert → vor Align abziehen, nach
  Align wieder aufschlagen).
- **Failure**: Aligner down → 503 mit verständlicher Meldung (kein
  stiller Fehler — User-Vorgabe: stille Fehler inakzeptabel).
- **Segments_manual**: Re-Align ändert keine Segment-Grenzen →
  `segments_manual` bleibt unverändert.
- **Cancel**: User kann den Lauf abbrechen (Button), Job-Timeout-Guard
  wie in `_run_align_phase`.

## Tests

- Endpoint: auth (write nötig), 404, Aligner-down → 503
- Mock-Aligner: korrigierter Text → neue Word-Timestamps in den
  Segmenten, Grenzen unverändert
- Versions-Guard: paralleler Edit verliert nicht
- Frontend: Button sichtbar (write), klickbar, Status-Feedback

## Checkliste

- [ ] proposal.md
- [ ] tasks.md
- [ ] Gemeinsame Align-Funktion (Refactor aus _run_align_phase)
- [ ] POST /realign-Endpoint
- [ ] Frontend-Button + Feedback
- [ ] Tests (Backend + Frontend)
- [ ] Commit + Push
