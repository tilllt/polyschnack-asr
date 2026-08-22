# Design — Change 082

## D1: Backend — `app/eta.py` (neu)

```python
ASR_RTF = {  # Benchmark 22.08. (RTX 3090/3060, Change-080-Testset)
    "ps-pk-onnx": 0.071, "crispr-pk-cpp": 0.056, "crispr-qwen3": 0.081,
    "crispr-moonshine-de": 0.073, "crispr-canary": 0.067,
    "crispr-whisper-large-v3": 0.199,
    # whisper-turbo: nie gemessen (Pull-Stall) → bewusst KEIN Eintrag (keine ETA)
}
DIAR_RTF = {"energy": 0.02, "foxnose": 0.2, "pyannote": 0.4}  # konservativ, kalibrierbar
OVERHEAD = {"vad": 0.03, "enhance": 0.1, "noise_reduce": 0.05}

def estimate_eta_s(duration_s, backend, enable_vad, enable_diarize,
                   diarize_method, enable_noise_reduce, enable_enhance,
                   elapsed_s) -> tuple[int, int, int] | None:
    """→ (rest_s, rest_low_s, rest_high_s) oder None (kein RTF bekannt)."""
```

- `rest = max(0, duration_s × (asr + diar + overheads) − elapsed_s)`
- Bereich: `rest × 0.7` … `rest × 1.3` (mind. 5 s) — ehrliche Spanne, kein
  Scheinwert.
- `None`, wenn: kein `duration_s`, unbekanntes Backend, `rest ≈ 0`.

## D2: Backend — Felder & Serialisierung

- `Recording.processing_started_at` (Optional datetime) — Job-Beginn; die
  bestehende `_auto_migrate()` (db.py) ergänzt die Spalte per
  `ALTER TABLE ADD COLUMN`.
- `set_processing()` (crud.py): `processing_started_at = now` (Heartbeat-
  Zeitstempel werden dort bereits frisch gesetzt).
- `service.py` (Z. ~1384): `backend = rec.backend or "ps-pk-onnx"` →
  `rec.backend = backend` zurückschreiben, damit das Dict den Backend-
  Namen während processing führt (bei 297 war er None).
- `_recording_to_dict` (recordings.py): bei `status == "processing"` →
  `eta_total_s`, `eta_low_s`, `eta_high_s` (int|None) aus
  `estimate_eta_s(...)`; zusätzlich `processing_started_at` serialisieren
  (via `iso_utc`).

## D3: Frontend — Heartbeat-Visualisierung

- `heartbeatState` (RecordingCard.tsx): neues Feld
  `level: "fresh" | "warn" | "stalled"` (≤8 s / ≤45 s / >45 s).
- Neue Aktivitätszeile (ersetzt die reine pct-Zeile nicht, ergänzt sie):
  - Ampel-Punkt: grün `animate-pulse` bei fresh, gelb bei warn, rot bei
    stalled.
  - Live-Zähler: lokales 1-s-Intervall re-rendert; Anzeige
    „Herzschlag vor {n}s" (`progress_heartbeat_ago`) — springt bei jedem
    Poll auf 0 zurück.
  - Aktiver Phasen-Chip: „· läuft seit mm:ss" (bestehende `fmtTime`,
    `sincePhase`).
- i18n de/en/pt: `progress_heartbeat_ago`, `progress_phase_since`,
  `progress_eta_range`, `progress_processing_since`.

## D4: Frontend — ETA (Fake raus, echt rein)

- `updateEta`/`etaFromRate` (Rate-ETA) ENTFERNEN.
- ETA-Zeile: bei `r.eta_low_s`/`r.eta_high_s` →
  „noch ca. 4–7 min (geschätzt)" (`fmtEtaRange` + `progress_eta_range`);
  sonst Fallback „verarbeitet seit Xs" (`secondsSince(processing_started_at)`).
- `progress_pct` bleibt sichtbar (echter Backend-Wert).

## D5: Tests

- Backend: `tests/test_eta.py` — RTF je Backend, Diar-Methoden, unbekanntes
  Backend → None, elapsed > total → 0; `set_processing` setzt
  `processing_started_at`; Dict enthält eta-Felder bei processing.
- Frontend: `progress-heartbeat.test.ts` — `level`-Logik; `fmtEtaRange`
  (Bereiche, „ca. 4–7 min"); Regression: kein `etaFromRate`-Pfad mehr.

## Phase 2 (skizziert, NICHT in diesem Change)

Selbstlernendes RTF: aus abgeschlossenen Jobs (`duration_s`,
`processing_ms`) gleitenden Mittelwert je Backend+GPU in einer kleinen
Tabelle (`backend_stats`) bilden → `estimate_eta_s` nutzt gemessene statt
statischer Raten. Voraussetzung: `processing_started_at` (D2) als
verlässlicher Job-Start.
