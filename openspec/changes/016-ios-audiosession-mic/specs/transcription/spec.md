## ADDED Requirements

### Requirement: iOS-Mikrofon-Aufnahme (AudioSession-Härtung)

- **Ablauf:** Der Record-Tab (`UploadZone`) setzt vor JEDEM Mikrofon-Zugriff
  die Audio-Session explizit auf `play-and-record`:
  `navigator.audioSession.type = "play-and-record"` (nur WebKit — andere
  Browser haben kein `navigator.audioSession` und ignorieren das still).
  Aufrufstellen: `prewarmMic()` vor `getUserMedia` und `startRecording()`
  vor `record.startRecording(...)`.
- **Warum:** WaveSurfer 7 setzt bei jedem WebAudio-Player-Start
  (`webaudio.js::setWebAudioSessionPlayback`) `audioSession.type =
  "playback"`. WebKit verbietet dann `getUserMedia` mit `InvalidStateError`
  „AudioSession category is not compatible with audio capture" (Audio-
  Session-Spec §6.3: nur `play-and-record`/`auto` erlauben den Mikrofon-
  Track). Die Recording-Liste rendert WaveSurfer-Player (WaveformPlayer,
  `backend: "WebAudio"`) → ohne Härtung ist die Aufnahme auf iOS
  reproduzierbar kaputt.
- **Retry (Sicherheitsnetz):** Schlägt `record.startRecording()` mit der
  AudioSession-Meldung fehl, setzt die App die Session erneut und versucht
  EINMAL (`1`), die Aufnahme zu starten — deckt den Fall ab, dass die
  Session zwischen Pre-Warm und Start durch weitere Player-Mounts wieder
  auf `playback` gekippt ist. Andere Fehler (Permission `NotAllowedError`,
  kein Gerät) lösen KEINEN Retry aus — sie sind User-Entscheid bzw.
  Hardware-Problem, kein Session-Problem.
- **Sichtbarkeit:** `prewarmMic()` schluckt Fehler nicht mehr still —
  es loggt die Ursache (`console.warn`) und der Record-Start zeigt die
  bestehende Toast-Meldung mit dem echten Fehlergrund. „Mikro verweigert"
  und „AudioSession-Konflikt" bleiben unterscheidbar.
- **Architektur:** `webapp/frontend/src/components/UploadZone.tsx`
  (Helfer `ensureAudioSessionForRecording()`, Einbau in Pre-Warm +
  Record-Start). Kein Vendor-Patch an `wavesurfer.js` (bricht bei
  npm-Update; Player brauchen `playback` für Wiedergabe).

#### Scenario: Aufnahme mit vorhandener Recording-Liste (iOS)

- **Akteure:** iOS-Safari-User, Record-Tab, Liste zeigt fertige Aufnahmen
  (WaveSurfer-Player gemountet → Session steht auf `playback`).
- **Eingaben:** Record-Button antippen.
- **Ergebnis:** `ensureAudioSessionForRecording()` setzt die Session vor
  `getUserMedia` auf `play-and-record`; die Aufnahme startet ohne
  „AudioSession category is not compatible with audio capture".

#### Scenario: Session driftet zwischen Pre-Warm und Start

- **Akteure:** iOS-Safari-User; nach dem Pre-Warm mounten weitere
  WaveSurfer-Player (Scrollen) und setzen die Session auf `playback`.
- **Eingaben:** Record-Button antippen.
- **Ergebnis:** Erster Start wirft AudioSession-Fehler → App setzt die
  Session erneut und startet den zweiten Versuch → Aufnahme läuft.
  Genau 2 `startRecording`-Aufrufe, kein Endlos-Retry.

#### Scenario: User verweigert die Mikrofon-Permission

- **Akteure:** iOS-Safari-User, Permission abgelehnt.
- **Eingaben:** Record-Button antippen.
- **Ergebnis:** `NotAllowedError` → KEIN Retry; Toast zeigt den
  Permission-Grund; die App wartet auf eine erneute Freigabe in den
  Browser-Einstellungen.
