import { useEffect, useRef, useState } from "react";

/**
 * Dropdown-Flip (aus RecordingCard extrahiert, Change 058 — jetzt auch für
 * die Tuning-Popover): öffnet nach unten, aber wenn das Menü unter den
 * Viewport ragen würde (Mobile!), klappt es nach oben auf. Zusätzlich
 * horizontal: right-0-verankerte Menüs ragen auf schmalen Screens links aus
 * dem Viewport, wenn der Trigger-Button nicht ganz rechts steht. Statt nur
 * left/right zu tauschen (verschiebt das Problem nur auf die andere Seite)
 * wird per translateX exakt geklemmt: dx > 0 schiebt das Menü nach rechts,
 * bis es komplett sichtbar ist (Fix 2026-08-15, User-Befund „abgeschnittene
 * Modals bei allen Buttons").
 */
export function useFlipUp(open: boolean) {
  const ref = useRef<HTMLDivElement>(null);
  const [up, setUp] = useState(false);
  const [dx, setDx] = useState(0);
  useEffect(() => {
    if (!open) return;
    const id = requestAnimationFrame(() => {
      const el = ref.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      setUp(r.bottom > window.innerHeight - 8);
      // Menü ist right-0 verankert: ragt es links aus dem Viewport
      // (r.left < 0), schiebe es um exakt den Überstand nach rechts.
      let shift = 0;
      if (r.left < 8) shift = 8 - r.left;
      // Sicherheitsnetz rechts (min-w kann breiter als der Platz sein).
      if (r.right > window.innerWidth - 8) {
        shift = Math.min(shift, window.innerWidth - 8 - r.right);
      }
      setDx(shift);
    });
    return () => cancelAnimationFrame(id);
  }, [open]);
  return { ref, up, dx };
}
