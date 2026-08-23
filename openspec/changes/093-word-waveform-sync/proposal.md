# Change 093 — Wort-/Waveform-Sync: Sticky-Hover, Seek-Meldung, Virtualizer-Scroll

**Status:** Implementiert (Code lokal, nicht committet)
**User-Auftrag (2026-08-22, Chrome/Android):**
> Klick auf Wort: Playback startet, Wort bleibt aber immer noch blau markiert.
> Klick in wavesurfer Wellenform: selbst wenn man an eine Stelle klickt an der
> Sprache ist, scrollt die transcription nicht an die richtige Stelle, hebt das
> Wort mit Karaoke Markierung hervor und scrollt es vertikal mittig in der
> Transkriptionsansicht.

## Probleme & Ursachen

### P1: Wort bleibt nach Klick blau (Touch)
- Wort-Spans nutzen `hover:text-accent/70`; `accent` = `#5b8cff` (blau).
- Android/Chrome implementiert `:hover` nach dem ersten Tap als **Sticky-Hover**:
  das angetippte Element behält den Hover-Zustand, bis woanders hingetippt wird.
- Kein `touch-sel` (Split-Markierung) und kein `karaoke-active` — der Klick-
  Handler (Change 091) räumt Markierungen korrekt auf; das Blau ist der Hover.

### P2a: Waveform-Klick meldet den Seek nicht sofort
- `onContainerClick` rief nur `ws.setTime(t)` + `ws.play()`.
- Transkript-Scroll/Karaoke-Highlight hingen am nächsten `timeupdate`/rAF-Tick —
  der feuert nur, wenn `play()` wirklich startet (WebAudio-Kontext/Puffer;
  auf Android gern verzögert). Cursor sprang, Transkription blieb stehen.

### P2b: Virtualisierung (Change 087) bricht den Auto-Scroll bei weiten Sprüngen
- Nur ~5 Zeilen sind gerendert; bei einem Sprung in die Welle (z. B. 57 min)
  ist das Ziel-Segment **nicht im DOM** → `rowRefs.current[activeIdx]` leer →
  `if (!target) return` → kein Scroll, kein Karaoke-Highlight, keine Zentrierung.

## Fixes

1. **`tailwind.config.js`:** Eigene Variante `hoverable` =
   `@media (hover: hover) { &:hover }`. Hover-Effekte nur noch auf Geräten
   mit echter Hover-Fähigkeit (Maus/Trackpad) — Touch bekommt keinen
   Sticky-Hover mehr. Wort-Span: `hover:text-accent/70` → `hoverable:text-accent/70`.
2. **`WaveformPlayer.tsx` (`onContainerClick`):** `setCurrentTime(t)` +
   `onTimeUpdateRef.current?.(t)` sofort im Click-Handler (vor `ws.play()`).
3. **`SegmentList.tsx` Auto-Scroll (aktives Wort):** Ziel-Zeile nicht im DOM →
   erst `virtualizer.scrollToIndex(activeIdx, { align: "center" })`, dann nach
   zwei Frames (Render fertig) das aktive Wort exakt vertikal mittig
   (`data-active-word`-Query + `container.scrollTo`).
4. **`SegmentList.tsx` Such-Scroll (`searchJump`):** gleiche Behandlung
   (scrollToIndex + rAF-Nachzentrierung), gleicher Virtualisierungs-Bug.

## Verifikation

- tsc sauber, 296/296 Frontend-Tests grün, Vite-Build ok.
- Touch-Emulation (Pixel 7, `touchscreen.tap`): Wort-Tap → `playing: true`,
  `karaoke-active` (gelb), kein `touch-sel`; Play-Button bleibt bis zum echten
  Decode disabled (Change 090-Mechanik).
- Waveform-Klick-Endverifikation (Scroll + Karaoke + Zentrierung) auf dem
  Produktions-Build noch ausstehend (lokales Setup instabil: 45,7-MB-Preview-
  Decode ~30 s, gelegentliche `AbortError`s).

## Offene Folgearbeit (unverändert)

- Change 089 (Waveform/Audio-Preview-Lazy-Load beim Seiten-Load, ~2,6-s-Long-Task).
- WaveSurfer-Pinning `7.12.11` ohne `^` — User-Entscheidung steht aus.
