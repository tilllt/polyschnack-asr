# Change 104 — Waveform-Klick: kein Play-Flicker vor Decode + Lücken-Scroll

## Problem

User-Befund 2026-08-23:

1. „Der Player zeigt den Hintergrund-Load-Indikator. Wenn die Waveform
   komplett geladen ist, wird der Play-Button grau gezeigt und man kann
   drauf klicken: kein Audio spielt, er flickert kurz zum Pause-Symbol.
   Nach längerem Warten kann man Play drücken." — Der Klick geht auf die
   WAVEFORM (der Play-Button selbst ist `disabled={!canPlay}`). Der
   Container-Click-Handler rief `ws.play()` OHNE canPlay-Guard: während
   der Decode noch läuft (canPlay=false → Button grau), setzt der Klick
   den Play-State (Flicker zum Pause-Symbol), aber kein Ton startet.
2. „Wenn man in der Waveform an eine Stelle drückt, an der kein Dialog
   ist, soll das Transkript trotzdem an die Stelle scrollen, die als
   Nächstes dran ist." — `activeSegmentIndex` lieferte bei Zeiten in
   Dialog-Lücken (zwischen Segment-Ende und nächstem Segment-Start bzw.
   vor dem ersten Segment) −1 → kein Auto-Scroll.

## Fix

1. WaveformPlayer.tsx (Container-Click): `ws.play()` nur bei
   `canPlayRef.current` — während des Decodes wird nur geseekt
   (Cursor + Transkript-Scroll via onTimeUpdate), kein Play-Versuch.
2. karaoke.ts `activeSegmentIndex`: Liegt die Zeit in keiner
   Segment-Range, wird das NÄCHSTE Segment (start >= t) aktiv; der
   Fall „nach dem letzten Segment" bleibt unverändert (letztes Segment).

## Tests

- karaoke.test.ts: Lücke zwischen Segmenten (t=5.5 bei [1-5]/[6-9]) → 1;
  vor dem ersten Segment → 0; bestehender −1-Test auf neue Semantik
  angepasst. Frontend 303/303, tsc 0.
