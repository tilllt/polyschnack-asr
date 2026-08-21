# Change 058 — Popovers & Modals: konsistentes Schließen + Positionierung

## Problem

Die UI mischt drei Overlay-Arten mit **unterschiedlichem Verhalten**:

1. **Klick-außerhalb schließt nicht überall:** Share- und Versionen-Dropdown
   (RecordingCard) schließen NUR über erneuten Klick auf den Trigger-Button;
   die Diarize-Tuning-`<details>`-Popover (FeatureToggles/ImportToggles)
   schließen nie durch Klick nach außen (natives `<details>`-Verhalten). Nur
   Download-Dropdown, Speaker-Menüs, Annotate- und Help-Modal schließen
   bereits per Klick-außerhalb.
2. **Inkonsistente Position:** Das Split-/Insert-Segment-Popover (SegmentList)
   ist hart auf `left: 8` (linker Viewport-Rand) positioniert — auf Desktop
   poppt es neben dem zentrierten Hauptcontainer links auf, statt neben dem
   Split-Symbol. User-Befund: „Wenn man auf Desktop den Insert Segment Button
   drückt, poppt das Modal irgendwo komplett neben dem Main Seitencontainer
   links auf."
3. **Viewport-Überlauf:** Das Share-Dropdown „wächst", wenn ein Anon-Link
   aktiv wird (URL-Zeile + Retention-Warnung), und wird höher als der
   Viewport — die Unterkante ist ohne Scroll nicht erreichbar.
4. **Fehlendes Auto-Kopieren:** Ein neu generierter Anon-Share-Link wird
   nicht automatisch in die Zwischenablage kopiert (nur der manuelle
   ⧉-Button kopiert).

## Ziel

- **Einheitliche Schließ-Logik:** ALLE Popover/Dropdowns/Modals schließen bei
  Klick außerhalb (+ Escape). Ein gemeinsamer Hook `useDismiss`.
- **Konsistente Position:** Echte Modals (Annotate, Help) = zentriertes
  Overlay mit `max-h` + Scroll-Sicherheitsnetz; Trigger-Dropdowns (Share,
  Versionen, Download, Speaker, Tuning) = am Trigger verankert, viewport-
  geklemmt (bestehendes `useFlipUp`-Muster); Split-Popover = neben dem
  Split-Symbol, nie am Viewport-Rand.
- **Kein Overlay größer als der Viewport:** `max-h` + `overflow-y-auto` überall.
- **Auto-Kopieren:** Anon-Link-Generierung → `navigator.clipboard.writeText`
  (Fallback textarea/execCommand) + Toast „Link erstellt und kopiert".

## Umsetzung (Frontend only — kein Backend, kein API-Contract)

| Datei | Änderung |
|---|---|
| `src/useDismiss.ts` (neu) | Hook: `useDismiss(ref, active, onDismiss)` — `mousedown` außerhalb + `Escape` schließen |
| `src/splitPosition.ts` (neu) | Pure Funktion `computeSplitPopover(btnRect, popW, popH, vw, vh)` — rechts neben dem Button, Flip nach links bei Platzmangel, Clamp an Viewport |
| `src/clipboard.ts` (neu) | `copyToClipboard(text)` — `navigator.clipboard` mit execCommand-Fallback |
| `RecordingCard.tsx` | `useDismiss` für dl/share/vers-Dropdowns (dl-Effekt vereinheitlichen); Share-Dropdown `max-h` + Scroll; Annotate-Modal `max-h`; `toggleAnonLinkState` auto-copy + Toast `anon_link_created` |
| `SegmentList.tsx` | Split-Popover-Position via `computeSplitPopover` statt `left: 8`; Escape |
| `FeatureToggles.tsx` / `ImportToggles.tsx` | `<details>` → kontrolliertes Popover mit `useDismiss` |
| `UploadZone.tsx` | Help-Modal: `max-h` + Scroll-Sicherheitsnetz |
| `useLocale.ts` | Neuer Key `anon_link_created` (de/en/pt) |

## Tests

- `splitPosition.test.ts` (neu): rechts-Fit, Flip nach links, Clamp links/bottom, Mindestabstand.
- `RecordingCard.test.tsx`: Share-Dropdown schließt bei Klick außerhalb; Anon-Link-Generierung kopiert automatisch (mock `navigator.clipboard`) + Toast.
- `npm test` (Vitest) komplett grün; `npm run build` (tsc + vite) grün.

## Out of Scope

- `searchOpen` (Inline-Panel, kein Floating-Overlay) — bleibt Toggle-Verhalten.
- `focusMode` (Vollbild-Edit-Modus mit eigener Schließen-UI + Escape) — kein Modal.
- Backend/API unverändert.
