# Change 114 — VAD-Modi: Tasks

## Phase 1 — Backend Modell + Routen

- [x] `models.py`: `TranscriptionRun.vad_mode: str = "off"` (+ docstring)
- [x] `recordings.py`: `vad_mode: str = Form("off")` an upload_recording,
      transcribe_ep (+ Guard), duplicate/crop (Kopie aus src_run),
      retranscribe (Params); Ableitung `enable_vad = vad_mode != "off"`;
      Abwärtskompatibel: `enable_vad=True` → `"edges"` wenn vad_mode "off"
- [x] `url_import.py`: vad_mode durchreichen
- [x] Run-Erzeugung: `run.vad_mode` + `run.enable_vad` setzen (alle Stellen)

## Phase 2 — Backend Service (VAD-Logik + Zeitbasis)

- [x] `_VAD_TRIM`-Gate entfernen; effektive Mode-Berechnung
      (`run.vad_mode or ("edges" if run.enable_vad else "off")`)
- [x] `vad.py`: `squash_silence_with_mapping(audio_bytes) -> (bytes, mapping)`
      (Regionen konkatenieren, mapping [[alt_start, alt_end, new_start], …])
- [x] `service.py`: `_apply_vad(audio_bytes, mode) -> (bytes, vad_meta)`
      (off/edges/all), an 3 Stellen (Job, Re-Align, Re-Diarize)
- [x] `_remap_segments(segments, mapping)` (forward) + inverse Abbildung
      für den Align-Worker; deterministisches Clamping für Lücken/Fugen
      (`_map_time`/`_unmap_time` — Roundtrip exakt für alle
      Regionen-Zeitpunkte, getestet)
- [x] Align-Cache: `write(rec_id, audio_bytes, vad_meta)`; meta.json
      `{"type": "shift"|"map", …}`; `read_vad_meta`; Worker je nach Typ
      kompensieren (Alt-Float-Format kompatibel)

## Phase 3 — Frontend

- [x] `FeatureToggles.tsx`: VAD-Select (aus/Ränder/überall), `vad: string`
- [x] `api.ts`: `vad_mode` in FormData (4 Stellen) + `enable_vad` abgeleitet;
      Recording-Typ `vad_mode?`; hooks `opts.vad_mode`
- [x] `RecordingCard.tsx`: feat.vad string, Initialwert aus r.vad_mode /
      r.enable_vad-Fallback

## Phase 4 — Tests + Verifikation

- [x] Backend: vad_mode-Durchreichung, squash-Mapping, remap forward/inverse
      (+ systematischer Roundtrip inkl. Grenzfälle), Cache-Meta;
      Gesamtsuite grün
- [x] Frontend: Select-Tests, FormData; Suite + tsc grün
- [x] Commit + Push, CI prüfen

## Befund (24.08.)

- `_VAD_TRIM` Default false (Env-Gate) → VAD lief produktiv nie.
- `enable_vad` bool, Default False, in 4 FormData-Funktionen + RetranscribeParams.
- `_shift_segments` (offset) reicht für "all" nicht → Mapping nötig.
- Auto-Migration (db.py `_auto_migrate`) ergänzt fehlende Spalten automatisch.
- Roundtrip: exakt für Zeitpunkte INNERHALB von Speech-Regionen; Zeitpunkte
  in entfernten Lücken werden deterministisch auf die Regionskante geclampt
  (kein Original-Pendant — mathematisch unvermeidbar).
