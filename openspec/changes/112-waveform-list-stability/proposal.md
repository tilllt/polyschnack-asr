# Change 112 — Waveform-Listenstabilität (Android-Chrome: Blinken + Tab-Crash)

## Proposal

### Problem (Produktions-Befund, 23.08., User tilllt)

Auf der **Startseite (Liste)** mit Android-Chrome:
- Die **Wellenform-Kurve verschwindet und erscheint periodisch** (Sekundentakt).
- Der **Tab stürzt komplett ab** („Aw, Snap" / OOM).

Diagnose (lokale Reproduktion, 23.08.): Das Frontend ist auf Desktop-Chromium
stabil (3 Konfigurationen × 120 s: 0 Canvas-Re-Builds, 0 Fehler, Memory
konstant) — auch mit der echten Produktionsdatei (95 min, 136 MB M4A,
16-MB-Preview, 2000 Peaks, 2508 Wörter). Die Ursachen sind Android-spezifisch
und betreffen zwei getrennte Mechanismen:

1. **Blinken = Rendering:** Die Kurve wird aus den `waveform_peaks` (2000
   Punkte) gezeichnet — **kein Audio-Decode nötig**. Der 1-s-Tick
   (`RecordingCard`, setInterval Z. 212) re-rendert alle Karten sekündlich.
   Unter Android-Chrome (schwächere Canvas/GPU-Pipeline) erzeugt der
   Re-Render sichtbare Canvas-Leerphasen → Kurve „verschwindet/erscheint".
   Desktop-Chromium zeichnet den Re-Render in <16 ms (unsichtbar).
   → Fix: Player-Instanz stabilisieren (kein Re-Mount/Re-Init durch den Tick).

2. **Tab-Crash = Memory-OOM:** Die Karten **preloaden und dekodieren ihr
   Audio schon beim Anzeigen** (nicht erst beim Play). Die Preview ist
   16 MB MP3 (95 min) → WebAudio dekodiert **~180 MB PCM pro Karte** im Tab.
   Android-Chrome-Renderer: Heap-Limit typisch ~512 MB–1 GB. Mehrere Karten
   + 95-min-Datei → OOM → kompletter Tab-Absturz.
   → Fix: Audio erst beim Play-Klick laden (WaveSurfer lazy) — die Kurve
   bleibt sofort sichtbar (Peaks), der Decode passiert nur bei Interaktion.

### Ziel

- Karten in der Liste zeichnen die Wellenform **sofort aus den Peaks** und
  laden das Audio **erst beim Play-Klick** (kein Preload/Decode beim Render).
- Der WaveformPlayer wird durch Re-Renders (1-s-Tick, Status-Polls) **nicht
  neu initialisiert** — gleiche Canvas-Instanz, keine Leerphasen.
- Keine Verhaltensänderung in der Detail-Ansicht (`/r/<uid>`): dort darf der
  Player weiterhin das Audio laden (Nutzer erwartet sofortiges Playback).

### Abgrenzung

- Kein Eingriff in Change 108 (GUI/Timeline-Refactor, Review bei Ruben
  ausstehend) — 112 ist ein Sofort-Fix auf dem bestehenden Player.
- Kein Backend-Change (Preview-Format 32 kbps bleibt optionaler Punkt 3,
  separat zu bewerten).
- Keine Änderung am Playback-Verhalten nach dem Play-Klick.

## Kontext

- `webapp/frontend/src/components/RecordingCard.tsx`:
  - Z. 212: `setInterval` 1-s-Tick (Status/ETA-Refresh)
  - Z. 352: `loadWaveform = !collapsed && (nearViewport || expandedOnce)`
  - Z. 1112: `<WaveformPlayer … />` (Aufrufstelle, ohne stabilen Key)
- `webapp/frontend/src/components/WaveformPlayer.tsx`: WS7-Init mit
  `url` (Audio-URL) — lädt/decodiert beim Mount (Preload-Verhalten).
- `webapp/frontend/src/lib/audio.ts` o. ä.: `resolveAudioUrl` /
  `audio_preview_url`-Auswahl (Preview bevorzugt, Fallback volle Datei).
- Befund-Details: siehe 106-tasks.md „BUGFIX (23.08.)" (separate_backend)
  — unabhängiges Thema, gleicher Tag.
