# Change 110 — Internes Workflow-Scheduling: Phasen-Registry + ein Job-Modell für alle Workflows

> Status: KONZEPT (User-Auftrag 23.08.2026: „Refactoring für das interne
> Scheduling aller Workflows").
> Design-Change: Analyse + Ziel-Architektur; Umsetzung als Folge-Change
> (baut auf Change 109 auf, liefert den Unterbau für Change 108 reprocess).
> Teil des Refactoring-Programms (openspec/refactoring-program.md): Stufe 2.

## Problem

Neben der ASR-Queue (Change 109) ist auch die **interne Workflow-Schicht**
organisch gewachsen: eine monolithische Pipeline, drei Kopien von
Heartbeat-Logik, Background-Jobs außerhalb jedes Job-Modells, Phasen-Status
als Freitext.

**S1. Monolithische Pipeline ohne Phasen-Registry.**
`process_recording` (service.py Z. 1405–2102, ~700 Zeilen) durchläuft alle
Phasen linear (Audio → VAD → Enhance → Separate → ASR → Punc → Align → Diar →
Persist). Es gibt keine datengetriebene Phasen-Liste, keinen Wiedereinstieg,
keine Persistenz der Phasen-Zeiten — `phase_times` (Z. 1520) lebt nur im RAM
(Stichproben für den rtf_learner, gehen beim Restart verloren).

**S2. Phasen-Status als Freitext.**
Der Fortschritt ist `progress_pct` + `progress_note` (String: „alignment",
„Re-Diarize läuft …"); `run.phase = rec.progress_note` (Z. 1484). Kein Enum,
keine Maschinenlesbarkeit, kein validierter Übergang.

**S3. Drei Heartbeat-Kopien.**
- phasen-spezifische Heartbeats (Z. 1357: asr/diar/llm setzen pct+note),
- Job-Heartbeat (Z. 1397: tickt pct mit note=None),
- align-Heartbeat (Z. 706: eigener Thread mit Stop-Event).
Selbst als Problem erkannt (Kommentar Z. 1370: „Befund 2026-08-20: Die
phasen-spezifischen Heartbeats …") — drei Varianten mit unterschiedlicher
pct/note-Semantik, manuell koordiniert.

**S4. Background-Workflows außerhalb der Queue (fire-and-forget).**
`_run_background_align` (Z. 878, Start Z. 1098/1957) und
`_run_background_rediarize` (Z. 1168, Start Z. 1159) laufen als nackte
daemon-Threads: kein Queue-Job, kein Cancel-Interface, kein Timeout, kein
Retry, kein Tracking außer `rec.alignment = "pending"` + Versions-Guard.
Ein hängender Aligner-Call im Hintergrund läuft unbegrenzt weiter.

**S5. Drei Copy-Paste-Daemon-Loops in main.py.**
retention-sweep (inkl. stale-sweep + health-scan, Z. 160–177),
peaks-backfill (2/Batch à 30 s, Z. 184–194), yjs (Z. 195–203) — jeder mit
eigenem Stop-Event und eigener Fehlerlogik; dazu fire-and-forget-Threads im
Router (`routers/recordings.py` Z. 421 `_compute_peaks_background`).

**S6. Implizite Run-Bindung.**
Der Worker sucht den „ältesten queued Run" (Z. 1466–1468) statt einer
expliziten Job→Run-Referenz — mit dem `settings_snapshot` aus Change 109
entfällt diese Suche komplett.

**S7. Kein Wiedereinstiegspunkt (blockiert Change 108).**
Die Reprocess-Pipeline (108: Bereich + Schritt align/diarize/asr mit anderem
Modell) ist heute unmöglich: `process_recording` startet immer von vorn, kann
keine Teilbereiche verarbeiten.

## Ziel-Architektur

### K1. Phasen-Registry + explizite Workflow-Definition
```
WORKFLOWS = {
  "transcribe": [vad, enhance, separate, asr, punc, align, diarize, persist],
  "align":      [align, persist],
  "rediarize":  [diarize, persist],
  "reprocess":  ...  # 108: beliebiger Schritt auf Bereich (range)
}
Phase = { name: Enum, pct_range: (from, to), cancel_check: bool,
          timeout_s: int, output: audio|text|segments|words }
```
- `run.phase` wird **Enum** (nicht Freitext); `progress_note` nur noch
  User-Text.
- Phasen-Zeiten pro Run persistieren (JSON-Spalte) — rtf_learner und ETA
  (109 J3) speisen sich aus echten Werten statt flüchtiger Stichproben.

### K2. Ein Job-Modell für ALLE Workflows (mit Change 109)
- align/rediarize/reprocess laufen als Jobs desselben Job-Runners
  (109 J1), mit `workflow`-Feld, identischem Cancel/Timeout/Retry.
- `_run_background_align`/`_run_background_rediarize` werden zu
  `Job(workflow="align"|"rediarize")`; der Versions-Guard bleibt
  (Idempotenz bei Retry).
- **Regel:** Workflow-Start ohne Queue-Job ist verboten (Assertion) —
  beendet das fire-and-forget-Muster.

### K3. Ein Heartbeat-Muster
- Eine Heartbeat-Funktion pro Job; Fortschritt kommt aus der
  Phasen-Registry (Phasen-Index → pct-Bereich). Die drei Kopien
  (phasen/job/align) entfallen.

### K4. Cancel/Timeout überall
- `cancel_requested` + `timeout_s` aus der Job-Tabelle gelten für alle
  Workflows (auch align/rediarize); Cancel wird zwischen Phasen geprüft.

### K5. Wiedereinstieg (Unterbau für 108 reprocess)
- `run_workflow(rec_id, workflow, step=None, range=None, job)` —
  Phasen-Liste ab beliebigem Schritt; jede Phase deklariert ihren
  Input/Output. 108s reprocess = `run_workflow(..., "align", range=[a,b])`.

### K6. Scheduled Tasks vereinheitlichen
- sweep/peaks/health als Registry `SCHEDULED_TASKS = { name: (interval_s,
  fn, stop_event) }` mit einer Loop-Funktion statt drei Copy-Paste-Loops.
- yjs bleibt asyncio (eigenes Paradigma, kein Thread-Loop).

## Verifikation

- align/rediarize erscheinen in `/api/queue`, sind cancelbar, timeout- und
  retry-fähig (109-Tests erweitert).
- Grep-Beweis: keine `threading.Thread`-Starts mehr in service.py außer im
  Job-Runner; keine `_run_background_*`-Funktionen.
- `phase` ist Enum: keine Freitext-Zuweisung mehr
  (grep `progress_note\s*=` findet nur User-Text-Stellen).
- Restart: laufender align-Job wird ehrlich `failed` („Neustart", 109-Muster).
- Reprocess-Smoke (108): Bereichs-Align verändert nur Wörter im Bereich.

## Abhängigkeiten

- **Basis:** Change 109 (Job-Tabelle, Rehydration, Retry) — 110 nutzt den
  Job-Runner; ohne 109 bleibt 110 ein Thread-Umbau ohne Persistenz-Gewinn.
- **Liefert:** Change 108 (reprocess-Pipeline) den Ausführungs-Unterbau.
- Reihenfolge: 109 → 110 → 108-Frontend.
