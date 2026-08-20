# Change 044: Benchmark-Balken — Skalierung auf Qualität (bestes Modell = volle Breite)

**Status:** proposal
**Datum:** 2026-08-20
**Typ:** Bugfix (Change 040-Nacharbeit)

## Problem

Die in Change 040 eingeführten grafischen Qualitäts-Balken (Kategorie + Sample)
repräsentieren die angezeigten WER-Werte nicht: Alle Balken wirken gleich lang.

### Root Cause

Beide Balkenformeln berechnen die Breite als

```ts
pct = Math.round((wer / best) * 100)   // best = bester (kleinster) WER
```

Da `best` das **Minimum** aller WER-Werte ist, ergibt:

- bestes Modell: `wer / best = 1.0` → 100 % ✓
- jedes schlechtere Modell: `wer / best > 1.0` → z. B. 300 % → durch
  `overflow-hidden` des Containers auf 100 % gedeckelt

→ Alle Modelle mit WER > best erscheinen als voller Balken. Die Länge ist
damit nicht mehr proportional zur Qualität (bzw. invers zum WER) — sie
repräsentiert die angegebenen Werte nicht.

Die Code-Kommentare (Z. 317) dokumentieren die Intention: *„Balkenbreite =
relative Qualität (bestes Modell = volle Breite)"* — umgesetzt wurde die
inverse Division.

### Beispiel (Kategorie „Akzente", Testdaten)

| Backend | WER | aktuell (`wer/best`) | gewollt (`best/wer`) |
|---|---|---|---|
| crispr-pk-cpp | 0,10 | 100 % | 100 % |
| ps-pk-onnx | 0,30 | 300 % → 100 % (gedeckelt) | 33 % |

## Lösung

Division umdrehen, damit die Länge die **relative Qualität** (invers zum WER)
darstellt und nie > 100 % wird:

```ts
pct = Math.min(100, Math.max(4, Math.round((best / (wer || 0.0001)) * 100)))
```

- bestes Modell (kleinster WER) = volle Breite (100 %)
- schlechtere Modelle proportional kürzer (best/wer ≤ 1)
- `Math.min(100, …)` schützt gegen wer = 0 (best/0.0001 ≫ 100)
- Minimum 4 % bleibt (schwache Werte noch sichtbar)
- Farbe (`werColor`, grün→rot) bleibt unverändert — codiert den Absolutwert

Betroffen: `webapp/frontend/src/components/BenchmarkPage.tsx`

- Zeile ~145 (Sample-Balken): `bestW / (wer || 0.0001)`
- Zeile ~348 (Kategorie-Balken): `best / (r.wer || 0.0001)`

## Tests

- `BenchmarkPage.test.tsx`: bestehender Kategorie-Test (0,3 vs. 0,1) prüft
  zusätzlich die **Breite** der Füllung: bestes Modell = `width: 100%`,
  schlechteres = `width: 33%` (gerundet, 0.1/0.3)
- Neuer Sample-Balken-Test analog (perSample 0,2 vs. 0,1 → 100 % / 50 %)
- Frontend-Tests grün

## Checkliste

- [ ] proposal.md angelegt
- [ ] tasks.md angelegt
- [ ] Fix in BenchmarkPage.tsx (2 Formeln)
- [ ] Tests ergänzt
- [ ] Frontend-Tests laufen grün
- [ ] Commit + Push
