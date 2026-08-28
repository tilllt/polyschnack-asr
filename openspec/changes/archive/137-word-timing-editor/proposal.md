# Change 137: Word-Timing-Editor (Timing-Tab mit Waveform-Markierung)

**Status:** Archived (auf specs/transcription-view/spec.md angewendet, 2026-08-28)

## Problem

Die Word-Timestamps aus dem Forced-Alignment sind nicht immer präzise
(Aligner-Bins 80 ms, bekannter Offset ~0,1–0,2 s zu spät — Messung Change 019,
Fehlalignments bei Musik/Geräuschen). Es gibt KEINE Möglichkeit, das Timing
eines einzelnen Wortes manuell zu korrigieren:

- Text-Edit (Change 010) baut Wörter neu bzw. erhält nur unveränderte — eine
  gezielte Timing-Korrektur ist nicht möglich.
- Struktur-Operationen (Grenze ziehen, +/−, Split, Segmentlänge) verschieben
  nur die Segment-ZUORDNUNG, nie die Wort-Zeiten.
- Ein Re-Align (Change 046) ersetzt ALLE Timestamps — auch die, die der User
  manuell nachjustiert hat.

Der User will (2026-08-28): die Waveform auf das Timing EINES Wortes
heranzoomen (Wort belegt ~30 % der Ansicht), die Markierung = Alignment
(Anfang, Ende, Länge) sehen und durch Ziehen der Markierung das Wort-Timing
manuell präzisieren. Manuelle Korrekturen sollen gegen spätere Re-Aligns
geschützt sein (Override-Marker, User-Entscheid).

## Ziel

- Der Editor-Bereich der RecordingCard bekommt **zwei Tabs**: „Transkription"
  (bestehender Text-Editor) und „Timing" (neu).
- **Timing-Tab:** Waveform-Detailansicht + Wortliste (read-only). Klick auf ein
  Wort zoomt die Waveform so heran, dass das Wort ca. **30 % der sichtbaren
  Zeitspanne** belegt; die **Markierung** zeigt das aktuelle (Alignment-)Timing:
  Anfang, Ende, Länge.
- **Drag an der Markierung** (Start-/Ende-Handles) ändert `start`/`end` des
  Wortes — manuelle Präzisierung, gespeichert per PATCH; das Wort bekommt ein
  **Override-Flag**.
- **Alle anderen Edit-Funktionen sind im Timing-Tab deaktiviert:** kein
  Text-Edit, kein Sprecher-Edit/Rename, keine Segmentgrenzen verschieben, kein
  +/−/Split, kein Re-Segmentieren. Playback/Seek bleiben (Wort anhören).
- **Override-Schutz:** Ein späterer Re-Align überschreibt manuell korrigierte
  Wörter nicht; alle anderen Wörter werden normal neu getimt.
- Position/Länge kommen aus dem **letzten Alignment** (aktueller
  `words[].start/end`-Stand in den Segmenten — Align-Phase Change 045/078/124,
  Re-Align Change 046/101) — der Timing-Tab startet KEIN neues Alignment.

## Nicht-Ziel

- Kein neuer Alignment-Lauf im Timing-Tab (nutzt den letzten Align-Stand).
- Keine Text-Änderungen im Timing-Tab (Wort-TEXT ist Sache des
  Transkription-Tabs; hier geht es nur um Zeiten).
- Kein Loop-/Auto-Follow-Playback in v1 (Zoom-Fenster = 3,3× Wortdauer hält
  das Wort beim Abspielen lange sichtbar; reicht fürs akustische Prüfen).
- Kein Batch-Editing mehrerer Wörter gleichzeitig.

## Kontext

- **Datenmodell:** `Recording.segments` (JSON) enthält je Segment
  `words[]` mit `{word, start, end}` — die „letzte Alignment"-Quelle. Die
  Segment-Grenzen (`start`/`end`) sind erstes/letztes Wort.
- **Re-Align:** `app/service.py::_run_align_phase` ersetzt die Wort-Timestamps
  durch akustisch verifizierte Grenzen (crispr-align); `_run_background_align`
  (Change 045) hat einen Versions-Guard (parallele Edits → Ergebnis verworfen).
- **Frontend:** `RecordingCard.tsx` rendert `WaveformPlayer` (WaveSurfer 7,
  Zoom über px/s — `doZoom`, `ZOOM_STEPS`, beliebige pps seit Change 083;
  Zoom-Reset-Guards Change 100) und `SegmentList.tsx` (Wort-Spans,
  Klick-Seek zum Wortstart mit 280-ms-Doppelklick-Schutz — Req 2; alle
  Edit-Funktionen Req 3–7).
- **Invariante (Req 10):** Struktur-Ops erhalten Timestamps 1:1
  (`flattenWords`); der Timing-Edit ist die zweite dokumentierte Ausnahme
  (wie Text-Edit Change 010) — er ändert gezielt start/end GENAU EINES Wortes,
  Reihenfolge bleibt monoton.
- **WaveSurfer 7 hat kein Regions-Plugin** → Markierung als eigenes Overlay
  über dem Waveform-Canvas (Vendor-Patch-Muster existiert bereits:
  `src/vendor/` + Vite-Alias).

## Changes

- **Backend — neuer Endpoint:** `PATCH /api/recordings/{rid}/segments/{idx}/words/{word_idx}`
  mit `{start, end}` — Auth + `ensure_access(write)` + `snapshot("edit")`
  (Versionierung wie `update_segment`). Validierung: `start < end`,
  Monotonie gegen Nachbarwörter (`start_i >= end_{i-1}`, `end_i <= start_{i+1}`,
  Lücken erlaubt — wie ASR sie liefert). Setzt `words[word_idx].override = true`
  und leitet die Segment-Grenzen aus erstem/letztem Wort neu ab (SRT/VTT/Export
  bleiben konsistent). Response = aktualisierte `segments` (Muster
  `update_segment`). Tests nach Muster `test_segment_edit.py` (eigene SQLite-DB).
- **Backend — Re-Align erhält Overrides:** Nach dem Align-Lauf stellt der
  Anwendungs-Schritt (Change 078: globale Sammlung → Zuordnung) für alle
  Wörter mit `override=true` die manuellen `start`/`end` aus der Baseline
  wieder her (Index-Zuordnung bei unveränderter Wortzahl des Segments; bei
  Text-Änderung wird der Override verworfen — der Versions-Guard verwirft
  ohnehin bei parallelen Edits). Alle anderen Wörter bekommen die frisch
  alignten Zeiten. Tests: Override überlebt Re-Align; Nicht-Override wird neu
  getimt.
- **Frontend — Tabs:** `RecordingCard` — der Editor-Bereich bekommt die Tabs
  „Transkription | Timing" (i18n de/en/pt-BR). Transkription-Tab = heutiges
  Verhalten unverändert.
- **Frontend — TimingEditor (neu):** Wortliste read-only (Klick lädt das Wort)
  + Waveform im Timing-Modus: `pps = 0.3 * Containerbreite / Wortdauer` (Wort
  belegt 30 % der sichtbaren Zeitspanne), geclampt auf sinnvolle Grenzen;
  Seek zum Wortstart. **Marker-Overlay** über dem Canvas: hervorgehobener
  Bereich mit Start-/Ende-Handles, px↔Zeit via pps + scrollLeft (Muster
  Klick-Seek), Anzeige Start/Ende/Länge. Drag (Pointer-Events, Touch-tauglich)
  → optimistisches Update, onDragEnd → PATCH; bei Fehler Toast + Rollback
  (User-Regel: sichtbares Feedback, stille Fehler inakzeptabel).
- **Frontend — SegmentList `readOnly`-Prop:** im Timing-Tab sind alle
  Edit-Interaktionen aus (kein Doppelklick-Edit, kein Speaker-Dropdown, kein
  Grenz-Drag, kein +/−/Split); Wort-Klick = Auswahl/Laden statt nur Seek.
- **Frontend — Override entfernen:** kleiner „Reset"-Button am geladenen Wort
  (löscht das Override-Flag; das Wort behält seine aktuelle Zeit bis zum
  nächsten Re-Align).
- **OpenSpec:** Req-Delta in `transcription-view` (s. Spec-Datei).

## Downgrade

- Tabs + TimingEditor-Komponente entfernen (RecordingCard rendert wieder nur
  den Transkription-Tab).
- `PATCH .../words/{word_idx}`-Endpoint + `override`-Handling entfernen.
- Re-Align-Merge entfernen → Re-Align überschreibt wieder alle Timestamps
  (Verhalten wie vor Change 137).
