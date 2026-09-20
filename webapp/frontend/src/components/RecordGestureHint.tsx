/**
 * Change 216 (Nutzer-Vorgabe 20.09.2026) — Gestenhinweise am Aufnahmeknopf.
 *
 * Der Nutzer wollte die Hilfe NICHT als Block neben dem Knopf (genau das war
 * die frühere, ausdrücklich verworfene Lösung), sondern als halbtransparente
 * Kopie des Knopfes, die über dem echten Knopf liegt und die Geste selbst
 * vorführt: nach oben wischen, nach unten wischen, senken (Halten), heben
 * (Loslassen) — alles auf der Kreisform des Knopfes.
 *
 * Aufbau (drei Bauteile, die sich nicht beeinflussen können):
 *   .ps-record-stage  — Bezugsrahmen; genau so groß wie der Knopf, weil nur
 *                       der Knopf im Fluss liegt. Kopie und Hinweiszeile sind
 *                       absolut positioniert und damit nicht layoutwirksam.
 *   .ps-record-ghost  — Kopie in gleicher Größe und Form (inset: 0), Deckkraft
 *                       0,55, pointer-events: none (fängt keine Klicks ab).
 *   .ps-record-tip    — eine Zeile Text unter dem Knopf, innerhalb der festen
 *                       Zone, ohne Einfluss auf die Höhe.
 *
 * Der Textknoten trägt bewusst KEINEN key: beim Wechsel des Hinweises bleibt
 * derselbe DOM-Knoten bestehen, es wechselt nur der Textinhalt. Dadurch kann
 * nichts neu aufgebaut werden und nichts springen.
 */
import type { ReactNode } from "react";

/** Größe und Form des Aufnahmeknopfes — gilt für Knopf UND Kopie. */
export const RECORD_BUTTON_SHAPE = "w-16 h-16 sm:w-20 sm:h-20 rounded-full";

export type GestureKind = "lock" | "stop" | "hold" | "release";

export interface GestureTip {
  kind: GestureKind;
  /** Schlüssel im Textkatalog (src/useLocale.ts). */
  key: string;
  /** Klasse, die die Bewegung der Kopie steuert (src/index.css). */
  anim: string;
}

export const RECORD_GESTURE_TIPS: readonly GestureTip[] = [
  { kind: "lock", key: "gesture_lock_up", anim: "ps-ghost-lock" },
  { kind: "stop", key: "gesture_stop_down", anim: "ps-ghost-stop" },
  { kind: "hold", key: "gesture_hold", anim: "ps-ghost-sink" },
  { kind: "release", key: "gesture_release_pause", anim: "ps-ghost-rise" },
];

/** Hinweis für eine laufende Nummer — immer gültig, auch bei negativen Werten. */
export function gestureTipAt(tipIdx: number): GestureTip {
  const n = RECORD_GESTURE_TIPS.length;
  return RECORD_GESTURE_TIPS[((tipIdx % n) + n) % n];
}

/**
 * Symbol des jeweiligen Hinweises: Kreis als Grundform (wie der Knopf), darin
 * das Zeichen der Geste. Ein- bzw. zweifarbig aus der eigenen Palette:
 * Grün var(--ps-accent,#2ea043), Rot var(--ps-err,#f85149), Amber #d99e2b.
 * Bewusst kein currentColor — die Farben sollen nicht von der Umgebung
 * abhängen.
 */
function GestureIcon({ kind }: { kind: GestureKind }): ReactNode {
  const svgProps = {
    width: 26,
    height: 26,
    viewBox: "0 0 24 24",
    "aria-hidden": true as const,
    focusable: "false" as const,
    style: { display: "block" as const },
  };

  if (kind === "lock") {
    return (
      <svg {...svgProps}>
        <circle
          cx="12"
          cy="12"
          r="9.4"
          fill="none"
          stroke="var(--ps-accent, #2ea043)"
          strokeOpacity="0.5"
          strokeWidth="1.5"
        />
        <path
          d="M12 17.2V8.4M8.3 12.1 12 8.4l3.7 3.7"
          fill="none"
          stroke="var(--ps-accent, #2ea043)"
          strokeWidth="2.1"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  }

  if (kind === "stop") {
    return (
      <svg {...svgProps}>
        <circle
          cx="12"
          cy="12"
          r="9.4"
          fill="none"
          stroke="var(--ps-err, #f85149)"
          strokeOpacity="0.5"
          strokeWidth="1.5"
        />
        <path
          d="M12 6.8v8.8M8.3 11.9 12 15.6l3.7-3.7"
          fill="none"
          stroke="var(--ps-err, #f85149)"
          strokeWidth="2.1"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  }

  if (kind === "hold") {
    // Aufnehmen: grüner Punkt im Kreis — dieselbe Farbe wie der Ruhezustand
    // des Knopfes („halten: aufnehmen").
    return (
      <svg {...svgProps}>
        <circle
          cx="12"
          cy="12"
          r="9.4"
          fill="none"
          stroke="#2ea043"
          strokeOpacity="0.5"
          strokeWidth="1.5"
        />
        <circle cx="12" cy="12" r="5" fill="var(--ps-accent, #2ea043)" />
      </svg>
    );
  }

  // release → Pause: zwei amberfarbene Balken wie im pausierten Knopf.
  return (
    <svg {...svgProps}>
      <circle
        cx="12"
        cy="12"
        r="9.4"
        fill="none"
        stroke="#d99e2b"
        strokeOpacity="0.5"
        strokeWidth="1.5"
      />
      <rect x="8.6" y="7.4" width="2.7" height="9.2" rx="1.1" fill="#d99e2b" />
      <rect
        x="12.7"
        y="7.4"
        width="2.7"
        height="9.2"
        rx="1.1"
        fill="#d99e2b"
        fillOpacity="0.6"
      />
    </svg>
  );
}

interface RecordGestureHintProps {
  /** Laufende Nummer des Hinweises — kein React-Schlüssel, der Knoten bleibt. */
  tipIdx: number;
  /** Übersetzter Hinweistext. */
  label: string;
}

/**
 * Halbtransparente Kopie des Aufnahmeknopfes samt Hinweiszeile. Wird innerhalb
 * von `.ps-record-stage` direkt nach dem Knopf gerendert.
 */
export function RecordGestureHint({ tipIdx, label }: RecordGestureHintProps) {
  const tip = gestureTipAt(tipIdx);
  return (
    <>
      <span
        data-testid="record-ghost"
        data-ps-gesture={tip.kind}
        aria-hidden="true"
        className={`ps-record-ghost ${tip.anim} ${RECORD_BUTTON_SHAPE}`}
      >
        <span className="ps-record-ghost-ring" />
        <GestureIcon kind={tip.kind} />
      </span>
      <div data-testid="record-tip" className="ps-record-tip">
        {label}
      </div>
    </>
  );
}
