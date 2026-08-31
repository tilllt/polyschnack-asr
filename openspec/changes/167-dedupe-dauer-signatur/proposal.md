# Change 167 — Dedup: Dauer-Signatur (Parakeet-Alignment) für Stille-Kopien

**Status:** Implemented (2026-08-31, Live-Check auf der KI-Box)

## Befund (2026-08-31, Recording 297 „Tragende Wände", Ergebnis 130 / Run 140)

- Change 161 entfernt Chunk-Overlap-Dopplungen über Text-Identität + Zeit-
  Overlap (`start₂ < end₁ + 1,0 s`). Beim REALEN Fall 297 greift das nicht:
  - Kopie 1 (Chunk-Rand, in der Stille): „Im" 519,60–520,16,
    „anliegenden" **520,16–526,16 (6,0 s!)**, „Ort" **526,16–529,43 (3,27 s!)**
  - Kopie 2 (echt): „Im" 533,64–534,44, „anliegenden" 534,44–534,84,
    „Ort" 534,84–535,64 (normale 0,4–0,8 s)
  - `start₂ = 533,64 > end₁ + 1,0 = 530,43` → Zeit-Signatur verfehlt, Lücke 4,2 s.
- Der bestehende Regressionstest (test_chunk_overlap_dedup.py) bildet den
  Realbefund mit KÜNSTLICH überlappenden Zeiten ab (Kopie 2 ab 521,4) —
  dadurch grün, obwohl der Live-Fall doppelt bleibt.
- Chunk-freier ASR-Beweis: Die Phrase kommt im Audio genau EINMAL vor.

## Lösung

Zusätzliche **Dauer-Signatur** direkt aus dem Parakeet-Alignment
(Wort-Timestamps):

> Identische benachbarte Wortfolge (n ≥ 2) UND genau EINE Kopie enthält
> ein Wort mit Dauer > `duration_anomaly_s` (Default 2,5 s) → die
> gestreckte Kopie ist die Stille-Halluzination und wird entfernt
> (unabhängig davon, ob sie die erste oder zweite ist).

Begründung: Echte Sprache hat Wort-Dauern von ~0,3–0,9 s. Ein Wort mit
3–6 s Dauer ist akustisch unmöglich — der Decoder hat die Wörter am
Chunk-Rand über angrenzende Stille „gestreckt". Echte rhetorische
Wiederholungen („Ich liebe dich. Ich liebe dich.") haben in BEIDEN Kopien
normale Dauern → bleiben unangetastet (Unterschied zur Lockerung der
Zeit-Signatur, die echte Wiederholungen fälschlich entfernen würde).

## Tests

- Echter 297-Fall mit den DB-Wort-Timestamps (gestreckte Kopie 1, Lücke
  > 1 s) → Kopie 1 entfernt, `join(words) == text`.
- Gestreckte ZWEITE Kopie → Kopie 2 entfernt (Symmetrie).
- Regression: bestehende Overlap-, Fallback- und rhetorische-Fälle
  bleiben grün.
