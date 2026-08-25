# Change 127 — ETA für laufende Rediarize (methoden-getrennt) + Fallback-Kalibrierung

## Problem

User-Befund (2026-08-25): Bei laufender Diarization („Sprechererkennung"
auf fertigem Recording) zeigt die App auf dem Handy nur
„Diarization running in background … · running for XXs" — **keine ETA**.
Grund (code-verifiziert): `recordings.py` berechnete ETA nur bei
`rec.status == "processing"`; die Rediarize läuft aber mit
`status == "done"` + `diar_status == "running"` → `eta` war immer
`None`.

Zusätzlich sind die Fallback-RTF-Werte (`DIAR_RTF`: pyannote 0.4,
foxnose 0.2) deutlich zu optimistisch gegenüber der Realität
(75-min-Meeting: pyannote ≈ 1,3×, foxnose ≈ 1× Echtzeit) — bis der
Learner genug Stichproben hat (n ≥ 10), zeigt die ETA also viel zu
kurze Zeiten. Der User will „halbwegs realistische ETA", gelernt
getrennt für pyannote und foxnose.

## Analyse (Ist-Zustand, code-verifiziert)

- Der ETA-Learner lernt Diarization **bereits methoden-getrennt**:
  Ingest `diar:{method}` im Transcribe-Pfad (`service.py` ~Z. 2063)
  UND im Rediarize-Worker (Change 115, `service.py` ~Z. 1535).
- Die ETA-Abfrage (`eta.py` Z. 96–98) nutzt denselben Key
  `diar:{method}` mit `DIAR_RTF`-Fallback.
- **Lücke 1:** Keine ETA bei `done + diar_status running` (Rediarize).
- **Lücke 2:** `DIAR_RTF`-Fallbacks nicht kalibriert (zu optimistisch).

## Lösung

1. `eta.py`: neue Funktion `estimate_diar_eta_s(duration_s, method,
   elapsed_s, learner)` — Rest-ETA nur für die Diar-Phase
   (Dauer × RTF(diar:<methode>), gelernt > Fallback > None; elapsed
   seit `phase_started_at`).
2. `recordings.py`: ETA-Zweig für `done + diar_status in
   (running, pending)` → `estimate_diar_eta_s` (Basis
   `phase_started_at`, gesetzt beim Rediarize-Start via
   `set_progress`-Note).
3. `eta.py` `DIAR_RTF`: Fallbacks an gemessene Läufe kalibrieren
   (Benchmark 220-s-Ausschnitt, 2026-08-25: pyannote/foxnose mit
   `scripts/diarize_local.sh` auf derselben Datei).
4. Frontend `RecordingCard.tsx`: ETA-Spanne (`etaRange`) im
   bg-diar-Hinweis anzeigen („· geschätzt X–Ym").

## Betroffene Dateien

- `webapp/app/eta.py` (`estimate_diar_eta_s`, `DIAR_RTF`)
- `webapp/app/routers/recordings.py` (ETA-Zweig)
- `webapp/frontend/src/components/RecordingCard.tsx` (bg-diar-ETA)
- Tests: `tests/test_eta.py`, `tests/test_cancel_align_diar.py`,
  `RecordingCard.test.tsx`

## Verifikation

1. Unit-Tests `estimate_diar_eta_s`: Fallback, elapsed-Abzug, None ohne
   Dauer, methoden-getrennte Lernwerte (foxnose 0.5 vs. pyannote 2.0).
2. Response-Test: `done + diar_status running` → `eta_low_s`/`eta_high_s`
   gesetzt.
3. Frontend-Test: bg-diar-Hinweis zeigt ETA-Spanne.
4. Backend- + Frontend-Gesamtsuite grün.
