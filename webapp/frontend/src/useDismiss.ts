import { useEffect } from "react";

/**
 * Change 058 — Einheitliche Schließ-Logik für ALLE Popover/Dropdowns/Modals:
 * Klick außerhalb (mousedown) ODER Escape schließt.
 *
 * Nutzung:
 *   const ref = useRef<HTMLDivElement>(null);
 *   useDismiss(ref, open, () => setOpen(false));
 *
 * `active` false → keine Listener (kein Overhead, kein Close bei geschlossen).
 */
export function useDismiss(
  ref: React.RefObject<HTMLElement | null>,
  active: boolean,
  onDismiss: () => void,
) {
  useEffect(() => {
    if (!active) return;
    function handlePointer(e: MouseEvent | TouchEvent) {
      const t = e.target as Node;
      if (!ref.current || !ref.current.contains(t)) onDismiss();
    }
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onDismiss();
    }
    // mousedown statt click: schließt auch, wenn der Klick in einem
    // anderen Trigger startet (Toggle-Reihenfolge bleibt korrekt).
    document.addEventListener("mousedown", handlePointer);
    document.addEventListener("touchstart", handlePointer, { passive: true });
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handlePointer);
      document.removeEventListener("touchstart", handlePointer);
      document.removeEventListener("keydown", handleKey);
    };
  }, [active, ref, onDismiss]);
}
