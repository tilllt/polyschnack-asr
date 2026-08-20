# Change 042: Benchmark-Matrix-Filter — kanal/inhalt in /samples-Response

## Problem

Klickt man in der 2-Achsen-Matrix eine Zelle an (z. B. clean × akzente, 8
Samples), erscheinen unten **keine Samples und keine Graphen**, obwohl die
Zelle korrekt zählt.

Ursache: `GET /api/benchmark/meta` baut die Matrix aus den Manifest-Samples
inkl. `kanal`/`inhalt` — aber `GET /api/benchmark/samples` liefert diese
Felder **nicht** mit (nur id/category/text/accent/age/preview/audio). Der
Frontend-Filter fällt dadurch auf Defaults zurück
(`(s.inhalt ?? "allgemein") === "akzente"` → nie wahr) → 0 Treffer.

## Lösung

- `/api/benchmark/samples`: `kanal` (Default `"clean"`) und `inhalt`
  (Default `"allgemein"`) pro Sample mitsenden — gleiche Defaults wie die
  Matrix-Zählung in `/meta`, damit Filter und Zellen immer konsistent sind.

## Tasks

- [ ] kanal/inhalt in samples()-Response aufnehmen
- [ ] Backend-Test: Samples enthalten kanal/inhalt; Filter-Matching
