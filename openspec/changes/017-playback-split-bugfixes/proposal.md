# Change Proposal 017 — Playback- & Split-Bugfix-Runde (2026-08-18)

**Status:** Proposed

## Why

Sechs User-Befunde aus einer Testrunde am 2026-08-18 (Webapp
whisper.cia-spandau.de, Firefox/Desktop + iOS Safari):

1. **„Loading audio“ dreht sich für immer** — der Play-Button erscheint
   nie (WaveformPlayer: `canPlay` blieb false).
2. **Volle WAV-Downloads statt Preview-MP3** — das Frontend lud bei
   fehlender Preview die komplette Audiodatei (bei langen Aufnahmen
   doppelt: WaveSurfer + `readyFetch` parallel).
3. **Karaoke-Doppel-Highlight + Scroll-Sprung** — beim Klick auf ein Wort
   weiter unten scrollte die Transkription nach oben, zwei Wörter waren
   gleichzeitig markiert.
4. **iOS: Mikro wird nach der Aufnahme nie freigegeben** — iOS zeigt den
   aktiven Mikrofon-Indikator dauerhaft.
5. **Split (Desktop/Firefox): Markierung verschwindet sofort beim
   Loslassen**; das Split-Symbol war unten abgeschnitten; die Markierung
   soll erst beim Symbol-Klick verschwinden. Zusätzlich: Symbol nicht
   mittig zur Auswahl und im Outline-Kreis kaum sichtbar.
6. **Markieren löst ein Playback aus** — Markieren/Splitten hat nichts mit
   Play zu tun; Play darf nur bei einem einfachen Wort-Klick (ab dem Wort)
   passieren.

## Root Causes (durch Code belegt)

1. `readyFetch` (WaveformPlayer Z. 296–299) lud die Audio-URL ein zweites
   Mal und verschluckte Fehler im leeren `catch` → `canPlay` blieb false.
2. `audioUrl={r.audio_preview_url ?? r.audio_url}` — `audio_preview_url`
   ist nur gesetzt, wenn das Sidecar schon existiert; der Server gab bei
   fehlender Preview 410 statt zu generieren.
3. `activeWordIndex()` klebte das letzte Wort für alle `t >= last.start`;
   die Markierung wurde auf ALLEN Segmenten berechnet → false positives
   über der Abspielposition; der Autoscroll fand das erste
   `data-active-word` im DOM (oben).
4. `prewarmMic()` öffnete den Mikrofon-Stream nach jedem Stop/Upload neu
   und die AudioSession blieb auf `play-and-record` (kein Restore).
5. `setAnchorFromRange` rief direkt nach dem Mouse-Up `removeAllRanges()`
   auf (native Auswahl weg); das Symbol wurde am Auswahl-TOP positioniert
   (nicht mittig) und ragte über die Zeilen-/Container-Unterkante; Icon
   14px im 24px-Kreis mit feinen 2.2er-Strichen.
6. Nach einer Textauswahl feuert der Browser zusätzlich ein `click` auf
   dem Start-Wort → `scheduleClick(handleWordClick)` → `seekTo` + `play`.

## Lösungsansatz (umgesetzt, Commits)

- `491020f` — iOS-Mikro-Release: kein Prewarm auf WebKit +
  `restoreAudioSessionAfterRecording()` (zurück auf `playback`) bei
  Stop/Upload/Unmount.
- `9a208e2` — Playback: Decode-Polling auf `ws.getDecodedData()` statt
  Doppel-Fetch + 90s-Timeout mit sichtbarem Fehler; `resolveAudioUrl()`
  nutzt IMMER die deterministische Preview-URL; Backend generiert das
  64-kbps-Sidecar synchron beim ersten Zugriff; Karaoke: kein Wort-Kleben
  nach Segment-Ende + Markierung nur im aktiven Segment.
- `1f168ee` — Split-Desktop: keine `removeAllRanges` im Mouse-Pfad
  (Markierung bleibt), `selectionchange`-Guard gegen Geister-Icons,
  Symbol-Top auf Zeilenhöhe geclampt.
- `575e3d8` — Symbol mittig zur Auswahl (`rangeRect.top + height/2`),
  Icon 18px im 26px-Kreis mit kräftigeren Strichen.
- `2f7fd98` — Markieren ≠ Play: Wort-`onClick`-Guard (native Selection
  nicht kollabiert ODER Touch-Drag), Touch-Tap setzt keinen Split-Anker.
