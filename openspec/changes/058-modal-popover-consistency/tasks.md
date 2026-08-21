# Tasks — Change 058 (Popovers & Modals)

## 1. Gemeinsamer Dismiss-Hook

- [x] `src/useDismiss.ts`: `useDismiss(ref, active, onDismiss)` — `document`-`mousedown`-Listener: Ziel außerhalb `ref` → `onDismiss()`; zusätzlich `Escape`-Keydown → `onDismiss()`. Cleanup bei Inaktiv/Unmount. Export für Tests.

## 2. Reine Positions-Logik fürs Split-Popover

- [x] `src/splitPosition.ts`: `computeSplitPopover(btnRect, popW, popH, vw, vh)` → `{left, top}`.
      Rechts neben dem Button (`btn.x + btn.w + 8`); reicht rechts nicht → links (`btn.x - popW - 8`); Clamp `left ≥ 8`, `top ≥ 8`, `top ≤ vh - popH - 8`.
- [x] `src/splitPosition.test.ts`: 4+ Fälle (rechts passt / Flip nach links / Bottom-Clamp / Left-Clamp bei kleinem Viewport).

## 3. RecordingCard: Schließen + Viewport + Auto-Kopieren

- [x] `useDismiss` für `dlOpen` (bestehenden Inline-Effekt ersetzen), `shareOpen`, `versOpen` (Refs an die Wrapper-Divs).
- [x] Share-Dropdown: `max-h-[min(72dvh,520px)] overflow-y-auto` (wächst nie über den Viewport).
- [x] Annotate-Modal-Panel: `max-h-[85dvh] overflow-y-auto`.
- [x] `toggleAnonLinkState(enabled=true)`: nach Erfolg `copyToClipboard(url)` + `toast(t("anon_link_created"))`.
- [x] `copyAnonLink` nutzt `copyToClipboard` (mit Fallback statt catch-Toast).

## 4. SegmentList: Split-Popover neben dem Symbol

- [x] Split-Popover per `computeSplitPopover` positionieren (Button-Rect aus `rowRefs` + `splitAnchor.y`), `useLayoutEffect` + gemessene Popover-Größe; `left: 8` entfernen.
- [x] Escape schließt Split-Popover (+ `splitSpeakerOpen`).

## 5. Tuning-Dropdowns kontrolliert machen

- [x] `FeatureToggles.tsx`: `<details>` → Button + State + `useDismiss` (Klick-außen + Escape schließen). Styling unverändert (`absolute left-1/2 -translate-x-1/2 top-full`, `max-h-[50vh]`).
- [x] `ImportToggles.tsx`: identisch.

## 6. UploadZone Help-Modal

- [x] Panel `max-h-[85dvh] overflow-y-auto` (kleine Viewports).

## 7. i18n

- [x] `useLocale.ts`: `anon_link_created` in de/en/pt („Anonymer Link erstellt und in Zwischenablage kopiert").

## 8. Verifikation

- [x] `npm test` (Vitest) komplett grün.
- [x] `npm run build` (tsc + vite) grün.
- [x] Commit + Push auf main (direkt, kein MR), CI-Check.
