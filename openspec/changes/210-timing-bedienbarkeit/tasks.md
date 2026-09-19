# Aufgaben — Change 210

- [x] Befunde aufgenommen: Klick nur in den ersten Zeilen, Marker zu blass, gegriffene Kante markieren,
      Process-Knopf kehrt nach dem Zurückwechseln nicht wieder.
- [x] Daten geprüft: alle 96 fertigen Aufnahmen durchgehend mit Wort-Zeitstempeln (0 Lücken; längste
      Aufnahme 1544 Segmente / 41 546 Wörter).
- [x] Reproduktion versucht und dokumentiert: kein Prod-Login im Tresor; virtualisierter jsdom-Pfad
      nicht ehrlich abbildbar → Testversuch entfernt statt wackliger Test.
- [x] `SegmentList`: neuer Modus `tall` → `max-h-[62vh]` im Timing-Tab.
- [x] `TimingEditor`: `tall` + `listFillHeight` (Vollbild), Farblegende in der Kopfzeile
      (`data-testid="timing-legend"`).
- [x] `RecordingCard`: `handleTimingWordSelect` meldet ein Wort ohne eigene Zeit sichtbar
      (`timing_word_no_time`) statt stumm zurückzukehren; Start-Zeile bleibt immer gerendert,
      Knopf im Timing-Tab `disabled` + `data-timing-disabled` + Titel.
- [x] `WaveformPlayer`: aktives Wort kräftiger + 2 px Rahmen, Nachbarn bernstein/gestrichelt mit
      Beschriftung „davor"/„danach"; gegriffene Kante (`ps-edge-start`/`ps-edge-end`) hervorgehoben,
      beim Loslassen gelöst; Waveform scrollt beim Wortwechsel ins Sichtfeld.
- [x] `index.css`: Regeln für Markierungen, Label und hervorgehobene Kante (Handle-Klassen gegen
      wavesurfer.js 7.12.11 geprüft).
- [x] Locale de/en/pt: `timing_neighbor_prev|next`, `timing_legend_active|neighbor`,
      `timing_word_no_time`, `start_disabled_timing`.
- [x] Tests: `TimingEditor.height.test.tsx` (3 neu), `RecordingCard.test.tsx` auf die neue
      Knopf-Semantik umgestellt (sichtbar + deaktiviert + nach dem Zurückwechseln bedienbar).
- [x] `tsc --noEmit` sauber, volle Frontend-Suite grün.
- [ ] CI, Deploy, Gegenprobe am Gerät (Klick weit unten in einer langen Transkription).
