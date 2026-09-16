# Change 197 — Wort-Timing-Anzeige in Millisekunden + Zoom-Grenze

## Problem

Im Timing-Tab war die Wortlänge praktisch immer `00:00`.

**Ursache:** `fmtTimecode()` rundet auf ganze Sekunden (`Math.floor(s % 60)`).
Ein Wort von 0,32 s Länge → `00:00`. Damit ist die Length-Anzeige nicht nur
unbrauchbar, sondern zeigt einen falschen Wert (0 statt 320 ms) — der Nutzer
kann nicht erkennen, ob ein Timing überhaupt gesetzt ist.

Dasselbe Problem bei Start und Ende: bei Wort-Timings ist Sekundengenauigkeit
wertlos — 12,3 s und 12,8 s sind nicht unterscheidbar, obwohl der Unterschied
für die Wortgrenze entscheidend ist.

**Zweiter Befund (bei der Analyse gemessen):** `MAX_TIMING_PPS = 2000` deckelt
den Wort-Zoom, sodass kurze Wörter ihr 30-%-Zielfenster nie erreichen:

- Wort 20 ms → nur **4,0 %** der Containerbreite (statt 30 %)
- Wort 50 ms → 10,0 %
- Wort 100 ms → 20,0 %
- Wort ≥ 150 ms → 30,0 % ✓

Ein 20-ms-Wort ist damit im Timing-Tab praktisch nicht markierbar — genau die
Klasse von Wörtern, für die man den Timing-Modus überhaupt öffnet.

## Lösung

### 1. `fmtShortTimecode()` — neue Formatierung mit Millisekunden

`src/format.ts`:

```ts
/** Dauer in Sekunden → "MM:SS.sss" (für Wort-Timing, Millisekunden-Auflösung) */
export function fmtShortTimecode(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.max(0, s % 60);
  // 2 Vorkomma- + 3 Nachkommastellen = 6 Zeichen ("00.320")
  return `${String(m).padStart(2, "0")}:${sec.toFixed(3).padStart(6, "0")}`;
}
```

`fmtTimecode()` bleibt unverändert — es wird an Stellen mit langen Zeitspannen
(Segment-Start, Suchergebnisse) weiter genutzt, wo `MM:SS` richtig ist.

`TimingEditor.tsx` (Kopfzeile des geladenen Wortes) nutzt jetzt für **Start,
Ende und Länge** `fmtShortTimecode`.

### 2. `MAX_TIMING_PPS` 2000 → 48000

`src/waveformTime.ts`. 48000 lässt die Mindest-Wortdauer
(`MIN_WORD_DURATION_S = 0.02`) ihr Zielfenster treffen: bei 1000 px Container
ergibt `0.3 * 1000 / 0.02` = 15000 px/s, also unterhalb der neuen Grenze.

Die progressive-Peaks-Maschinerie trägt das: `needed = pps × Dauer`, gedeckelt
bei 300000 Punkten. Beispiel: 15000 px/s × 60 s = 900000 → 300000 Punkte
→ 3 px pro Peak-Punkt.

## Tests

- `format.test.ts`: `fmtShortTimecode`-Fälle inkl. Invariante
  „`fmtTimecode` verliert Sub-Sekunden, `fmtShortTimecode` nicht".
- `waveformTime.test.ts`: **Invariante** — die Mindest-Wortdauer muss das
  30-%-Zielfenster erreichen (`pps < MAX_TIMING_PPS` und
  `dauer × pps / breite ≈ 0.3`). Das ist der Test, der die Regression
  „MAX zu niedrig" künftig verhindert.
- Der alte Clamp-Test nutzte `0.01 s` und traf mit 48000 nicht mehr —
  auf `0.001 s` / `0.0001 s` umgestellt (dort greift der Clamp weiterhin).

## Abgrenzung

Change 196 hat den Timing-Marker auf das WaveSurfer-`RegionsPlugin` umgestellt
(Marker-Höhe/Position/Drag nativ). Change 197 setzt darauf auf und behebt die
Anzeige-Präzision und die Zoom-Grenze — beide betreffen ausschließlich den
Timing-Tab.
