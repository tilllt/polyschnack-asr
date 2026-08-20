# Change 035 — Fortschrittsanzeige ehrlich: Heartbeat-Fix + Phasen-Chips

## Problem

1. **„⚠ keine Aktivität seit …" bei JEDER Transkription** (User-Befund 20.08.):
   Der Heartbeat-Thread startet nur bei `async_jobs=False` (service.py Z. 881).
   Das Default-Backend `ps-pk-onnx` deklariert `async_jobs=True` (+ `streaming=True`),
   definiert aber keinen eigenen `transcribe_async` → der Aufruf fällt auf den
   **blockierenden Sync-Fallback** der Basisklasse zurück. Ohne Streaming-Toggle
   läuft die Transkription also blockierend OHNE Heartbeat: `last_heartbeat_at`
   friert bei „20% asr" ein → die UI zeigt nach 45 s die Stall-Warnung — bei
   jeder Transkription, die länger als ~45 s dauert.
2. **`set_queued`/`set_processing` setzen `last_heartbeat_at`/`phase_started_at`
   nicht zurück** → nach Re-Transcribe/Enqueue zeigt die Karte sofort einen
   uralten Zeitstempel („seit 120m"), bevor der erste echte Progress kommt.
3. **LLM-Phasen ohne Lebenszeichen**: `run_punctuation`/`run_llm_enhance`/
   Prompt-Template laufen bei pct=95 ohne `set_progress` und ohne Heartbeat →
   minutenlange LLM-Calls lösen ebenfalls die Stall-Warnung aus (Fehlalarm).
4. **Prozent-Skala ist nicht linear** (1 → 21 → 95 → 96 → 99 → 100): ein
   einzelner Balken suggeriert Genauigkeit, wo Phasen unterschiedlicher Länge
   willkürlich skaliert sind. ETA aus Poll-Sprüngen fehlt in Phasen ohne Zähler.

## Ziel

- **Heartbeat überall dort, wo ein Job blockiert ohne Zähler läuft** — die
  Stall-Warnung ist wieder ein echtes Signal, kein Dauerzustand.
- **Phasen-Chips** statt nur Text: Vorbereitung → ASR → Diarisierung →
  Alignment → Nachbearbeitung, je Chip Status (erledigt / aktiv / übersprungen
  / offen). Der Prozentwert bleibt als Zusatzinfo, wo er real ist (Zähler).
- **Ehrliche Zeitangaben**: echte Rate → „~Xm"; keine Rate → „aktiv seit Xs"
  (Heartbeat); Stall nur bei totem Job („möglicherweise hängend").

## Entscheidungen

- **Heartbeat-Fallback für ALLE nicht-streamenden Pfade** (Change 035): der
  Heartbeat-Thread startet immer, wenn nicht `transcribe_streaming` läuft —
  auch bei `async_jobs=True`. `on_progress` aktualisiert parallel pct
  (`set_progress` tickt ohnehin `last_heartbeat_at`); der Thread schreibt nur
  denselben pct — kein Konflikt, kein erfundener Fortschritt.
- **LLM-Phasen bekommen note `postprocessing` + Heartbeat** (pct 95): vor
  `run_punctuation`/`run_llm_enhance`/Template-Call wird
  `set_progress(95, "postprocessing")` gesetzt und der Heartbeat gestartet.
- **`set_queued`/`set_processing` reseten Heartbeat-Felder** auf now — die
  „seit Xs"-Anzeige startet frisch; ein alter Wert von einem früheren Lauf
  kann nie mehr durchscheinen.
- **Frontend Phasen-Chips**: feste Phasenreihenfolge
  `[preparing, asr, diarization, alignment, postprocessing]`; aktive Phase aus
  `progress_note` (+ pct-Fallback: ≤20 → preparing, 21–95 ohne note → asr,
  note finalizing/postprocessing → Nachbearbeitung). Optional-Phasen
  (diarization) werden „übersprungen" markiert, wenn `enable_diarize=false`
  (Recording-Objekt liefert das Flag).
- **ETA unverändert ehrlich**: `etaFromRate` nur bei echten Sprüngen; sonst
  „aktiv seit Xs" aus `phase_started_at`. RTF×duration_s-Gesamtschätzung ist
  bewusst NICHT Teil dieses Changes (eigener Change, braucht Backend-Benchmark-
  Werte).
- **Stall-Text präzisiert**: „möglicherweise hängend · keine Aktivität seit Xs"
  (kein Fake-Fehler, aber klarer Handlungsimpuls).

## Nicht-Ziele

- Keine RTF-basierte Dauer-Schätzung (eigener Change).
- Keine Änderung an Queue-ETA-Formel (`position × avg_recent_processing_ms`
  bleibt; Kennzeichnung als Ø-Schätzung im Text).
- Kein Progress-Refactoring der Benchmark-Seite (401-Thema Change 030/031 ist
  separater Strang).
- Kein Prozent-Balken-Entfernen: bleibt als dezente Zusatzinfo (nur wo pct
  real von Zählern kommt).

## Betroffene Dateien

- `webapp/app/service.py` (Heartbeat-Bedingung, LLM-Phasen-Heartbeat)
- `webapp/app/crud.py` (`set_queued`, `set_processing`: Heartbeat-Reset)
- `webapp/frontend/src/components/RecordingCard.tsx` (PhaseChips, Stall-Text)
- `webapp/tests/` + `frontend`-vitest (Regressionstests)
