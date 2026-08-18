# Change 016 — Design

## Kontext

iOS Safari blockiert `getUserMedia` mit „AudioSession category is not
compatible with audio capture", sobald `navigator.audioSession.type` auf
`playback` steht. WaveSurfer 7 setzt das bei jedem WebAudio-Player-Start
(`webaudio.js::setWebAudioSessionPlayback`), und die Recording-Liste
rendert solche Player (WaveformPlayer mit `backend: "WebAudio"`).

## Entscheidungen

### 1. App-seitiger Helfer statt Vendor-Patch

- **Ansatz:** `ensureAudioSessionForRecording()` setzt
  `navigator.audioSession.type = "play-and-record"` direkt vor jedem
  `getUserMedia`-Aufruf (Pre-Warm UND Record-Start).
- **Warum kein Vendor-Patch an wavesurfer.js:** (a) bricht bei jedem
  `npm install`/Update (node_modules, kein patches/-Mechanismus im Repo);
  (b) WaveSurfer-Player brauchen `playback` für normales Abspielen —
  die Session soll nur WIE AUFNAHME anliegen, nicht generell; (c) der
  Eingriff an der richtigen Stelle (Mikrofon-Zugriff) ist wirkungsgleich
  und wartbar.
- **Warum `play-and-record` und nicht `auto`:** `play-and-record` ist der
  von der Spec explizit für Aufnahme+Wiedergabe vorgesehene Typ; `auto`
  überlässt die Wahl dem Browser. Beide sind laut Spec §6.3 zulässig,
  `play-and-record` ist deterministisch.

### 2. Retry bei AudioSession-Fehler (1 Versuch)

- Der Fehler kann AUCH zwischen Pre-Warm und Record-Start entstehen
  (User scrollt, weitere WaveSurfer-Player mounten → Session wechselt
  zurück auf `playback`). Deshalb reicht der Pre-Warm-Fix allein nicht.
- Ablauf: `startRecording()` → `record.startRecording()` → catch:
  wenn `message` „AudioSession category is not compatible" enthält →
  Session setzen → EINMAL erneut versuchen. Kein Endlos-Retry
  (Permission-Ablehnungen dürfen nicht maskiert werden).
- Zusätzlich schützt der Helfer vor `record.startRecording(...)`, sodass
  der Retry-Pfad praktisch nie greift — aber als Sicherheitsnetz da ist.

### 3. Pre-Warm-Fehler sichtbar machen

- `prewarmMic()` schluckt Fehler bisher komplett (catch {}). Neu:
  `console.warn("mic prewarm failed:", reason)` — und der Record-Start
  zeigt die bestehende Toast-Meldung mit dem echten Grund. Damit ist
  „Mikro verweigert" von „AudioSession-Konflikt" unterscheidbar (wichtig
  für künftige Diagnose, stille Fehler inakzeptabel).

## Alternativen geprüft

- **Vendor-Patch webaudio.js:** verworfen (s. o.).
- **`backend: "MediaElement"` in WaveformPlayer:** verworfen — Memory:
  WS7-7.8+-Regression (stiller Player) wurde genau durch WebAudio-Backend
  behoben (`c26ce58`); ein Zurückwechseln würde Playback brechen.
- **AudioContext vor getUserMedia schließen:** nicht nötig und riskant —
  der Fehler kommt von `audioSession.type`, nicht vom AudioContext selbst.
- **`audioSession.type` global auf `play-and-record` fixieren (App-Init):**
  verworfen — WaveSurfer setzt es beim Player-Start eh zurück, und
  dauerhaft `play-and-record` könnte die Wiedergabe-Lautstärke auf iOS
  beeinflussen. Der punktuelle Set-vor-Zugriff ist minimal-invasiv.

## Offene Fragen

- Soll der Retry auch `NotAllowedError` (Permission) abfangen? → Nein:
  Permission-Ablehnung ist ein User-Entscheid, kein Session-Problem;
  Retry würde nur verwirren. Nur der AudioSession-spezifische Fehler
  löst den Retry aus.
