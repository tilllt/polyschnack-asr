# Change 208 — Timing-Modus: kein Playback beim Klick, kein Start-Knopf

## Warum (Nutzer-Vorgabe 19.09.2026)

> „im Gegensatz zum transkriptionsmodus soll ein Klick auf ein Wort im Timing-Modus nicht das
> Playback starten sondern nur an das Wort Heranzoomen und die Markierung zeigen. Im Timing-Modus
> soll der ‚process' button entweder ausgeblendet werden oder nicht klickbar sein, da man ihn
> leicht mit Play verwechselt."

Beim Prüfen: Der **Wort**-Klick im Timing-Modus tut bereits das Richtige (er lädt das Wort, der
Player zoomt auf ~30 % und legt die Markierung an). Das Playback kam vom **Zeilen**-Klick: die
Wortliste bekam im Timing-Modus denselben `onSeekTo` wie die Transkription — und der spielt ab
(`WaveformPlayer.seekTo` = `setTime` + `play()`). Ein Klick, der ein paar Pixel neben dem Wort
landet, läuft in den Zeilen-Handler und startet damit die Wiedergabe. Genau das war zu sehen.

Gegenprobe (Test gegen die alte Verdrahtung): Der Zeilen-Klick rief `onSeekTo` (spielt ab) und
nicht `onSeekPaused` — der neue Test schlägt dort fehl. ✓

## Was sich ändert

1. **Timing-Tab spielt nie mehr die ganze Aufnahme.** `TimingEditor` reicht `onSeekTo` (spielt ab)
   **nicht** mehr an die Wortliste durch. Jede Navigation (Wort- wie Zeilen-Klick) seekt
   **pausiert**; fehlt der pausierte Seek ganz, bleibt der Klick ohne Seek. Der
   Transkriptions-Tab behält sein Verhalten (Klick spielt ab) — wie gewünscht.
2. **Wort-Klick spielt genau die Wortspanne** (Nachtrag des Nutzers, gleiche Sitzung):
   „Der Klick auf das Wort soll auch nur die Wort Range abspielen und dann wieder stoppen. Klick
   auf das Wort setzt auch den Playback Marker auf den Start des Wortes, das heißt wenn man danach
   den Play Button drückt spielt die Aufnahme ab dem Wort."
   - Neue Player-Methode `playRange(start, end)`: setzt den Cursor auf den Wortanfang, spielt ab
     und **hält am Ende an**; danach steht der Cursor wieder am **Wortanfang**, damit ein
     anschließender Play-Druck ab dem Wort weiterläuft.
   - Die Abbruch-Prüfung sitzt im bestehenden rAF-Sync-Loop (kein Timer, kein Drift) und ist als
     reine Funktion `rangeFinished()` herausgezogen — damit prüfbar.
   - Jede manuelle Aktion hebt die Spanne auf: Play/Stop, Seek, Cursor-Navigation.
3. **Start-Knopf im Timing-Tab ausgeblendet.** Der Knopf („Process", startet Transkription /
   Ausrichtung / Diarisierung) sitzt direkt beim Player und wurde mit Play verwechselt. Er wird
   im Timing-Tab nicht mehr gerendert; die Aktions-Tabs und das Options-Panel bleiben, weil sie
   dort nichts auslösen.
4. `data-testid="process-btn"` am Start-Knopf — macht ihn prüfbar.

## Nachweis (Tests)

- `WaveformPlayer.rangePlay.test.ts`: `rangeFinished()` — läuft weiter vor dem Wortende, hält am
  Ende an, bricht ohne angeforderte Spanne nie ab.
- `RecordingCard.timingWord.test.tsx` (echter SegmentList, nur der Player nachgebildet):
  Wortklick im Timing-Tab ruft `playRange(1, 2)` für „Welt" — und **nicht** den abspielenden
  `seekTo`. Damit ist die Verdrahtung Klick → Wortspanne bewiesen.
- `TimingEditor.test.tsx`:
  - „Wort-Klick startet kein Playback und lädt nur das Wort": `onWordClick` gerufen,
    `onSeekTo` **und** `onSeekPaused` **nicht** (der Wortklick seekt nicht).
  - „Zeilen-Klick seekt PAUSIERT, spielt aber nicht ab": `onSeekPaused` gerufen, `onSeekTo`
    nicht — schlägt gegen die alte Verdrahtung fehl (Gegenprobe durchgeführt).
- `RecordingCard.test.tsx`: Start-Knopf ist im Transkriptions-Tab vorhanden, im Timing-Tab nicht
  und nach dem Zurückwechseln wieder da.
- `tsc --noEmit` sauber, komplette Frontend-Suite grün.

## Abgrenzung

- Der Zeilen-Klick **seekt weiter** (pausiert) — die Ansicht springt also zur Zeile, nur ohne
  Wiedergabe. Kein stiller Verzicht auf Navigation.
- Kein Eingriff in Zoom, Markierung, Drag-Commit (PATCH der Wortzeiten) oder den
  Transkriptions-Tab.
