# Change 137 — Design-Entscheidungen (Word-Timing-Editor)

## 1. 30 %-Zoom: Formel + Clamping

**Ziel:** Wortdauer belegt ~30 % der sichtbaren Zeitspanne.

```
visible_duration = Wortdauer / 0.30
pps = Containerbreite_px / visible_duration = Containerbreite_px * 0.30 / Wortdauer
```

- WaveformPlayer kann seit Change 083 beliebige px/s (nicht nur `ZOOM_STEPS`) —
  `doZoom`-Erweiterung um eine explizite pps-Variante (oder direkter
  `ws.zoom(pps)`-Aufruf mit dem bestehenden Zoom-Gate „Audio geladen", Change 100).
- **Clamping:** sehr kurze Wörter (< 100 ms) → pps explodiert. Obergrenze
  z. B. `MAX_TIMING_PPS = 2000 px/s` (unter der Peaks-Auflösung rendert die
  Wellenform gestreckte Balken — akzeptabel); Untergrenze `fitPps` (Wort länger
  als das Fenster → nie kleiner als die Fit-Auflösung).
- Seek zum Wortstart nach dem Zoom (`ws.setTime(word.start)`).

## 2. Marker als eigenes Overlay statt WS7-Plugin

WaveSurfer 7 hat **kein Regions-Plugin** mehr. Optionen:
- (a) Eigenes Overlay: absolutes Div über dem Waveform-Canvas-Container,
  Hintergrund-Highlight + zwei Drag-Handles, Positionen aus `pps + scrollLeft`
  (`px = (t − scrollLeft/pps) * pps`-Umkehrung des bestehenden Klick-Seek).
- (b) Vendor-gepatchtes Regions-Plugin (wie timeline/record in `src/vendor/`).

**Gewählt: (a).** Volle Kontrolle über Interaktion (Handles, Cursor, Touch),
kein fremder Plugin-Code, px↔Zeit-Mapping existiert als Muster bereits
(Klick-Seek). Der Overlay-Container wird über `ws.getWrapper()` positioniert
(Shadow-DOM: WaveSurfer-Canvas liegt im Shadow-Root — Overlay außerhalb des
Shadow-Roots, aber über dem Container, koordinieren über Container-BoundingBox
+ scrollLeft).

## 3. PATCH pro Wort statt PUT-Ganzliste

Der Grenz-Drag nutzt `PUT /segments` (ersetzt die komplette Liste). Für die
Wort-Timing-Korrektur ist ein **granularer PATCH** (`.../words/{word_idx}`)
besser: kleinere Payload, keine Klon-/Merge-Races mit parallelen Edits,
Muster `update_segment` (Auth/`ensure_access(write)`/`snapshot("edit")`).
Response = komplette `segments`-Liste (wie `update_segment`), damit das
Frontend seine Anzeige 1:1 übernehmen kann.

## 4. Monotonie-Regel + Clamp statt Fehler

ASR-Wort-Timestamps haben Lücken und (selten) Überlappungen. Regel für die
Korrektur: `start_i >= end_{i-1}` und `end_i <= start_{i+1}` (Lücken erlaubt),
`start < end`, Mindestdauer 20 ms. Beim Drag wird **geclampt** (nicht
abgelehnt): Der Handle kann nicht über die Nachbar-Grenze gezogen werden —
verhindert kaputte Reihenfolgen, ohne den User mit Fehlermeldungen zu nerven.

## 5. Override-Flag + Re-Align-Merge

- `words[].override = true` auf dem korrigierten Wort (JSON-Feld, bleibt bei
  PUT-/PATCH-Roundtrips erhalten — `replace_segments` macht tiefe Kopien).
- **Re-Align:** `_run_align_phase` sammelt die alignten Wörter global und
  ordnet sie danach zu (Change 078). Dort wird gemergt: Wörter mit
  `override=true` aus der Baseline behalten ihre manuellen `start`/`end`;
  alle anderen bekommen die frisch alignten Zeiten. Index-Zuordnung je Segment
  (der alignte Text entspricht dem Segment-Text — Overrides ändern den Text
  nicht); weicht die Wortzahl ab (Text wurde geändert), Override verwerfen.
- Versions-Guard (Change 045) bleibt unberührt: parallele Edits während des
  Aligns verwerfen das Ergebnis ohnehin.

## 6. Optimistisches UI mit Rollback

User-Regel: sichtbares Feedback, stille Fehler inakzeptabel, Fortschritt nur
echt. Drag ist live (nur lokal), onDragEnd → PATCH. Bei Fehler: Toast (err) +
Anzeige auf den letzten Serverstand zurück. Beim Erfolg: Toast (ok) + Wortliste
aktualisiert. Kein Spinner während des Drags (der Drag IST die Interaktion);
nur der Save-Vorgang nach dem Loslassen zeigt kurz einen Zustand.

## 7. Kein Loop-/Auto-Follow-Playback in v1

Playback im Timing-Tab startet am Wortanfang; das Zoom-Fenster (3,3× Wortdauer)
hält das Wort beim Abspielen sichtbar, bis der Playhead es verlässt (nach ~3,3
Wortdauern). Ein Wort-Loop oder Auto-Follow wäre nettes Extra, aber Aufwand
(neue Playback-Modi, Kollision mit `claimExclusivePlayback`/Space-Handler) —
bewusst nicht in v1. Sichtbarkeit der Markierung bleibt durch den großen
Zoom-Fenster-Rand gewährleistet.

## 8. Mobile / Touch

Pointer-Events (Muster Grenz-Drag `onBoundaryPointerDown/Move/Up`), Handles mit
Touch-Targets ≥ 40 px; Klick-Seek-Schutz (280 ms Doppelklick) gilt im
Timing-Tab nicht (kein Text-Edit → Klick = Wort laden, kein Doppelklick-Edit).

## 9. Abgrenzung Invariante (Req 10)

Bisherige Ausnahme: Text-Edit (Change 010). Neu: **Timing-Korrektur** ändert
gezielt `start`/`end` genau eines Wortes (plus `override`-Flag) — die
`flattenWords`-Invariante gilt weiterhin für Struktur-Operationen; die
Timing-Korrektur ist dokumentierte zweite Ausnahme, aber die Reihenfolge der
Wörter (chronologisch, monoton) bleibt per Clamp garantiert.

## Offene Punkte

- Keine kritischen offenen Punkte. „Reset"-Button (Override entfernen) ist in
  v1 enthalten (klein, verhindert Sackgassen).
