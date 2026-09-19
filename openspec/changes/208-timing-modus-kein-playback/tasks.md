# Aufgaben — Change 208

- [x] Nutzer-Vorgabe aufgenommen: Timing-Modus — Wortklick ohne Playback, Start-Knopf weg.
- [x] Ursache des Playbacks belegt (nicht der Wortklick, sondern die *Zeilen*-Verdrahtung:
      `onSeekTo` = `setTime` + `play()`; ein Klick neben dem Wort läuft in den Zeilen-Handler).
- [x] Gegenprobe: Test gegen die alte Verdrahtung schlägt fehl (`onSeekPaused` nicht gerufen).
- [x] `TimingEditor`: abspielender Seek nicht mehr durchgereicht → nur pausiertes Seeken.
- [x] `RecordingCard`: Start-Knopf im Timing-Tab ausgeblendet (+ `data-testid`).
- [x] Nachtrag Nutzer: Wortspanne abspielen und am Ende anhalten; Cursor danach am Wortanfang.
      - [x] `WaveformPlayer.playRange(start, end)` (imperative Schnittstelle + Handle-Typ).
      - [x] Abbruch im rAF-Sync-Loop über die reine Funktion `rangeFinished()`.
      - [x] Spanne aufheben bei Play/Stop, Seek und Cursor-Navigation.
      - [x] `handleTimingWordSelect` ruft `playRange(w.start, w.end)`.
- [x] Tests: `rangeFinished` (3), Wortklick-Verdrahtung (1), TimingEditor (2), Start-Knopf (1).
- [x] `tsc --noEmit` sauber, komplette Frontend-Suite grün.
- [ ] CI, Deploy, Gegenprobe am Gerät (Wortklick spielt nur das Wort und hält an).
