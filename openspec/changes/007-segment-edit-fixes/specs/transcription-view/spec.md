## MODIFIED Requirements

### Requirement: Karaoke-Hervorhebung (Lead nur während Playback)

- **Ablauf:** `activeWordIndex(words, currentTime)` erhält den Vorlauf
  `KARAOKE_LEAD_S` nur, während die Wiedergabe läuft. Im pausierten/gestoppten
  Zustand wird mit `leadS = 0` gerechnet — die Markierung bleibt exakt an der
  Stopp-Position, auch wenn diese nahe einer Wortgrenze liegt.
- **Verdrahtung:** `WaveformPlayer` meldet den Play-Zustand über die bereits
  existierende Prop `onPlayStateChange` (play/pause/finish); `RecordingCard`
  reicht den Zustand an `SegmentList` weiter.
- **Architektur:** `src/components/RecordingCard.tsx` (playing-State),
  `src/components/SegmentList.tsx` (leadS-Auswahl), `src/karaoke.ts`
  (Signatur unverändert).

#### Scenario: Stop nahe Wortgrenze

- **Akteure:** Besitzer der Aufnahme.
- **Eingaben:** Wiedergabe starten, bis kurz vor dem Ende eines Wortes
  abspielen (z. B. t = 1.85 s bei Wortende 2.0 s), stoppen.
- **Ergebnis:** Die Karaoke-Markierung zeigt das zuletzt gehörte Wort
  (start ≤ t), nicht das nächste (start ≤ t + 0.15).

### Requirement: Grenzen verschieben (Persistenz + Anzeige konsistent)

- **Ablauf:** Beim Loslassen einer Grenze speichert `replaceSegments` (PUT);
  die Server-Liste wird in Cache und Anzeige übernommen. Die Anzeige zeigt
  danach **immer** die gespeicherte Grenze — auch wenn `segMaxDuration`
  gesetzt ist (Anzeige = Re-Segmentierung der ASR-Segmente + manuelle
  Grenzen als eine Liste, keine zweite Wahrheit).
- **Reset-Semantik:** Manuelle Grenzen verfallen nur, wenn sich der
  Segment-INHALT wirklich ändert (z. B. Retranscribe: andere Wortfolge,
  andere Wortanzahl) — nicht wenn der Server dieselbe Liste bestätigt.
  Der Reset-Vergleich nutzt die Wort-Invariante (`flattenWords`), keine
  Objekt-Referenzen.
- **Race-Schutz:** Mehrere PUTs in schneller Folge sind möglich (Drags kurz
  nacheinander). Es gewinnt immer der neueste Drag: Antworten älterer PUTs
  werden verworfen (monotone Drag-Sequenznummer), damit eine langsame
  Antwort keinen neueren Stand überschreibt.

#### Scenario: Grenze ziehen bei gesetzter Segmentlänge

- **Akteure:** Besitzer der Aufnahme.
- **Eingaben:** Segmentlänge auf 3 s stellen (4 Buckets), erste Grenze um
  ein Wort nach unten ziehen, loslassen, 1 s warten.
- **Ergebnis:** Die Anzeige zeigt sofort die neue Grenze (w0 w1 w2 w3 |
  w4 w5 | …) und bleibt dabei — kein Zurückspringen auf die Auto-Aufteilung.
  Ein Reload bestätigt denselben Stand.

#### Scenario: Zwei Drags kurz nacheinander

- **Akteure:** Besitzer der Aufnahme.
- **Eingaben:** Grenze um 2 Wörter ziehen und loslassen, unmittelbar darauf
  dieselbe Grenze um 1 Wort zurückziehen und loslassen; die erste
  PUT-Antwort trifft verzögert ein (nach der zweiten).
- **Ergebnis:** Der Endstand entspricht dem zweiten Drag (1 Wort verschoben);
  die verzögerte Antwort des ersten Drags überschreibt ihn nicht.
