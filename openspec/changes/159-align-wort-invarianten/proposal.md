# Change 159 — Aligner-Wort-Invarianten: Mindestdauer + Monotonie

**Status:** Proposed

## Befunde (2026-08-30, Prod-DB + Live-A/B auf der Box)

1. **Letztes Wort ohne Timing (Karaoke-Skip):** 207/1809 Segmente
   (11,4 %) haben ein letztes Wort mit < 0,1 s Dauer — **140× exakt
   0,08 s** (Kollaps-Signatur `e = s + 0.08`). Beispiele: `telefoniert.`
   12.24→12.32, `Art.` 212.14→212.22. Ursache: Der qwen3-forced-aligner
   quetscht das letzte Wort eines Segments an die Audio-Kante (0-Dauer /
   minimale Restzeit) → die Kette `_energy_refine → _resolve_zero_duration`
   kollabiert es auf 80 ms → `activeWordIndex` findet das Wort praktisch
   nie aktiv → Karaoke überspringt es.
2. **Puffer-Hypothese FALSIFIZIERT (A/B auf der Box):** Segment-Audio mit
   `-to seg_end + 0.5 s` geschnitten macht es SCHLECHTER (12.72→12.74
   statt 12.08→12.16) — der Aligner legt das letzte Wort ans gepufferte
   Audio-Ende. Kein Audio-Schnitt-Problem; die Wort-Verteilung ist das
   Problem.
3. **„Textpassagen verdoppeln sich":** Der Grenz-Drag-Pfad ist sauber
   (Browser-Repro: 6 Drags hin/zurück, Wortzahl konstant, keine Duplikate
   — 2026-08-16-Fix wirkt). Die 32 „Duplikat"-Segmente in der DB sind
   **Zeit-Kollisionen**: 0-Dauer-Ketten (z.B. 4× „ja" auf identischer
   80-ms-Klasse 2227.52→2227.6) → Karaoke markiert mehrere Wörter
   gleichzeitig = sieht aus wie doppelt.

## Lösung: Zwei Invarianten in `_resolve_zero_duration`

1. **Monotonie:** kein Wort startet vor dem Vorgänger-Ende; Wörter mit
   `end <= start` bekommen `end = start + 0.08` → 0-Dauer-Ketten werden
   auseinandergezogen (Karaoke markiert sequenziell).
2. **Mindestdauer fürs LETZTE Wort:** nie < 0,3 s — Start rückwärts
   ziehen (begrenzt durch Vorgänger-START); Überlappung mit dem Vorgänger
   ist akzeptabel (das Wort wird im Karaoke sichtbar statt übersprungen).

Tests: 26 grün (3 neue: Mindestdauer Ein-Wort, Kollaps mit Vorgänger,
0-Dauer-Kette-De-Kollision).

Hinweis: Alte Align-Ergebnisse in der DB behalten die Kollaps-Zeiten —
ein Re-Align (Button) wendet die Invarianten auf neue Aligner-Läufe an.
