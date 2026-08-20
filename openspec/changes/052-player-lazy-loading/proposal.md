# Change 052: Lazy-Loading im WaveformPlayer (nur sichtbare Samples laden)

**Status:** proposal
**Datum:** 2026-08-20
**Typ:** UX/Performance-Bugfix

## Problem

User-Befund 2026-08-20: Auf der Benchmark-Seite spielen „viele Audios"
nicht — Play-Klick ohne Wirkung. Headless-Reproduktion (Playwright):

- Beim Öffnen einer Kategorie lädt der Browser **ALLE** Sample-Player
  gleichzeitig (belegt: 8× `GET /api/benchmark/preview/telefon_00X` in
  einem Schub) — kein Lazy-Loading.
- Die Previews sind klein (78–112 KB), aber bei langsamem Netz (User:
  „sehr langsames Netz") queueen die parallelen fetches; der Player ist
  beim Play-Klick noch nicht abspielbereit → „es passiert nichts".
- Im schnellen Headless-Test funktioniert derselbe Player (Play startet,
  Zeit läuft) — der Unterschied ist die Netz-/Lade-Situation.

## Lösung

**Lazy-Loading im WaveformPlayer** (generisch, wirkt überall — auch bei
langen RecordingCard-Listen):

- IntersectionObserver auf dem Player-Container (`rootMargin: 200px`):
  `ws.load()` wird erst ausgelöst, wenn der Player sichtbar wird.
- Vorher: kein Fetch, kein Decode — nur das leere Player-Gerüst.
- Nach Sichtbarkeit: normaler Load-Pfad (Peaks/Preview, canPlay-Polling,
  Timeouts) — unverändert.
- Unmount-Cleanup bleibt null-safe.

Damit lädt beim Öffnen einer Kategorie nur noch das/die sichtbaren
Samples statt aller 8; beim Scrollen laden die nächsten nach.

## Abgrenzung

- Kein virtuelles Scrolling/Unmounting — nur verzögertes Laden (der
  User-Vorschlag „nur Viewport-Samples laden").
- Peaks-Optimierung (Benchmark-Samples haben keine Server-Peaks) bleibt
  separates Thema.
