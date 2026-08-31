# Change 168 — Design

## Problem 1: Wörter ohne Timing brechen die gesamte Logik (User-Vorgabe)

Wörter ohne Timestamps (Aligner-Lücken, Desync nach Drag/Insert) brechen
Karaoke, Split, Timing-Edits und Segment-Reparaturen. Statt Symptome zu
kurieren gilt die **Invariante: kein Wort ohne Timing speichern** —
fehlende Zeiten werden aus den Nachbarn + geschätzter Wortlänge generiert
(≈0,09 s/Zeichen, min. 0,15 s), Lücken proportional zur Wortlänge verteilt.

## Problem 2: `undefined`-Feld verschwindet beim JSON-Serialisieren

`JSON.stringify({end: undefined})` → `"{}"`. Ein Segment, dessen `end`
nach Drag/Insert im Frontend `undefined` ist, wird vom Backend als
„missing end" abgelehnt — der 400 ist korrektes Backend-Verhalten, aber
das Frontend heilt den Zustand vor dem Senden (`ensureSegmentBounds`).

## Lösung: Invariante an der Wurzel + Frontend-Schutz

1. `ensure_word_timings` im Backend, eingebaut in `reconcile_words_to_text`
   (Choke-Point für ASR-Ergebnis, Aligner und Edit-PUT) — Wort-TS sind
   danach überall garantiert.
2. `ensureSegmentBounds` im Frontend vor jedem PUT — Segment-Ebene.
3. Split-No-Op wird sichtbar (Toast) statt still zu scheitern.

## Offene Fragen

Schätzfaktor 0,09 s/Zeichen: konservativ (längere Wörter bekommen mehr
Zeit); die Interpolation deckt nur Lücken zwischen Ankern. Falls der
Live-Betrieb zeigt, dass generierte Zeiten zu lang/kurz sind, Faktor
nachziehen (Konstante, kein Parameter — Einfachheit zuerst).

