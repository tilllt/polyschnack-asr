# Change 137 — Tasks (Word-Timing-Editor)

## 1. Backend: PATCH Wort-Timing

- [ ] `app/routers/segments.py`: `PATCH /recordings/{rid}/segments/{idx}/words/{word_idx}`
      mit `{start, end}` — Auth + `ensure_access(write)` + 401-Guard
      (Muster `update_segment`), `snapshot("edit")`
- [ ] Validierung: `start < end`, Mindestdauer 20 ms, Monotonie vs. Nachbarn
      (`start_i >= end_{i-1}`, `end_i <= start_{i+1}` — Lücken erlaubt);
      400 mit verständlicher Meldung, 404 bei ungültigem idx/word_idx
- [ ] Setzt `words[word_idx].override = true`; Segment-Grenzen aus
      erstem/letztem Wort neu ableiten (`seg.start`/`seg.end`); `rec.text`
      unverändert; Response = komplette `segments` (tiefe Kopie vor
      SQLAlchemy-Write)
- [ ] Tests `tests/test_word_timing.py` (Muster `test_segment_edit.py`, eigene
      SQLite-DB): 401 ohne Login, 400 start>=end / Mindestdauer / Monotonie,
      Override-Flag gesetzt, Segment-Grenzen abgeleitet, Snapshot-Version,
      Roundtrip erhält Nachbar-Wörter

## 2. Backend: Re-Align erhält Overrides

- [ ] `app/service.py` (`_run_align_phase`, Change-078-Zuordnungs-Schritt):
      Baseline-Wörter mit `override=true` nach dem Align-Lauf je Segment per
      Index wiederherstellen; bei abweichender Wortzahl Override verwerfen
- [ ] Tests: Override-Wort behält manuelle Zeit nach Re-Align; Nicht-Override
      bekommt neue Zeit; Text geändert → Override verworfen (kein Crash)

## 3. Frontend: Tabs „Transkription | Timing"

- [ ] `RecordingCard.tsx`: Editor-Bereich bekommt Tab-Leiste (Transkription |
      Timing), aktiver Tab als State; Transkription-Tab = heutiges Verhalten
- [ ] i18n-Keys (de/en/pt-BR): `editor_tab_transcription`, `editor_tab_timing`
- [ ] Timing-Tab rendert `TimingEditor` (neu), Transkription-Tab `SegmentList`

## 4. Frontend: TimingEditor — Wortliste + Laden

- [ ] `src/components/TimingEditor.tsx` (neu): read-only-Wortliste/Transkript
      (Segmente + Wort-Spans); Klick auf ein Wort → aktives Wort + Waveform
      lädt das Wort (Zustand in RecordingCard oder TimingEditor)
- [ ] Aktives Wort visuell markiert (Karaoke-Stil, kein Konflikt mit
      `karaoke-active` — eigener CSS-Klasse)

## 5. Frontend: Waveform-Timing-Modus (30 %-Zoom)

- [ ] `WaveformPlayer.tsx`: Prop/Variante „Timing-Modus" — `pps =
      0.3 * Breite / Wortdauer`, geclampt (`MAX_TIMING_PPS`, Untergrenze
      fitPps), Seek zum Wortstart, Zoom-Gate Change 100 beachten
- [ ] Wortwechsel (Klick) aktualisiert Zoom + Seek ohne Player-Neubau

## 6. Frontend: Marker-Overlay + Drag + PATCH

- [ ] Marker-Overlay über `ws.getWrapper()`: Highlight-Bereich + Start-/Ende-
      Handles, px↔Zeit via pps + scrollLeft; Anzeige Start/Ende/Länge
      (Formatierung wie bestehende Zeitcodes)
- [ ] Drag-Handles (Pointer-Events, Touch): Clamp an Nachbar-Grenzen +
      Mindestdauer; während des Drags lokaler State, onDragEnd → PATCH
      `.../words/{word_idx}` (optimistisch), Erfolg → Toast ok + Wortliste
      aktualisieren; Fehler → Toast err + Rollback
- [ ] „Reset"-Button am geladenen Wort: löscht Override-Flag (PATCH mit
      `override: false`), Wort behält Zeit bis zum nächsten Re-Align

## 7. Frontend: SegmentList readOnly-Prop

- [ ] `SegmentList.tsx`: `readOnly`-Prop — deaktiviert Doppelklick-Edit,
      Speaker-Dropdown/Rename, Grenz-Drag, +/−/Split, Re-Segmentierung;
      Wort-Klick = `onWordClick`-Callback (Timing-Tab) statt nur Seek
- [ ] Im Timing-Tab mit `readOnly` gerendert; Transkription-Tab unverändert

## 8. Frontend-Tests (Vitest)

- [ ] Zoom-Formel: `pps = 0.3 * Breite / Wortdauer` inkl. Clamping
      (sehr kurzes / sehr langes Wort)
- [ ] px↔Zeit-Mapping (Marker-Position, Handle-Drag bei scrollLeft ≠ 0)
- [ ] Marker-Clamp: Handle kann Nachbar-Grenze nicht überschreiten;
      Mindestdauer eingehalten
- [ ] PATCH-Payload (start/end/override), Rollback bei Fehler
- [ ] `readOnly`: alle Edit-Interaktionen aus, Wort-Klick feuert Callback
- [ ] tsc clean + `npm run build` OK

## 9. GUI-Test gegen laufendes System (Playwright)

- [ ] Testaufnahme (JS-WAV) uploaden → transkribieren (Align an) → Timing-Tab
      → Wort klicken → Waveform gezoomt (Markierung ≈ Wortbereich) → Handle
      ziehen → PATCH verifizieren (API-Wert + Anzeige) → Re-Align → Override
      behalten
- [ ] Mobile-Check (Viewport, Touch-Drag auf Handle)
- [ ] Testskripte im Repo-Muster (`/opt/data/perf-prof/`-Stil oder dev-server)

## 10. OpenSpec archivieren (nach Umsetzung)

- [ ] Spec-Delta (`changes/137/.../specs/transcription-view/spec.md`) nach
      `openspec/specs/transcription-view/spec.md` anwenden
- [ ] `changes/137` nach `changes/archive/` verschieben, Status Archived,
      `specs`-Unterordner entfernen; Projekt-README-Konvention beachten

## 11. Commit, Push, CI

- [ ] Commit(s), Push direkt auf main, CI-Watch bis success (Jobs melden)
