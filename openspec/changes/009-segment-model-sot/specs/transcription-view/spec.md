## MODIFIED Requirements

### Requirement: Grenzen verschieben (ein Segment-Modell, keine zweite Wahrheit)

- **Ablauf:** Timecode-Marker zwischen den Segmenten ziehen (nach oben =
  Segment N verliert am Ende Wörter, N+1 gewinnt vorne; nach unten =
  umgekehrt), Wort für Wort, nie geteilt, Rand-Clamp. Beim Loslassen
  `PUT /api/recordings/{rid}/segments` ersetzt die komplette Liste
  (tiefe Kopie; `rec.text` neu; Versions-Snapshot `kind="edit"`).
- **Duplikat-Freiheit (bleibt):** `dragRef.baseSegments` eingefroren,
  `moveBoundary(base, idx, KUMULATIVES words)`, `currentList` beim
  Loslassen explizit an `onBoundaryDragEnd`.
- **Ein-Modell-Architektur (Change 009, ersetzt dragSegments-Overlay):**
  Die Segment-Wahrheit lebt NUR im Recording-Modell (Cache/Server).
  Das persistierte Feld `segments_manual: bool` markiert „manuelle
  Aufteilung aktiv" (gesetzt durch jede Segment-Struktur-Operation,
  zurückgesetzt bei Transcribe/Retranscribe/Restore). Die Anzeige ist
  eine reine Funktion:
  `displaySegments = deriveSegments(segments, segMaxDuration)` —
  `segments_manual == true` → `segments` direkt (keine erneute
  Re-Segmentierung, die manuelle Grenze verschwindet nie aus der
  Anzeige); sonst → `resegmentByDuration` bei gesetzter
  Segmentlänge, sonst `segments`.
- **Kein `dragSegments`-State, kein Reset-Effekt:** Die Drag-Preview
  bleibt lokal in `SegmentList` (`dragRef.currentList`); beim
  Loslassen ein optimistisches Cache-Update (`next` +
  `segments_manual: true`), PUT im Hintergrund, bei Server-Fehler
  Rollback auf den vorherigen Modell-Stand + Fehler-Toast. PUT-Guard
  „letzter Drag gewinnt" (monotone Sequenznummer) bleibt für parallele
  PUTs.
- **Architektur:** `src/resegment.ts` (moveBoundary, buildSeg),
  `SegmentList.tsx` (Drag-Handler, lokale Preview), `RecordingCard.tsx`
  (`deriveSegments`, optimistisches Commit, Rollback),
  `app/models.py` (+`segments_manual`), `app/routers/segments.py`
  (PUT setzt Flag), `service.py` (Transcribe/Retranscribe/Restore
  setzen Flag zurück).

#### Scenario: Grenze ziehen bei gesetzter Segmentlänge — Anzeige bleibt

- **Akteure:** Besitzer.
- **Eingaben:** Segmentlänge auf 3 s (4 Buckets), erste Grenze um ein
  Wort nach unten ziehen, loslassen, 1 s warten.
- **Ergebnis:** Anzeige zeigt sofort und dauerhaft die neue Grenze
  (`w0 w1 w2 w3 | w4 w5 | …`); kein Zurückspringen auf die
  Auto-Aufteilung (Anzeige == Modell == Server); Reload bestätigt
  denselben Stand (`segments_manual` persistiert).

#### Scenario: Re-Transkription verwirft manuelle Grenzen

- **Akteure:** Besitzer.
- **Eingaben:** Nach manuellen Grenz-Verschiebungen Retranscribe
  auslösen.
- **Ergebnis:** Neue ASR-Segmente ersetzen die Liste, `segments_manual`
  wird `false` — die Auto-Aufteilung (bzw. Re-Segmentierung nach
  Segmentlänge) gilt wieder; keine veraltete manuelle Liste bleibt
  stehen.

#### Scenario: Zwei Drags kurz nacheinander

- **Akteure:** Besitzer.
- **Eingaben:** Grenze 2 Wörter ziehen und loslassen, unmittelbar
  danach 1 Wort zurück; die erste PUT-Antwort trifft verzögert ein.
- **Ergebnis:** Endstand = zweiter Drag; die verzögerte Antwort
  überschreibt ihn nicht (PUT-Guard).
