# Change 049: Streaming-Playback (MediaElement) für sehr lange Aufnahmen

**Status:** proposal
**Datum:** 2026-08-20
**Typ:** Bugfix (Mobile-Playback)

## Problem

User-Befund 2026-08-20: Bei einer 4h52min-Aufnahme (562 MB WAV, Preview
140 MB MP3) startet auf dem Handy kein Playback nach der Transkription.

Ursache: `WaveformPlayer` nutzt hart `backend: "WebAudio"` (Fix c26ce58 —
WS7 7.8+ MediaElement-Default war silent mit Blob-URLs). WebAudio dekodiert
die KOMPLETTE Datei in den RAM:

- 4h52min @ 16 kHz mono s16 = **~560 MB PCM** im Handy-Speicher → OOM/
  Timeout auf Mobile-Geräten
- Zusätzlich lädt der Browser vor dem Decode die ganze 140-MB-Preview —
  bei langsamem Netz dauert das Minuten (User: „sehr langsames Netz")

## Lösung

**Backend dynamisch wählen** (pro Player, abhängig von der Dauer):

- `duration_hint > 7200 s` (2 h) → `backend: "MediaElement"` — das
  `<audio>`-Element **streamt** die Preview per Range-Request (Server
  liefert 206): Playback startet nach wenigen Sekunden Pufferung, kein
  Voll-Download, kein Voll-Dekode, RAM ~0. Seek (Wort-Klick) via
  `ws.setTime()` — identische Handle-API.
- sonst → `backend: "WebAudio"` (unverändert, Karaoke-Präzision).

**Anpassungen für MediaElement:**

1. `canPlay`-Freigabe: pollt aktuell `ws.getDecodedData()` (WebAudio-only).
   Bei MediaElement stattdessen auf `readyState >= 3` (HAVE_FUTURE_DATA)
   des internen `<audio>`-Elements bzw. WS-`ready`-Event warten.
2. Timeouts: Der 60-s-Decode-Timeout entfällt bei MediaElement (kein
   Decode); Lade-Timeout bleibt (Netz).
3. Peaks + durationHint funktionieren mit MediaElement unverändert
   (Waveform wird aus den Server-Peaks gezeichnet, kein Decode nötig).

## Abgrenzung

- Preview-Bitrate (64 kbps) bleibt: mit Streaming lädt der Browser nur
  gepufferte Segmente — die Gesamtgröße ist sekundär. Optionaler Folge-
  Change: adaptive Bitrate für >2h-Dateien.
- Kein HLS/segmented streaming (Overkill; Range-Streaming reicht).
- Desktop bleibt auf WebAudio (dort ist der Voll-Dekode unkritisch).
