# Change 090 — Player-Playback-Fixes (Play-Button-Regression + Seek-Verzerrung)

**Status:** in Arbeit → fertig (2026-08-22)
**Befund (User, 22.08.):**
1. „Lange bevor das audio playable ist kann man schon auf Play drücken
   (nichts passiert) — das ist eine Regression, hatten wir schonmal gefixt."
2. „Auf Desktop: click bei ca. 9min in die Timeline: playback startet bei
   31min."

## Root Cause 1 — Play-Button-Regression (WS-Update 7.7.15 → 7.12.11)

Der Abspielbarkeits-Fix (2026-08-18) pollte `ws.getDecodedData()`. WaveSurfer
7.12+ erzeugt `decodedData` im Peaks-Pfad **sofort** aus den Server-Peaks
(`createBuffer(peaks, duration)` in `setOptions`/`loadAudio`) — der echte
Audio-Download + `decodeAudioData` läuft separat im Hintergrund. Dadurch war
`getDecodedData()` nicht mehr der Indikator für geladenes Audio → `canPlay`
sofort `true` → Play-Button aktiv, `ws.play()` auf leerem Buffer = stumm.

**Fix (WaveformPlayer.tsx):** Polling prüft jetzt den echten Playback-Puffer:
- WebAudio: `getMediaElement().buffer` (decodeAudioData-Puffer)
- MediaElement (> 2 h): `readyState >= 3` (wie bisher)

## Root Cause 2 — Seek 9 min → 31 min (Faktor 3,44)

Der Initial-Zoom (Change 083, `doZoom(ws, 0)`) lief im `ready`-Handler,
während der Waveform-Container noch `display:none` war (hidden bis `ready`)
→ `clientWidth = 0` → `fitPps` fiel auf `MIN_PPS` (0,05 px/s) → Welle nur
285 px breit statt Container-Breite (~982 px) und `ppsRef` = 0,05. Der
Klick-Seek rechnete `t = px/pps` → 9 min-Klick wurde 3,44× zu weit
(982/285 = 3,44): 31 min.

**Fix (WaveformPlayer.tsx):**
- Initial-Zoom in einen `useEffect([ready, error])` verschoben — läuft nach
  dem React-Commit, wenn der Container sichtbar ist (clientWidth korrekt).
- Klick-Seek berechnet px/s im Fit-Modus (`zoomIdx === 0`) LIVE aus der
  aktuellen Container-Breite — robust gegen Layout-Änderungen.

## Verifikation (lokal, echte 45-MB-Preview, 20-s-Ladeverzögerung)

- Bug 1: Button **disabled** während des gesamten Ladeblocks (t=5–27 s),
  enabled erst nach Download+Decode (t=45 s). Vorher: enabled bei t≈5 s.
- Bug 2: Klick bei 9/95 der Breite → **„8:58 / 95:10", playing: true**
  (vorher: 31 min).
- 290 Frontend-Tests grün, tsc sauber.
