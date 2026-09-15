# Change 195 — Waveform-Klick: Exklusivität vor Playback-Start

**Status:** Proposal

## Warum

Der Play-Button stoppt zuverlässig einen bereits aktiven Player, bevor der neue startet. Ein Klick auf die Waveform (Seek + Play) tut das nicht — beide Player laufen kurz parallel oder der zweite startet, ohne den ersten zu stoppen.

Root Cause: Der `onContainerClick`-Handler ruft `ws.play()` und verlässt sich darauf, dass WS7 das `"play"`-Event synchron feuert — und erst in diesem Event-Handler wird `claimExclusivePlayback()` aufgerufen. Wenn die Event-Reihenfolge nicht strikt synchron ist oder sich das WS7-intern ändert, startet Audio bereits vor der Exklusivitäts-Prüfung.

Zusätzlich pausiert mount-time `claimExclusivePlayback` (Zeile 923) einen spielenden Player, sobald ein neuer WaveformPlayer im DOM erscheint (z. B. Virtual-Scroll). Das maskiert den Bug in vielen Szenarien, ist aber selbst ein Problem: ein bloßes Mounten sollte nie das Playback eines anderen Players beenden.

## Was sich ändert (Verhaltens-Delta)

### Expliziter claim vor ws.play() im Container-Klick

`onContainerClick` ruft `claimExclusivePlayback(me)` **vor** `ws.play()` auf — direkt, nicht über den WS7-Event-Umweg. Dadurch stoppt der vorherige Player garantiert, bevor der neue startet, unabhängig von WS7s Event-Timing.

### Mount-Zeile: claim → register (kein Pause)

Zeile 923 (`claimExclusivePlayback(me)`) wird ersetzt durch eine neue Funktion `registerActivePlayer(me)`, die nur `activePlayer = me` setzt, ohne den Vorgänger zu pausieren. Pausieren soll nur passieren, wenn der User bewusst ein Playback startet (Play-Button oder Waveform-Klick), nicht bei reinem DOM-Mount.

### Vereinfachung der Event-Handler

Der `ws.on("play")`-Handler behält `claimExclusivePlayback(me)` — als doppelte Absicherung für andere Play-Pfade (z. B. `toggleActivePlayback`, imperative `seekTo`, externe API-Aufrufe). Der Klick-Handler macht den claim bereits explizit, der Event-Handler fängt die restlichen Pfade ab.

## Was NICHT geändert wird (Scope)

- Keine Änderung am `releaseExclusivePlayback` oder `toggleActivePlayback`
- Keine Änderung am Play-Button-Pfad (der funktioniert bereits korrekt)
- Keine neuen Tests für bereits abgedeckte Fälle

## Specs-Delta

`MODIFIED` **captions-view**: Das Verhalten „Klick auf Waveform → Seek + Play" wird um die explizite Exklusivitäts-Prüfung ergänzt.

## Risiken / Trade-offs

| Risiko | Maßnahme |
|--------|----------|
| `registerActivePlayer(me)` vergisst den Player bei schnellem Mount/Unmount | Der bestehende `releaseExclusivePlayback` im Cleanup bleibt unverändert |
| Doppelter claim (im Handler + im Event) pausiert fälschlich denselben Player | `claimExclusivePlayback` hat `activePlayer !== me` Guard — Self-Pause ist unmöglich |
| `toggleActivePlayback` (Space) hat kein Ziel mehr, wenn nie ein Player per Klick/Button gestartet wurde | `registerActivePlayer` setzt `activePlayer` wie bisher beim Mount — Space hat weiter ein Ziel |