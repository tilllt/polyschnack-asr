import { useRef, useState } from "react";
import type { ReactNode } from "react";
import { useDismiss } from "../useDismiss";
import { useFlipUp } from "../useFlipUp";

/**
 * Change 058 — Diarize-Tuning-Popover (ersetzt natives <details>, das sich
 * per Klick-außerhalb nie schloss): Button + zentriertes Dropdown unter dem
 * Trigger, schließt bei Klick außerhalb + Escape (useDismiss), klappt bei
 * Viewport-Überlauf nach oben (useFlipUp). Gleiche Optik wie zuvor.
 */
export function TuningPopover({ label, children }: { label: string; children: ReactNode }) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  useDismiss(wrapRef, open, () => setOpen(false));
  const flip = useFlipUp(open);
  return (
    <div ref={wrapRef} className="relative">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="text-[11px] text-muted cursor-pointer select-none px-1 py-[2px] border border-border rounded-sm bg-panel2"
      >
        {label}
      </button>
      {open && (
        <div
          ref={flip.ref}
          // Achtung: style.transform überschreibt die Tailwind-Translate-Klasse —
          // die Zentrierung (-50%) muss in den Inline-Transform wandern.
          style={{ transform: `translateX(calc(-50% + ${flip.dx}px))` }}
          className={`absolute left-1/2 ${flip.up ? "bottom-full mb-1" : "top-full mt-1"} z-[110] flex flex-col gap-2 bg-panel3 border border-border2 rounded-sm px-3 py-2 shadow-[0_8px_24px_rgba(0,0,0,.4)] min-w-[200px] max-w-[calc(100vw-16px)] max-h-[50vh] overflow-y-auto`}
        >
          {children}
        </div>
      )}
    </div>
  );
}
