/**
 * Change 216 (Nutzer-Vorgabe 20.09.2026) — Gestenhinweise am Aufnahmeknopf.
 *
 * Der Nutzer wollte die Hilfe NICHT als Block neben dem Knopf (genau das war
 * die frühere, ausdrücklich verworfene Lösung), sondern als halbtransparente
 * Kopie des Knopfes, die über dem echten Knopf liegt und die Geste selbst
 * vorführt: nach oben wischen, nach unten wischen, senken (Halten), heben
 * (Loslassen) — alles auf der Kreisform des Knopfes.
 *
 * Change 218 (Nutzer-Vorgabe 20.09.2026) — vier Nachbesserungen, Bauart
 * unverändert (Knopf bleibt mittig und unbewegt, Kopie in Knopfgröße darüber,
 * immer `pointer-events: none`):
 *   1. Deckkraft der Kopie 0,55 → 0,85 (in src/index.css): deutlich sichtbar,
 *      der echte Knopf bleibt durch die schwache Flächenfüllung hindurch
 *      erkennbar. Die Hinweisfarbe steckt im Rand und im Symbol, die Fläche ist
 *      nur ein Hauch — deshalb sind Knopf und Kopie farblich unterscheidbar.
 *   2. Weg beim Wischen größer (src/index.css): hoch 12 → 26 px, runter 4 → 18 px,
 *      Senken 0,86 → 0,72, Heben 1,06 → 1,12. Die Grenzen sind gerechnet, nicht
 *      geschätzt — siehe den Kommentar am Bogenmaß unten.
 *   3. Der Hinweistext läuft nicht mehr gerade, sondern als gebogener Text auf
 *      einem SVG-Pfad um den Knopf (<defs><path id=…></defs> +
 *      <text><textPath href="#…">) — wie im css-tricks-Rezept „curved text
 *      along path". Der Bogen ist ein Ellipsenbogen über dem Knopf; seine Maße
 *      stehen in RECORD_ARC und sind gegen die feste Zonenhöhe gerechnet.
 *   4. Beim Wechsel blendet der alte Hinweis aus und der neue ein (weiches
 *      Überblenden, kein hartes Umschalten). Bei `prefers-reduced-motion`
 *      entfällt das Überblenden — dann wechselt der Text sofort.
 *
 * Aufbau (Bauteile, die sich nicht beeinflussen können):
 *   .ps-record-stage  — Bezugsrahmen; genau so groß wie der Knopf, weil nur
 *                       der Knopf im Fluss liegt. Kopie und Hinweisbogen sind
 *                       absolut positioniert und damit nicht layoutwirksam.
 *   .ps-record-ghost  — Kopie in gleicher Größe und Form (inset: 0), Deckkraft
 *                       0,85, pointer-events: none (fängt keine Klicks ab).
 *   .ps-record-tip    — der gebogene Text; untere Kante auf Knopfmitte
 *                       (`bottom: 50%`), Breite/Höhe fest, ebenfalls ohne
 *                       Einfluss auf die Zonenhöhe.
 *
 * Der Textknoten trägt bewusst KEINEN key: beim Wechsel des Hinweises bleibt
 * derselbe DOM-Knoten bestehen (nur der Inhalt wechselt nach dem Ausblenden).
 * Dadurch kann nichts neu aufgebaut werden und nichts springen.
 */
import { useEffect, useState, type ReactNode } from "react";

/** Größe und Form des Aufnahmeknopfes — gilt für Knopf UND Kopie. */
export const RECORD_BUTTON_SHAPE = "w-16 h-16 sm:w-20 sm:h-20 rounded-full";

/** Kennung des SVG-Pfades, auf dem der Hinweistext läuft. */
export const RECORD_ARC_PATH_ID = "ps-gesture-arc-path";

/**
 * Maße des Bogens (px in der Zeichenfläche des SVG).
 *
 * Der Knopf ist 64 px (ab 640 px: 80 px) breit, sein Mittelpunkt liegt auf der
 * unteren Kante der Zeichenfläche (`bottom: 50%` in .ps-record-tip). Damit gilt
 * für alle drei Breakpoint-Stufen:
 *   Knopfradius           32 / 40 px  → der Bogen liegt mit ry = 52 px außen
 *                                        vor dem Rand (kleinster Abstand 12 px
 *                                        ab 640 px, 20 px auf dem Handy).
 *   Höhe der Zone         144/160/174 px, Innenabstand 12 px, Rand 2 px
 *                         → nutzbar über der Knopfmitte sind 58/66/73 px
 *                         (Schnittkante 70/78/85 px). Der Bogen steigt
 *                         ry + Versalhöhe = 52 + 8 = 60 px hoch: keine
 *                         Abschneidung, kein Überlappen des Zonenrandes.
 *   Breite der Zone       ±113 px ab Knopfmitte (halbe Sehne 105 px + Schrift)
 *                         → auf dem schmalsten Handy (320 px Fenster) bleiben
 *                         ±134 px. Kein Überlaufen.
 *   Länge des Bogens      216 px. Der längste Hinweis („nach oben wischen:
 *                         Aufnahme sperren", 35 Zeichen bei 10 px) braucht rund
 *                         185 px — der Text wird also nicht abgeschnitten.
 * Die Maße sind in recordGestureHint.test.tsx gegen genau diese Grenzen
 * nachgerechnet; wer sie ändert, muss dort mitziehen.
 */
export const RECORD_ARC = {
  width: 240,
  height: 64,
  /** Knopfmittelpunkt in der Zeichenfläche (untere Kante). */
  cx: 120,
  cy: 64,
  rx: 130,
  ry: 52,
  /** Halbe Breite des Bogens links und rechts der Knopfmitte. */
  halfChord: 105,
  /** Schriftgröße des Hinweistextes in px. */
  fontSize: 10,
} as const;

export const RECORD_ARC_VIEWBOX = `0 0 ${RECORD_ARC.width} ${RECORD_ARC.height}`;

/** Höhe der beiden Bogenenden — aus der Ellipse gerechnet, nicht geschätzt. */
const ARC_Y_END =
  Math.round(
    (RECORD_ARC.cy -
      RECORD_ARC.ry * Math.sin(Math.acos(RECORD_ARC.halfChord / RECORD_ARC.rx))) *
      100
  ) / 100;

/**
 * `d` des Bogens: Ellipsenbogen von links nach rechts über den Knopf
 * (sweep-flag 1 = im Uhrzeigersinn, also über die obere Hälfte).
 */
export const RECORD_ARC_PATH_D =
  `M ${RECORD_ARC.cx - RECORD_ARC.halfChord} ${ARC_Y_END} ` +
  `A ${RECORD_ARC.rx} ${RECORD_ARC.ry} 0 0 1 ${RECORD_ARC.cx + RECORD_ARC.halfChord} ${ARC_Y_END}`;

/** Dauer des Ausblendens vor dem Wechsel; das Einblenden dauert 220 ms (CSS). */
export const TIP_FADE_OUT_MS = 180;

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
 * Hat der Nutzer reduzierte Bewegung angefordert? Ohne matchMedia (jsdom, alte
 * Browser) gilt „nein" — dann läuft das Überblenden. Dieselbe Regel wie in
 * WaveformPlayer.tsx (reduceMotionRequested), hier bewusst als kleine eigene
 * Funktion, damit dieses Bauteil nicht den ganzen Player mitlädt.
 */
export function reduzierteBewegung(): boolean {
  try {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches === true;
  } catch {
    return false;
  }
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
 * Halbtransparente Kopie des Aufnahmeknopfes samt gebogenem Hinweistext. Wird
 * innerhalb von `.ps-record-stage` direkt nach dem Knopf gerendert.
 *
 * Der Wechsel läuft in zwei Schritten: erst blendet der alte Hinweis aus
 * (Klasse `ps-record-hint-out`, Dauer TIP_FADE_OUT_MS), dann wechselt der Text
 * und der neue Hinweis blendet ein. Bei reduzierter Bewegung entfällt das —
 * dann steht der neue Text sofort da.
 */
export function RecordGestureHint({ tipIdx, label }: RecordGestureHintProps) {
  const tip = gestureTipAt(tipIdx);
  /** Der gerade sichtbare Text — hinkt dem neuen Hinweis um das Ausblenden nach. */
  const [sichtbar, setSichtbar] = useState(label);
  const [eingeblendet, setEingeblendet] = useState(true);

  useEffect(() => {
    if (label === sichtbar) return;
    if (reduzierteBewegung()) {
      // Kein Überblenden: sofortiger Wechsel (Standbild).
      setSichtbar(label);
      setEingeblendet(true);
      return;
    }
    setEingeblendet(false);
    const id = window.setTimeout(() => {
      setSichtbar(label);
      setEingeblendet(true);
    }, TIP_FADE_OUT_MS);
    return () => window.clearTimeout(id);
  }, [label, sichtbar]);

  const ausblenden = eingeblendet ? "" : " ps-record-hint-out";

  return (
    <>
      <span
        data-testid="record-ghost"
        data-ps-gesture={tip.kind}
        data-ps-hint-visible={eingeblendet ? "1" : "0"}
        aria-hidden="true"
        className={`ps-record-ghost ${tip.anim}${ausblenden} ${RECORD_BUTTON_SHAPE}`}
      >
        <span className="ps-record-ghost-ring" />
        <GestureIcon kind={tip.kind} />
      </span>
      <div
        data-testid="record-tip"
        data-ps-hint-visible={eingeblendet ? "1" : "0"}
        className={`ps-record-tip${ausblenden}`}
      >
        {/* Der Hinweis läuft als gebogener Text auf einem Kreisbogen um den
            Knopf (Bauart wie im css-tricks-Rezept „curved text along path"):
            <defs><path id=…></defs>, dann <text><textPath href="#…">.
            text-anchor: middle + startOffset 50% setzen den Text mittig auf
            den Bogen; er bleibt in beiden Wischrichtungen gleich lesbar. */}
        <svg
          className="ps-record-arc"
          viewBox={RECORD_ARC_VIEWBOX}
          width={RECORD_ARC.width}
          height={RECORD_ARC.height}
          focusable="false"
        >
          <defs>
            <path id={RECORD_ARC_PATH_ID} d={RECORD_ARC_PATH_D} />
          </defs>
          <text className="ps-record-arc-text" textAnchor="middle">
            {/* Beide Schreibweisen: `href` ist die aktuelle (SVG 2), `xlinkHref`
                die alte Fassung. Browser, die `href` an textPath nicht kennen
                (ältere Safari-Fassungen), zeichnen sonst still gar keinen Text. */}
            <textPath
              href={`#${RECORD_ARC_PATH_ID}`}
              xlinkHref={`#${RECORD_ARC_PATH_ID}`}
              startOffset="50%"
            >
              {sichtbar}
            </textPath>
          </text>
        </svg>
      </div>
    </>
  );
}
