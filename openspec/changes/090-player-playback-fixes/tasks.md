# Tasks — Change 090: Player-Playback-Fixes

## Umsetzung
- [x] OpenSpec-Change dokumentiert (proposal.md)
- [x] Bug 1: canPlay-Polling auf echten Playback-Puffer
      (WebAudio: mediaElement.buffer; MediaElement: readyState >= 3)
      statt ws.getDecodedData() — WS 7.12+ Peaks-createBuffer-Regression
- [x] Bug 2: Initial-Zoom in useEffect([ready, error]) verschoben
      (Container ist im ready-Handler noch display:none → clientWidth 0 →
      fitPps=MIN_PPS → Welle 285 px + Seek um Faktor 3,44 verzerrt)
- [x] Bug 2: Klick-Seek nutzt im Fit-Modus (zoomIdx 0) die LIVE-Container-
      Breite (fitPps) statt des fixen ppsRef

## Verifikation
- [x] 290 Frontend-Tests grün + tsc sauber
- [x] Playwright (echte 45-MB-Preview, 20-s-Delay):
      Button disabled bis Download+Decode (t=45 s statt t≈5 s)
- [x] Klick bei 9/95 der Breite → „8:58 / 95:10", playing: true (statt 31 min)

## Abschluss
- [ ] Commit + Push + CI-Check

## Design-Notizen
- getDecodedData() ist seit WS 7.12.11 im Peaks-Pfad SOFORT gesetzt
  (createBuffer aus Server-Peaks) — nie wieder als „Audio geladen"-
  Indikator verwenden. Echte Indikatoren: mediaElement.buffer (WebAudio)
  bzw. readyState >= 3 (MediaElement) bzw. das „canplay"-Event.
- Der Waveform-Container ist bis `ready` display:none — clientWidth ist im
  ready-Handler 0; Layout-abhängige Berechnungen gehören in useEffect nach
  dem Commit.
