# Change 209 — Nachbar-Marker (n-1/n+1) mit automatischem Schrumpfen

**Nutzer-Vorgabe 19.09.2026 (wörtlich):**

> „Lass uns die Range marker fuer das aktuelle Wort, für n+1 und n-1 anzeigen. Die Range marker des
> Wortes davor und danach schrumpfen automatisch wenn man den aktuellen Marker gegen ihren Anfang
> oder ihr Ende zieht. Wenn man in n-1 oder n+1 clickt oder einen ihrer Marker anfaeesst werden sie
> automatisch zum aktuellen wort."

## Warum das auch den Server betrifft

Der Timing-Tab darf nur Wörter ändern, nie Segment-Grenzen (Change 155). Für den Wort-Flow gilt
zusätzlich eine **Monotonie-Invariante**: kein Überlappen, Reihenfolge bleibt chronologisch. Diese
Invariante wurde bisher **hart durchgesetzt**: `PATCH …/words/{i}` lieferte 400, sobald das neue
Timing über das Nachbarwort hinausreichte („start must not precede previous word end"). Das Frontend
clamp-te den Drag deshalb an der Innenkante des Nachbarn ab — genau das, was der Nutzer jetzt
aufheben will.

Deshalb: die Invariante bleibt (keine Überlappung, chronologische Reihenfolge), aber sie wird jetzt
durch **Mitschieben der berührten Kante** hergestellt statt durch Ablehnen der Eingabe.

## Was sich ändert

### Server (`app/routers/segments.py`)

- Neues Feld im PATCH-Body: `shrink_neighbors: bool = false`.
  - **false (Standard):** Verhalten wie bisher — strenge Prüfung, 400 bei Überlappung. Skripte und
    alte Clients bleiben unverändert.
  - **true (Timing-Tab):** `_apply_shrink()` schiebt die berührte Kante mit:
    - Start links über den Vorgänger → `Vorgänger.end := neuer_start`
    - Ende rechts über den Nachfolger → `Nachfolger.start := neues_ende`
    - Jeder Nachbar behält `MIN_WORD_DURATION_S` (20 ms). Reicht der Platz nicht, wird die gezogene
      Kante begrenzt — **kein 400** (das Wort selbst behält seine 20 ms).
    - Nur die **berührte** Kante wandert; wird das aktive Wort kleiner, wächst kein Nachbar nach.
    - Ein mitgeschobener Nachbar bekommt `override=true` (er ist damit wie eine manuelle Korrektur
      gegen Re-Align geschützt).
    - **Segment-Grenzen bleiben unangetastet** (Change 155).
  - Nachbarn werden segmentübergreifend im Wort-Flow gesucht (wie die bisherige Monotonie-Prüfung).
  - Verschiebung wird geloggt (`log.info`, Change 207-Muster: keine stillen 400er mehr).

### Frontend

- **`src/timingNeighbors.ts` (neu, pur):** `neighborWords()` (Nachbarn im Wort-Flow, segment-
  übergreifend) und `shrinkNeighborEdges()` (identische Rechnung wie der Server, für die
  Live-Anzeige).
- **`WaveformPlayer`:** zwei zusätzliche, blass-graue Range-Marker für n-1/n+1 mit sichtbaren
  Handles. Klick, Anfassen (`pointerdown`) oder Ziehen eines Nachbar-Markers ruft
  `onTimingSelectWord(segIdx, wordIdx)` → dieses Wort wird aktiv. Die Regionen folgen den Werten aus
  den Props (`setOptions`), damit sie beim Ziehen live mitschrumpfen.
- **`RecordingCard`:**
  - Nachbarn werden beim Wortklick ermittelt und als State gehalten (Ausgangsstand in einer Ref).
  - **Zieh-Grenzen** des aktiven Wortes: statt Innenkante des Nachbarn jetzt dessen Außenrand
    (`prev.start + 20 ms` bzw. `next.end − 20 ms`) — bis dorthin darf gezogen werden, weil der
    Nachbar mitschrumpft.
  - `handleTimingChange` rechnet die Nachbarn live aus dem **Ausgangsstand** (Zug zurück setzt den
    alten Rand wieder her).
  - `handleTimingCommit` schickt **einen** PATCH mit `shrink_neighbors: true` und übernimmt die
    Nachbarn + Zieh-Grenzen aus der Server-Antwort (der Server ist die Wahrheit). Bei Fehler:
    Rollback der Nachbarn + sichtbare Meldung (bestehendes Muster).
- **Nebenfund (mitbehoben):** Die Markierung des aktiven Wortes wurde nur einmal angelegt und blieb
  beim Wechsel des Wortes an der alten Stelle stehen — sie wandert jetzt mit (`setOptions` beim
  Wechsel der Wort-Kennung; während eines Drags bleibt sie unangetastet).

## Welche Geste lässt was schrumpfen

| Geste | Klemmung (Frontend) | Wirkung |
| --- | --- | --- |
| Startmarker ziehen | `clampWordTiming`, untere Grenze `Vorgänger.start + 20 ms` | Vorgänger schrumpft (bis 20 ms), Nachfolger unberührt |
| Endmarker ziehen | `clampWordTiming`, obere Grenze `Nachfolger.end − 20 ms` | Nachfolger schrumpft, Vorgänger unberührt |
| Ganze Markierung ziehen | `clampMoveWordTiming` mit denselben Grenzen | nach links: Vorgänger; nach rechts: Nachfolger; beide nur, wenn das Wort länger ist als die Lücken zu beiden |

Der Server unterscheidet die Gesten nicht — er sieht nur „neuer Start / neues Ende" und prüft
Vorgänger und Nachfolger unabhängig (`_apply_shrink`). Deshalb ist jede Geste abgedeckt, die
irgendeine Kante über einen Nachbarn schiebt.

## Nachweis (Tests)

- `webapp/tests/test_word_timing.py` (Server, 9 neue Tests): Start-Kante → Vorgänger schrumpft,
  End-Kante → Nachfolger schrumpft (segmentübergreifend), **Körper-Zug nach links** (nur Vorgänger),
  **Körper-Zug nach rechts** (nur Nachfolger), **beide Kanten in einem Request** (beide Nachbarn),
  Mindestdauer statt 400, nicht berührte Kante wächst nicht, `shrink_neighbors` fehlt → weiter 400,
  letztes Wort ohne Nachbarn. Datei **28 Tests grün.**
- `frontend/src/timingNeighbors.test.ts` (12 Tests): `neighborWords` (Mitte, Segmentanfang, Ränder,
  defensiv) und `shrinkNeighborEdges` (Start-Kante, End-Kante, Körper-Zug links/rechts, beide Kanten,
  Mindestdauer, kein Nachwachsen, ohne Nachbarn).
- `frontend/src/components/RecordingCard.timingWord.test.tsx` (5 Tests, echter SegmentList,
  nachgebildeter Player mit Prop-Mitschnitt): Wortklick spielt nur die Wortspanne (Change 208),
  Nachbar-Marker für n-1/n+1 vorhanden, Ziehen schrumpft live — inklusive **Körper-Zug** —, Speichern
  schickt `shrink_neighbors: true` und übernimmt die Server-Antwort, Klick auf einen Nachbarn macht
  ihn aktiv. Zusammen mit der Logik-Datei **17 Tests grün**.
- `tsc --noEmit` sauber; volle Frontend-Suite **489 Tests** grün.

## Offen

- Gegenprobe am Gerät (Ziehen über den Nachbarn, Marker-Anfassen).
- Bewusst nicht gemacht: Nachbarn bis auf 0 s schrumpfen lassen (20-ms-Untergrenze bleibt), und
  Segment-Grenzen mitziehen (Change 155 verbietet es).
