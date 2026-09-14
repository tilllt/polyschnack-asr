# Design — Change 192

## Zeilen-Layout (Row 1)

```
[logo PolySchnack]  [Transcribe | Settings | Benchmark | Admin]  [🇩🇪 ▾]      →   [Guthaben] [Name] [Symbol]
```

- Container: `flex flex-wrap items-center gap-x-2 sm:gap-x-4` wie bisher.
- Nutzerbereich mit `ml-auto` → rechtsbündig, bricht auf schmalen Geräten in
  die nächste Zeile um (bestehendes Verhalten).
- Reihenfolge rechts: Guthaben-Chip → Username → Symbol (An-/Abmelden).

## Flaggen-Dropdown (`components/LangMenu.tsx`)

- Trigger: Flagge der aktuellen Sprache, `aria-haspopup="listbox"`,
  `aria-expanded`, `title`/`aria-label` = „Sprache" (lokalisiert).
- Liste: `role="listbox"` mit `role="option"` + `aria-selected`; Auswahl
  schließt und setzt die Sprache über `setLang` (bestehender Pfad).
- Schließen: `useDismiss(ref, open, …)` — Klick außerhalb (mousedown/touch)
  und Escape.
- Keine native `<select>`-Lösung: Flaggen werden dort je nach Plattform nicht
  gerendert, und die Projektvorgabe ist „Dark-Selects statt native".

## Status (StatsBar)

Behalten: `total` (Aufnahmen), `total_audio_s` (Gesamtlänge), `total_size_bytes`
(Speicher) + Geräte-Badge. Entfernt: `done`, `uploaded`, `processing`.

## Tests

- Vitest: Menü und Flaggen-Trigger vorhanden; Dropdown öffnet, Auswahl setzt
  die Sprache und schließt; Escape schließt.
- Vitest/StatsBar: nur die drei Kennzahlen + Badge gerendert.
- `tsc --noEmit` sauber.
