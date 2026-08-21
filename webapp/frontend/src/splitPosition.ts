/**
 * Change 058 — Positionierung des Split-Popovers (Insert Segment).
 *
 * Das Popover soll NEBEN dem Split-Symbol stehen (nicht am Viewport-Rand —
 * der alte Fix `left: 8` poppte auf Desktop neben dem Hauptcontainer auf).
 * Reine Funktion → unit-testbar (TDD).
 *
 * @param btnRect getBoundingClientRect() des Split-Buttons
 * @param popW    Popover-Breite (offsetWidth)
 * @param popH    Popover-Höhe (offsetHeight)
 * @param vw      window.innerWidth
 * @param vh      window.innerHeight
 */
export function computeSplitPopover(
  btnRect: { left: number; top: number; width: number; height: number },
  popW: number,
  popH: number,
  vw: number,
  vh: number,
): { left: number; top: number } {
  const GAP = 8;
  const MARGIN = 8;

  // Bevorzugt rechts neben dem Button; passt es nicht (schmaler Viewport),
  // links davon.
  let left = btnRect.left + btnRect.width + GAP;
  if (left + popW > vw - MARGIN) {
    left = btnRect.left - popW - GAP;
  }
  left = Math.max(MARGIN, Math.min(left, vw - popW - MARGIN));

  // Vertikal am Button ausrichten, unten clampen (nie über den Viewport).
  let top = btnRect.top;
  top = Math.max(MARGIN, Math.min(top, vh - popH - MARGIN));

  return { left, top };
}
