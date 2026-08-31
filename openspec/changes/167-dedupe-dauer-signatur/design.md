# Change 167 — Design

## Problemklasse

Change 161 erkennt Overlap-Duplikate nur über den zeitlichen Überlapp
der Kopien. Liegt die erste Kopie aber in Stille (Chunk-Rand-Halluzination,
Wörter über die Lücke gestreckt), entsteht eine zeitliche Lücke zur echten
Kopie → kein Treffer, obwohl das Alignment die Dopplung eindeutig zeigt.

## Signal

Das Parakeet-Alignment (Wort-Timestamps) IST das Erkennungssignal:
- echte Sprache: Wort-Dauern ~0,3–0,9 s
- Stille-Halluzination: Wörter 3–6 s (gestreckt über die Lücke)

Deterministische Regel: identische benachbarte Folge (n ≥ 2) + genau EINE
Kopie mit `max(Wort-Dauer) > 2,5 s` → die gestreckte Kopie entfernen.
Symmetrisch (erste ODER zweite Kopie kann die gestreckte sein).

## Alternativen

1. **Zeit-Signatur lockern** (start₂ < end₁ + 5 s o.ä.) — verworfen:
   entfernt echte rhetorische Wiederholungen (zeitlich getrennt, normale
   Dauern in beiden Kopien).
2. **Audio-Energie im Wortfenster prüfen** (Stille = keine Energie) —
   akustisch präziseste Variante, aber Post-Processing müsste Audio
   laden; die Dauer-Signatur nutzt NUR das Alignment (User-Vorgabe) und
   ist deterministisch.
3. **Dauer-Signatur (gewählt)** — robust, rein aus den Wort-Zeiten,
   keine Audio-Abhängigkeit, Regressions-sicher.

## Offene Fragen

Schwellwert 2,5 s: sehr langsame/deutliche Rede kann einzelne Wörter
> 1,5 s erzeugen, 2,5 s+ ist praktisch ausgeschlossen (Parakeet-Zeiten
eher 0,3–0,8 s). Falls der Live-Betrieb Fehltreffer zeigt: Schwellwert
nachziehen (konfigurierbar via Parameter).
