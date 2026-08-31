# Change 183 — Job-Zustandsmaschine: EINE Quelle der Wahrheit

**Status:** Proposed (Design-Review, KEIN Code — 2026-08-31)

## Warum (Bilanz der Hotfix-Kette 173–182)

Zehn Einzel-Fixes in einer Session — alle Symptome derselben strukturellen
Schwächen. Die Progress-/Cancel-/Aktivitäts-Logik ist über acht
Recording-Felder + In-Memory-Queue + DB-Job-Rows verteilt, von sechs+
Stellen geschrieben, mit Race-Fenstern und Blocking-Calls ohne Abbruch.
Hotfixes schließen einzelne Lücken, die Struktur erzeugt laufend neue.

## Strukturelle Befunde (aus Live-Debugging 2026-08-31)

1. **Mehrere Wahrheitsquellen:** `rec.status` (transcribe) vs.
   `rec.alignment` (realign) vs. `rec.diar_status` (rediarize) vs.
   `progress_note/pct` vs. `phase_started_at` vs. In-Memory-`_jobs` vs.
   DB-Job-Rows. Kein Zustandsübergang ist atomar; Restzustände bleiben
   nach skipped/failed stehen (Befund: note='alignment', pct=1 nach
   skipped; "preparing blinkt mit runtime 8:30").
2. **Race-Fenster:** Zwischen POST und Worker-Start zeigt die UI den
   Restzustand (Change 180 pflastert mit Sofort-note).
3. **Cancel nur zwischen Phasen:** blockierende Calls (sep 3600 s-idle,
   ASR, diar, align, LLM) sind nicht unterbrechbar — Cancel wirkte
   5× ohne Effekt (Befund: Worker hing im sep-HTTP-Transfer).
4. **In-Memory-Queue:** Webapp-Restart killt laufende Jobs; verwaiste
   Zustände (processing/alignment=running) brauchen boot-recovery-
   Pflaster (Change 182).
5. **ETA-Learner:** Ausreißer (hängender Aligner-Call) vergiftet die
   ETA bei kleinen Stichproben (Befund: „~3960–44539m").
6. **UI rät:** activePhaseIndex leitet aus note+pct mit pct-Fallback ab
   (preparing bei pct≤20) statt aus einem Job-Zustand.

## Ziel-Architektur

### A. Job-Zustandsmaschine (eine Quelle der Wahrheit)

Der **DB-Job** (existiert bereits als Row) wird die einzige
Job-Entität:

```
Job {
  id, rec_id, kind: transcribe|align|rediarize|peaks,
  status: queued|running|done|failed|cancelled,
  phase: preparing|separate|asr|diarization|alignment|finalizing|null,
  pct: float, started_at, phase_started_at, heartbeat_at,
  cancel_requested: bool, error: str|null, backend
}
```

- **Atomare Übergänge:** Eine Funktion `job_transition(job, new_status,
  phase=...)` schreibt status+phase+pct+Zeitstempel in EINEM
  DB-Update. Recording-Ableitungsfelder (`status`, `alignment`,
  `diar_status`, `progress_*`) werden **abgeleitet** (Query-Join) oder
  entfallen ganz — die UI liest den Job.
- **pro Recording höchstens ein aktiver Job** (Guarded im Enqueue,
  Change 173 bleibt) — aber jetzt zentral, nicht als Hotfix.

### B. Cancel = persistent + blockierende Calls abbrechbar

- `cancel_requested` ist DB-persistent auf dem Job (überlebt Restarts).
- Der Worker prüft cancel VOR jeder Phase **und** der laufende Call
  wird abbrechbar: (a) Einheitliche Timeouts (idle 60 s, gesamt
  30 min); (b) httpx/requests mit Abbruch über ein Cancel-Event;
  (c) der sep-/ASR-/Aligner-Call läuft mit stream/Read-Timeout und
  der Worker pollt `cancel_requested` währenddessen (kurze Poll-Loops
  statt eines einzigen Riesen-Reads).
- Kill-Fallback: Der Queue-Worker läuft pro Job in einem eigenen
  Thread, dessen Call-Stack über das Cancel-Event unterbrochen wird;
  erst wenn das fehlschlägt, wird der Job auf `failed/cancelled`
  gesetzt und der nächste gestartet.

### C. UI zeigt den Job, nicht geratene Phasen

- Die Chips lesen direkt: aktiver Job → `phase` (kein pct-Fallback).
  Kein aktiver Job → keine aktiven Chips (kein Blinken, keine Zeit).
- `phase_started_at` kommt vom Job (beim Enqueue atomar gesetzt) —
  nie ein Restzustand.
- ETA: nur aus dem Job (Dauer × gelerntem Faktor mit Clipping) und
  nur, wenn ein Job läuft; sonst keine ETA-Anzeige.

### D. ETA-Learner: Ausreißer-Schutz

- Clipping beim Ingest: ms/Gruppe > 120 s → verwerfen (hängender
  Call); Median + Trim auch bei kleinen Stichproben (n≥3).
- Bestehende vergiftete Werte: einmalige DB-Bereinigung.

### E. Persistenz der Queue (Resume-fähig)

- Der In-Memory-`_jobs` bleibt als Ausführungs-Scheduler, aber der
  Job-Zustand lebt in der DB: beim Boot werden `queued`-Jobs wieder
  eingereiht, `running`-Jobs werden **nicht** fortgesetzt, sondern
  ehrlich auf `failed` („Restart") — statt verwaister Zustände
  (Change 182 bleibt als Basisschutz).

## Migrations-Schritte

1. `Job`-Model erweitern (phase, heartbeat_at, cancel_requested —
   teilweise vorhanden).
2. `job_transition()` einführen; alle Worker-Endpunkte (transcribe/
   align/rediarize/peaks) darauf umstellen.
3. Recording-Ableitungsfelder: erst parallel schreiben (kein
   Verhaltensbruch), dann UI auf Job umstellen, dann Felder entfernen.
4. Cancel-Event durch die Calls ziehen (sep/ASR/diar/align/LLM).
5. ETA-Clipping + DB-Bereinigung.
6. Frontend: Chips/Zeit/ETA aus dem Job-Objekt des API-Responses.
7. Bestehende Hotfixes bewerten: 173/174/175/177 bleiben (Grund-
   korrekturen); 178–182 werden durch die Maschine ersetzt/vereinfacht.

### F. Einheitliche Job-Status-Anzeige (eine Komponente, überall identisch)

Es gibt aktuell zwei unterschiedliche Darstellungen (Header oben,
Detailbereich in der Transkription) mit abweichenden Beschreibungen.
Ziel: **eine** Komponente `<JobStatus job={...} />`, die oben UND in
der RecordingCard gerendert wird — identisches Aussehen, identische
Daten (beide aus demselben Job-Objekt):

1. **Was läuft** — Modus + Phase: „Re-Transkription · Trennt Musik"
   (aus `job.kind` + `job.phase`, i18n), nicht mehr frei formulierter
   Text.
2. **Seit wann** — „läuft seit 0:17" (aus `job.phase_started_at`,
   atomar vom Job gesetzt beim Enqueue — nie ein Restzustand).
3. **Wie lange noch** — ETA nur, wenn ein Job läuft UND der Faktor
   plausibel ist (geclippter Learner); sonst KEINE Anzeige (kein
   „~3960–44539m").
4. **Heartbeat nur graphisch** — pulsierender Punkt (fresh = grün
   pulsierend, warn = orange, stalled = rot) mit Tooltip. **Kein Text**
   wie „heartbeat 2s 0%" (Screenshot-Befund 2026-08-31).
5. **Cancelbar** — einheitlicher Cancel-Button (immer sichtbar bei
   laufendem Job, deaktiviert wenn der Job nicht cancelbar ist; aus
   `job.cancel_requested` + Zustandsmaschine).
6. **Progress in %** — nur wenn echte pct-Daten existieren (ASR mit
   on_progress, Alignment „Gruppe X/Y"); sonst kein % (Phase reicht).

Die zwei Orte teilen sich dieselbe Komponente + denselben Job-Payload
aus dem API-Response — keine zweite, abweichende Logik im Header.



- Sollen die Recording-Ableitungsfelder sofort entfallen oder erst
  nach der UI-Umstellung (Empfehlung: parallel, dann entfernen)?
- LLM-Punctuation: Timeout (60 s?) oder komplett optional machen?
