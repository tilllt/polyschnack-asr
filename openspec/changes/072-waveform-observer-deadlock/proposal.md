# Change 072 — Waveform-Deadlock: IntersectionObserver auf hidden Container

**Status:** in Arbeit · **Datum:** 2026-08-21

## Problem

User-Befund (2026-08-21, nach Deploy von Change 070): „Waveforms lade
immer noch endlos."

Live-Verifikation (2026-08-21):
- Deployter Stand enthält 070 (Live-Bundle == lokaler dist, Peaks als
  Effect-Dependency vorhanden)
- Backend ist schnell: `waveform_peaks` (2000 Werte) in 0,3 s,
  Preview-MP3 in 1,3 s — die API ist NICHT das Problem
- Playwright-Live-Tests: alte Share-Links abgelaufen; Login nur per
  Cookie (kein localStorage-Token) → Live-Szenario nicht reproduzierbar,
  deshalb Code-Beweis

## Root Cause (Code-Beleg)

Deadlock in `WaveformPlayer.tsx`:

1. Der Canvas-Container (`containerRef`) trägt bis `ready` die Klasse
   `hidden` (`display:none`) — Zeile 587.
2. Der IntersectionObserver (Change 052, Lazy-Loading) beobachtet genau
   diesen Container — Zeile 241.
3. `display:none`-Elemente liefern NIE `isIntersecting: true` → `inView`
   bleibt `false`.
4. Der Init-Effekt bricht sofort ab (`if (!inView) return;`) → WaveSurfer
   wird nie gestartet → `ready` bleibt `false` → Container bleibt hidden
   → „Loading waveform…" für immer.

Der 070-Fix (peaks/durationHint als Effect-Dependencies) konnte nicht
greifen, weil der Effekt wegen `inView=false` gar nicht erst lief.
070 war nötig, aber nicht hinreichend.

## Ziel

Der IntersectionObserver beobachtet ein Element, das NIE hidden ist —
den äußeren Wrapper. Damit wird `inView` korrekt true, sobald die Karte
in den Viewport kommt, und der Init-Effekt läuft (mit oder ohne Peaks,
070-Fix greift dann auch).

## Verhaltens-Delta (IST → SOLL)

- **IST:** Observer auf hidden Container → inView bleibt false → endlos
  „Loading waveform…".
- **SOLL:** Observer auf äußeren Wrapper → inView true bei Sichtbarkeit →
  WaveSurfer startet → Waveform erscheint (sofort mit Peaks, sonst nach
  Decode/Timeout mit sichtbarem Fehler statt Endlos-Spinner).

## Umsetzung

1. `WaveformPlayer.tsx`: `outerRef` auf dem äußeren Wrapper (`<div
   ref={outerRef} className="w-full">`); Observer nutzt `outerRef.current`
   statt `containerRef.current`. Container bleibt hidden bis ready
   (Canvas braucht die Sichtbarkeit nicht, der Wrapper liefert die
   Intersection).
2. Tests: Fake-IntersectionObserver recordet jetzt die beobachteten
   Elemente (vorher `observe()` no-op → kein Test konnte den Deadlock
   sehen). 2 neue Regressionstests: (a) beobachtetes Element ≠ hidden
   Container, sondern sichtbarer Vorfahre; (b) Init startet trotz hidden
   Container (fire auf Wrapper → create+load mit Peaks).

## Referenzen

- Change 052 (Lazy-Loading via IntersectionObserver), Change 059
  (lite-Liste, Peaks asynchron), Change 070 (Peaks als Dependency —
  unzureichend, weil Effekt nie lief).
