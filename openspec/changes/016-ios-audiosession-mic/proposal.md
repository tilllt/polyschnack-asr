# Change Proposal 016 — iOS-Mikrofon-Aufnahme: AudioSession-Konflikt mit WaveSurfer

**Status:** Proposed

## Why

User-Befund (2026-08-18, iOS Safari, per.cia-spandau.de): Der Record-Button
zeigt sofort beim Antippen:

```
Mic access denied: Error accessing the microphone:
AudioSession category is not compatible with audio capture
```

Betroffen: **iOS Safari/WebKit nur** (Android/Chrome funktioniert). Der
Fehler tritt reproduzierbar auf, sobald auf der Seite eine fertige
Aufnahme (Recording-Karte mit Waveform) vorhanden ist — also immer dann,
wenn ein WaveSurfer-Player mit WebAudio-Backend erstellt wurde.

## Root Cause (durch Code + Web-Standard belegt)

1. **WaveSurfer setzt die AudioSession auf `playback`.** In
   `wavesurfer.js/dist/webaudio.js` (Z. 11–21) ruft der WebAudio-Player-
   Konstruktor `setWebAudioSessionPlayback()` auf:
   ```js
   function setWebAudioSessionPlayback() {
     const navigator = globalThis.navigator;
     if (!(navigator?.audioSession)) return;
     try { navigator.audioSession.type = 'playback'; } catch (e) { … }
   }
   ```
   `WaveformPlayer.tsx` erstellt Player mit `backend: "WebAudio"` (Z. 162)
   → schon beim Rendern der Recording-Liste steht
   `navigator.audioSession.type = "playback"`.

2. **WebKit verbietet Mikrofon bei `playback`.** Die Audio-Session-Spec
   (W3C, [§6.3 Microphone MediaStreamTrack](https://www.w3.org/TR/audio-session/#microphone-track-source)):
   *„If audioSession.[[type]] is not `play-and-record` or `auto`, end
   track."* WebKit wirft deshalb bei `getUserMedia` genau die gemeldete
   Meldung. Bestätigt im [W3C-Issue #46](https://github.com/w3c/audio-session/issues/46)
   (gleiche Meldung, gleiche Ursache bei descript.com).

3. **Fehlerpfad in der App:** `UploadZone.startRecording()` →
   `record.startRecording()` (wavesurfer-record.js) → `startMic()` →
   `navigator.mediaDevices.getUserMedia()` → wirft → Toast
   „Mic access denied: …". Auch `prewarmMic()` (getUserMedia beim
   Betreten des Record-Tabs) scheitert still — der Fehler wird dort
   geschluckt und erst beim Start sichtbar.

## What

1. **AudioSession vor jedem Mikrofon-Zugriff auf `play-and-record` setzen:**
   Neuer Helfer `ensureAudioSessionForRecording()` in `UploadZone.tsx`
   (oder eigenes Modul `audioSession.ts`):
   ```ts
   function ensureAudioSessionForRecording() {
     const s = (navigator as unknown as { audioSession?: { type: string } })
       .audioSession;
     if (s && s.type !== "play-and-record") s.type = "play-and-record";
   }
   ```
   Aufruf **vor** `getUserMedia` in `prewarmMic()` UND vor
   `record.startRecording()` in `startRecording()` (deckt beide Pfade ab:
   Pre-Warm und Direkt-Start ohne erfolgreichen Pre-Warm).

2. **Robuster Retry im Fehlerfall:** Fängt `startMic`/`getUserMedia` den
   `InvalidStateError` mit „AudioSession category is not compatible with
   audio capture" ab (oder jede Ablehnung), setzt die AudioSession explizit
   auf `play-and-record` und versucht **einmal** erneut. Damit ist die
   Aufnahme auch dann möglich, wenn ein anderer Code (WaveSurfer-Player
   beim Scrollen/Laden) die Session zwischen Pre-Warm und Start wieder auf
   `playback` gestellt hat.

3. **Kein stiller Fehler im Pre-Warm:** `prewarmMic()` loggt die Ablehnung
   (console.warn) und zeigt beim Record-Start eine klare Meldung, falls das
   Mikro nicht verfügbar ist (bestehender Toast-Pfad bleibt; zusätzlich
   wird der Fehlergrund differenziert: Permission vs. AudioSession vs. kein
   Gerät).

## Changes

- `webapp/frontend/src/components/UploadZone.tsx`:
  - Helfer `ensureAudioSessionForRecording()` (nur WebKit: `audioSession`
    existiert dort; andere Browser ignorieren das still).
  - `prewarmMic()`: Helfer vor `getUserMedia`; Fehler nicht mehr komplett
    schlucken (console.warn mit Grund).
  - `startRecording()`: Helfer vor `record.startRecording(...)`;
    Retry-Logik bei AudioSession-Fehler (1 Versuch nach explizitem Setzen).
- Kein Vendor-Patch an `wavesurfer.js` nötig (die Session wird app-seitig
  pro Mikrofon-Zugriff gesetzt; ein Patch würde bei jedem npm-Update
  brechen und den Player-Start nicht verhindern — Player brauchen
  `playback` für normale Wiedergabe).

## Downgrade

- Helfer entfernen → Verhalten wie vorher (iOS-Aufnahme kaputt, Rest
  unverändert). Kein Datenverlust, keine Schema-Änderung.
- Retry-Logik entfernen → Pre-Warm-Pfad bleibt funktionsfähig, Direkt-
  Start nach Session-Drift kann wieder fehlschlagen.

## Specs-Delta

- MODIFIED: `specs/transcription/spec.md` (Req 8 neu: iOS-Mikrofon-
  Aufnahme — AudioSession-Härtung + Retry)
