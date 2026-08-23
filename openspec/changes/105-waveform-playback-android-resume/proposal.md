# Change 105 — Waveform-Playback auf Android: AudioContext-Resume + robuste Container-Init

## Status
- **Stand:** 2026-08-23
- **Phase:** Umsetzung

## Problem
Nach Deploy von 102–104 (CI 4391–4393) meldet der User weiterhin (Android, mobil):
1. Loading-Bar fertig, Play-Button drückbar, aber **kein Ton** (Player flackert kurz zum Pause-Symbol).
2. Klick in die Waveform: **kein Ton**.
3. Klick an eine Dialog-Stelle: **Transkript scrollt nicht zur Stelle**.

## Analyse / Root Cause
- **WS7 7.12 ruft `audioContext.resume()` nie auf.** `new AudioContext()` startet
  auf Chrome/Android laut Autoplay-Policy im Zustand `suspended` — `bufferNode.start()`
  läuft dann **stumm**, obwohl `isPlaying()`/Pause-Symbol korrekt sind. Das erklärt
  exakt „Play drückbar, kein Ton, Flicker zum Pause-Symbol" (Play-State wird gesetzt,
  Audio-Graph bleibt suspended). Lokal (headless) ist der Context nicht suspended —
  deshalb lief der Playback-Cursor im Test, der Ton-Fehler ist nur auf Geräten mit
  Autoplay-Policy reproduzierbar.
- **Waveform-Click-Handler rief `ws.setTime(t)` vor `setCurrentTime`/`onTimeUpdate`**
  — wirft `setTime` (WS7 ohne spielbares Audio), bricht der Handler ab → kein Scroll.
- **Container bis `ready` `display:none`** → WS7 misst beim `create` eine Breite von 0
  (bekannt aus Change 083/100, Initial-Zoom-Kommentar) — Initialisierung mit 0-Breite.
- Nebenbei geklärt: WS7 rendert die Wave in einem **Shadow-Root** — die Waveform war
  nie „weg", frühere „0 Canvas"-Befunde waren Messfehler des Test-Skripts.

## Lösung
1. **`ensureAudioContext(ws)`**: vor jedem `ws.play()` wird `getMediaElement().audioContext.resume()`
   aufgerufen, wenn der Context `suspended` ist (im Klick-Kontext = erlaubte User-Geste).
   Alle 4 Play-Pfade: `play`, `playPause`, Waveform-Container-Klick, `seekTo`.
2. **Klick-Handler**: `setTime` in try/catch; `setCurrentTime`/`onTimeUpdate` laufen
   **immer** → Transkript-Scroll funktioniert auch bei nicht abspielbarem WS7.
3. **Container**: `visibility:hidden` statt `display:none` bis `ready` — Layout-Breite
   bleibt messbar, WS7 initialisiert mit korrekter Breite.

## Verifikation (lokal, Mobile-Emulation Pixel 7, Login-Cookie User 1)
- Play: Cursor läuft (6,8 % → 18,9 %), Button ⏸ — Wiedergabe-Pfad aktiv.
- Seek-Klick bei 60 %: Cursor springt auf 64 %.
- Klick markiert das aktive Segment (`karaoke-active`), keine JS-Fehler.
- `resume`-Guard: lokal kein suspendierter Context (0 Resume-Aufrufe — Guard greift
  nur bei `suspended`), tsc 0, Frontend-Suite grün.

## Ausblick
- Live-Verifikation auf Android nach Deploy (User).
- WaveSurfer-Pinning (7.12.11 ohne `^`) steht weiter zur Entscheidung an.
