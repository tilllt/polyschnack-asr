# Change 114 — VAD user-konfigurierbar: zwei Trim-Modi (ohne Env-Gate)

## Proposal

### Problem (User-Auftrag, 24.08.)

VAD-Trim ist aktuell doppelt optional und standardmäßig komplett aus:
1. **Env-Gate:** `_VAD_TRIM = os.getenv("VAD_TRIM_SILENCE", "false")`
   (service.py Z. 297) — ohne `VAD_TRIM_SILENCE=true` läuft VAD **nie**,
   selbst wenn der User `enable_vad` setzt.
2. **User-Option:** `enable_vad: bool = Form(False)` (bool, an/aus).

Der User will: VAD **ohne Env** rein user-konfigurierbar, mit **zwei Modi**:
- „Stille am Anfang & Ende wegschneiden" (leading/trailing, aktuelles Verhalten)
- „Stille überall wegschneiden" (alle Stille-Lücken ≥ min_silence zwischen
  Speech-Regionen ebenfalls entfernen → Regionen werden konkateniert)

### Design

**Modell:** `TranscriptionRun.vad_mode: str = "off"` (Werte `off` | `edges` |
`all`). `enable_vad: bool` bleibt als Legacy (effektive Mode-Berechnung:
`run.vad_mode or ("edges" if run.enable_vad else "off")`). Auto-Migration
(db.py `_auto_migrate`) legt die Spalte per ALTER TABLE an.

**Routen:** `vad_mode: str = Form("off")` an allen Stellen, die Runs erzeugen
(Upload, Transcribe, Retranscribe-Params, Duplicate/Crop-Kopie aus src_run,
URL-Import). Abwärtskompatibel: `enable_vad=True` ohne `vad_mode` → `"edges"`.
Runs speichern `vad_mode` + abgeleitet `enable_vad`.

**Service (Env-Gate entfällt):**
- `_apply_vad(audio_bytes, mode)` → `(bytes, vad_meta)`:
  - `off` → unverändert, `None`
  - `edges` → bisheriges Trim, `{"type": "shift", "offset_s": x}`
  - `all` → Regionen (mit Pad) ausschneiden + konkatenieren,
    `{"type": "map", "mapping": [[alt_start, alt_end, new_start], …]}`
- Zeitbasis: `edges` nutzt `_shift_segments(+offset)` wie bisher. `all` nutzt
  neues `_remap_segments(segments, mapping)` (forward: Original → getrimmt)
  und im Align-Worker die inverse Abbildung (getrimmt → Original), analog zur
  bisherigen Shift-Kompensation (Z. 922–924 / 941–942).

**Align-Cache:** `write(rec_id, audio_bytes, vad_meta)` — meta.json trägt
`{"type": "shift", "offset_s": …}` oder `{"type": "map", "mapping": […]}`;
`read_meta` bleibt als Kompatibilitäts-Leser für altes Float-Format, neu
`read_vad_meta` liefert das Dict. Aufrufer: Job-Fluss (Z. ~1772),
`_schedule_realign` (Z. ~1119).

**Frontend:** FeatureToggles: VAD-MiniToggle → Select mit 3 Optionen
(VAD: aus / Ränder / überall). `FeatureValues.vad: string`. api.ts sendet
`vad_mode` (+ `enable_vad` abgeleitet, für alte Backends). RecordingCard liest
`r.vad_mode` (Fallback `enable_vad ? "edges" : "off"`).

### Nicht-Ziel

- Kein VAD-Export als eigenständiges Ergebnis (bleibt Preprocessing).
- Keine Änderung an Silero-Modell/Parametern (Threshold 0.5, min_speech 250 ms,
  min_silence 400 ms, Pad 120 ms).
- `VAD_TRIM_SILENCE`-Env wird ignoriert (kein Gate mehr).

### Verifikation

- Backend-Tests: vad_mode-Durchreichung (Upload/Transcribe/Retranscribe),
  `squash`-Mapping (pure Funktion), `_remap_segments` forward/inverse,
  Align-Cache-Meta (shift/map, Alt-Format).
- Frontend-Tests: Select-Optionen, FormData enthält vad_mode.
- Nach Deploy: Aufnahme mit „Stille überall" → kürzeres Audio, Karaoke-
  Timestamps stimmen gegen die Originaldatei (Klick = richtiger Ton).
