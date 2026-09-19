# Status — Change 208

**Stand 19.09.2026:** umgesetzt und getestet. CI und Deploy stehen aus.

## Belege

- Ursache des ungewollten Playbacks: `WaveformPlayer.seekTo` = `setTime` **+ `play()`**. Die
  Wortliste bekam diesen Seek im Timing-Tab durchgereicht (`TimingEditor` → `SegmentList`), und ein
  Klick neben dem Wort landet im Zeilen-Handler → Wiedergabe der ganzen Aufnahme.
- Gegenprobe: Test „Zeilen-Klick seekt PAUSIERT" gegen die alte Verdrahtung → schlägt fehl
  (der abspielende Seek wurde gerufen, der pausierte nicht).
- Nachtrag des Nutzers (gleiche Sitzung): Wortklick soll **nur die Wortspanne** abspielen und
  anhalten, Marker danach am Wortanfang. Umgesetzt über `WaveformPlayer.playRange(start, end)`
  mit Abbruch im rAF-Sync-Loop (reine Funktion `rangeFinished`), Cursor wird auf `start`
  zurückgestellt.
- Ausblenden des Start-Knopfes: `editorTab !== "timing"` (der Knopf startet Transkription /
  Ausrichtung / Diarisierung, sah aber wie Play aus).

## Tests

- `WaveformPlayer.rangePlay.test.ts` — 3 Fälle für `rangeFinished`.
- `RecordingCard.timingWord.test.tsx` — Wortklick im Timing-Tab → `playRange(1, 2)`, kein
  abspielender Seek (echter SegmentList, nur der Player nachgebildet).
- `TimingEditor.test.tsx` — Wortklick ohne jeden Seek; Zeilen-Klick pausiert, spielt nicht.
- `RecordingCard.test.tsx` — Start-Knopf im Timing-Tab weg, im Transkriptions-Tab da.
- `tsc --noEmit` ohne Befund; volle Frontend-Suite 472 Tests grün (38 Dateien).

## Gegenprobe am Gerät (offen)

- Timing-Tab: Klick auf ein Wort → nur dieses Wort ist zu hören, danach Ruhe; Play läuft ab dem
  Wort weiter; der Start-Knopf ist dort nicht sichtbar.
