/**
 * Change 216 (Nutzer-Vorgabe 20.09.2026) — Gestenhinweise am Aufnahmeknopf.
 *
 * Der Nutzer wollte die Hilfe NICHT als Block neben dem Knopf, sondern als
 * halbtransparente Kopie des Knopfes, die über dem echten Knopf liegt und die
 * Geste selbst vorführt: nach oben wischen, nach unten wischen, senken
 * (Halten), heben (Loslassen) — alles auf der Kreisform des Knopfes.
 *
 * Change 218/219 (Nutzer-Vorgaben 20.09.2026) — Nachbesserungen: echter Kreis
 * (r = 60 px, keine Ellipse), Deckkraft 0,85, Puls nur nach außen, EIN Aus-
 * und EIN Einblenden je Hinweis, längere Überblendzeiten (Change 221:
 * 900 ms aus / 1100 ms ein).
 *
 * Change 222 (Nutzer-Vorgabe 20.09.2026, drei Punkte):
 *   1. Jeder Hinweis steht auf SEINER Seite des Knopfes, passend zur Geste:
 *        nach oben wischen   → oben    (top)
 *        nach unten wischen  → unten   (bottom)
 *        halten: aufnehmen   → links   (left)
 *        loslassen: Pause    → rechts  (right)
 *      Dazu ist die Zeichenfläche quadratisch (240 × 240) und der
 *      Kreismittelpunkt liegt in ihrer Mitte (cx = cy = 120) — der Text sitzt
 *      damit in jeder der vier Lagen gleich weit vom Knopf und wird nie
 *      abgeschnitten: der Kreisbogen ist in allen Lagen ein Halbkreis
 *      (π × 60 ≈ 188 px) und der Text läuft nach außen lesbar (oben und unten
 *      aufrecht, links von unten nach oben, rechts von oben nach unten — die
 *      Buchstabenrücken zeigen immer nach außen).
 *   2. Die Drehung des Hinweistextes ist ENTFALLEN („Generell lassen wir die
 *      Animation der Texte sein, die ist zu unruhig"). Der Text steht still;
 *      es gibt keine Drehklasse mehr.
 *   3. Bei laufender Aufnahme — gleich ob per Klick oder per Wisch-Sperre —
 *      werden die Hinweise ausgeblendet (`verdeckt`): sie erklären dann eine
 *      Geste, die gerade nicht zur Wahl steht. Das Ausblenden nutzt dieselbe
 *      Klasse wie der Hinweiswechsel (.ps-record-hint-out) und pausiert
 *      zugleich die Puls-Bewegung.
 *
 * Aufbau (Bauteile, die sich nicht beeinflussen können):
 *   .ps-record-stage  — Bezugsrahmen; genau so groß wie der Knopf, weil nur
 *                       der Knopf im Fluss liegt. Kopie und Hinweiskreis sind
 *                       absolut positioniert und damit nicht layoutwirksam.
 *   .ps-record-ghost  — Kopie in gleicher Größe und Form (inset: 0), Deckkraft
 *                       0,85, pointer-events: none (fängt keine Klicks ab).
 *   .ps-record-tip    — die Zeichenfläche des gebogenen Textes; MITTIG auf der
 *                       Knopfmitte (`left: 50%` + `top: 50%` + translate(-50%),
 *                       damit alle vier Seiten gleich weit reichen), feste
 *                       Maße, ebenfalls ohne Einfluss auf die Zonenhöhe.
 *
 * Der Textknoten trägt bewusst KEINEN key: beim Wechsel des Hinweises bleibt
 * derselbe DOM-Knoten bestehen (nur Inhalt und Pfad wechseln nach dem
 * Ausblenden). Dadurch kann nichts neu aufgebaut werden und nichts springen.
 */
import { useEffect, useRef, useState, type ReactNode } from "react";

/** Größe und Form des Aufnahmeknopfes — gilt für Knopf UND Kopie. */
export const RECORD_BUTTON_SHAPE = "w-16 h-16 sm:w-20 sm:h-20 rounded-full";

/** Kennung des ersten SVG-Pfades; je Seite gibt es eine eigene (siehe unten). */
export const RECORD_ARC_PATH_ID = "ps-gesture-arc-path";

export type HintSide = "top" | "bottom" | "left" | "right";

/**
 * Maße des KREISES (px in der Zeichenfläche des SVG).
 *
 * Der Knopf ist 64 px (ab 640 px: 80 px) breit, sein Mittelpunkt liegt exakt
 * in der Mitte der Zeichenfläche (`left/top: 50%` in .ps-record-tip). Damit gilt
 * für alle drei Breakpoint-Stufen:
 *   Knopfradius            32 / 40 px. Der Kreis liegt mit r = 60 px außen vor
 *                          dem Rand (kleinster Abstand 20 px).
 *   Kopie nach außen       1,22 × 40 = 48,8 px < 60 px — die pulsierende Kopie
 *                          bleibt immer INNERHALB des Textkreises; mit
 *                          1,35 × 40 = 54 px auch der Ring. Der Text kann
 *                          deshalb zu keinem Zeitpunkt von der Kopie überdeckt
 *                          werden.
 *   Zeichenfläche          240 × 240 px, Kreismittelpunkt in der Mitte
 *                          (120/120). Der Textkasten ragt deshalb in jeder
 *                          Richtung 120 px über den Knopfmittelpunkt hinaus;
 *                          sichtbar ist davon nur, was unter der Schnittkante
 *                          von `overflow: hidden` liegt (Change 222:
 *                          Schriftkante 60 + 7,2 = 67,2 px vom Mittelpunkt,
 *                          Innenhalbhöhe der Zone ≥ 68 px — die Zone ist
 *                          entsprechend bemessen, siehe --ps-zone-h).
 *   Breite 240 px           Kreis also ±60 px um die Knopfmitte; auf dem
 *                          schmalsten Handy (320 px Fenster) bleiben ±134 px.
 *                          Kein Überlaufen.
 *   Länge des Halbkreises   π × 60 ≈ 188 px. Der längste Hinweis („nach oben
 *                          wischen: Aufnahme sperren", 35 Zeichen bei 9 px)
 *                          braucht rund 167 px — der Text wird also nicht
 *                          abgeschnitten (13 % Luft) und die Buchstaben laufen
 *                          nicht ineinander. Grund: der längste Hinweis steht
 *                          auf dem oberen Halbkreis, nicht auf dem breiteren
 *                          Halbkreis links/rechts; alle vier Halbkreise sind
 *                          gleich lang.
 * Die Maße sind in recordGestureHint.test.tsx gegen genau diese Grenzen
 * nachgerechnet; wer sie ändert, muss dort mitziehen.
 */
export const RECORD_ARC = {
  width: 240,
  height: 240,
  /** Kreismittelpunkt in der Zeichenfläche (= Knopfmitte). */
  cx: 120,
  cy: 120,
  /** EIN Radius für beide Achsen — ein echter Kreis, keine Ellipse. */
  r: 60,
  /** Schriftgröße des Hinweistextes in px. */
  fontSize: 9,
} as const;

export const RECORD_ARC_VIEWBOX = `0 0 ${RECORD_ARC.width} ${RECORD_ARC.height}`;

/** Kennung des SVG-Pfades EINER Seite (je Seite eigener Pfad, sonst kollidieren sie). */
export function recordArcPathId(side: HintSide): string {
  return `${RECORD_ARC_PATH_ID}-${side}`;
}

/**
 * `d` des Bogens für eine Seite: immer ein HALBKREIS mit dem Radius r, dessen
 * Laufrichtung so gewählt ist, dass die Schrift aufrecht bzw. mit dem Rücken
 * nach außen steht (Change 222):
 *   top     links → rechts über den Scheitel   (sweep 1, aufrecht)
 *   bottom  links → rechts unter dem Knopf     (sweep 0, aufrecht, Rücken zur
 *           Knopfmitte — wie eine Bildunterschrift)
 *   left    unten → oben die linke Seite hoch  (sweep 1, Rücken nach links)
 *   right   oben → unten die rechte Seite ab   (sweep 1, Rücken nach rechts)
 * Beide Radien sind gleich — das ist der Kreis.
 */
export function recordArcPathD(side: HintSide): string {
  const { cx, cy, r } = RECORD_ARC;
  if (side === "bottom") return `M ${cx - r} ${cy} A ${r} ${r} 0 0 0 ${cx + r} ${cy}`;
  if (side === "left") return `M ${cx} ${cy + r} A ${r} ${r} 0 0 1 ${cx} ${cy - r}`;
  if (side === "right") return `M ${cx} ${cy - r} A ${r} ${r} 0 0 1 ${cx} ${cy + r}`;
  return `M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`;
}

/** Rückwärtskompatibler Name des oberen Bogens (Change 219). */
export const RECORD_ARC_PATH_D = recordArcPathD("top");

/**
 * Wechsel der Hinweise (Change 219, Punkt 6): Ausblenden dauert
 * TIP_FADE_OUT_MS, danach wechseln Text und Geste gemeinsam und blenden
 * TIP_FADE_IN_MS ein. Beide Werte stehen genauso in src/index.css — alt waren
 * 180 ms / 220 ms, dann 360 ms / 440 ms; auf Nutzerwunsch (20.09.2026:
 * „Fade out / fade in ist immer noch viel zu schnell") jetzt 900 ms / 1100 ms.
 * Hintergrund: der Hinweiswechsel soll ruhig wirken — kürzer wirkt wie ein
 * Zucken, und der Nutzer sieht den Wechsel der Geste nicht.
 */
export const TIP_FADE_OUT_MS = 900;
export const TIP_FADE_IN_MS = 1100;

export type GestureKind = "lock" | "stop" | "hold" | "release";

export interface GestureTip {
  kind: GestureKind;
  /** Schlüssel im Textkatalog (src/useLocale.ts). */
  key: string;
  /** Klasse, die die Bewegung der Kopie steuert (src/index.css). */
  anim: string;
  /** Seite des Knopfes, auf der die Erklärung steht (Change 222). */
  side: HintSide;
}

/**
 * Die vier Hinweise in der Reihenfolge, in der sie gezeigt werden. Die Seite
 * folgt der Geste: wischen nach oben → oben, nach unten → unten, halten →
 * links, loslassen → rechts (Change 222).
 */
export const RECORD_GESTURE_TIPS: readonly GestureTip[] = [
  { kind: "lock", key: "gesture_lock_up", anim: "ps-ghost-lock", side: "top" },
  { kind: "stop", key: "gesture_stop_down", anim: "ps-ghost-stop", side: "bottom" },
  { kind: "hold", key: "gesture_hold", anim: "ps-ghost-sink", side: "left" },
  { kind: "release", key: "gesture_release_pause", anim: "ps-ghost-rise", side: "right" },
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
  /**
   * Läuft gerade eine Aufnahme? Dann werden die Hinweise ausgeblendet
   * (Change 222, Nutzer-Vorgabe 20.09.2026 — gilt für Klick- UND Wischstart).
   */
  verdeckt?: boolean;
}

/** Der Hinweis, der gerade auf dem Kreis steht (Nummer + Text gehören zusammen). */
interface GezeigtHint {
  idx: number;
  label: string;
}

type HintPhase = "in" | "out";

/**
 * Halbtransparente Kopie des Aufnahmeknopfes samt Hinweistext auf einem Kreis.
 * Wird innerhalb von `.ps-record-stage` direkt nach dem Knopf gerendert.
 *
 * Ein Hinweiswechsel ist GENAU EIN Ablauf (Change 219, Punkt 2):
 *   1. Phase `out` — Kopie und Text blenden zusammen aus (TIP_FADE_OUT_MS),
 *      die Geste bleibt dabei unverändert (die Kopie bewegt sich nie, während
 *      man sie sieht — genau das war das doppelte Aufblenden).
 *   2. Text UND Geste wechseln gemeinsam, Phase `in` — beide blenden zusammen
 *      wieder ein (TIP_FADE_IN_MS), die neue Bewegung setzt erst hier ein.
 * Ein laufender Ablauf wird nicht neu aufgesetzt: Ändert sich der Hinweis
 * während des Ausblendens, nimmt der laufende Ablauf den neuesten Text mit —
 * es entsteht trotzdem nur ein Aus- und ein Einblenden.
 * Bei reduzierter Bewegung entfällt beides — dann steht der neue Text sofort da.
 *
 * `verdeckt` (Change 222) legt dieselbe Ausblendung über alles: während einer
 * Aufnahme steht die Kopie still (die Puls-Bewegung ist pausiert) und ist
 * unsichtbar.
 */
export function RecordGestureHint({ tipIdx, label, verdeckt = false }: RecordGestureHintProps) {
  /** Was wirklich auf dem Kreis steht — hinkt dem neuen Hinweis um das Ausblenden nach. */
  const [gezeigt, setGezeigt] = useState<GezeigtHint>(() => ({ idx: tipIdx, label }));
  const [phase, setPhase] = useState<HintPhase>("in");
  /** Der neueste Wunsch des Aufrufers — wird beim Wechsel übernommen. */
  const ziel = useRef<GezeigtHint>({ idx: tipIdx, label });
  /** Der EINE laufende Zeitgeber des Ausblendens. */
  const uhr = useRef<number | null>(null);

  useEffect(() => {
    ziel.current = { idx: tipIdx, label };
    if (verdeckt) return; // Verdeckt: kein Wechsel, kein Überblenden, kein Zeitgeber.
    if (tipIdx === gezeigt.idx && label === gezeigt.label) return;

    if (reduzierteBewegung()) {
      // Kein Überblenden: sofortiger Wechsel (Standbild).
      if (uhr.current !== null) {
        window.clearTimeout(uhr.current);
        uhr.current = null;
      }
      setGezeigt({ idx: tipIdx, label });
      setPhase("in");
      return;
    }

    // Läuft schon ein Ausblenden? Dann KEIN zweiter Ablauf — der laufende
    // nimmt den hier gesetzten Zielhinweis mit.
    if (uhr.current !== null) return;

    setPhase("out");
    uhr.current = window.setTimeout(() => {
      uhr.current = null;
      setGezeigt(ziel.current);
      setPhase("in");
    }, TIP_FADE_OUT_MS);
  }, [tipIdx, label, verdeckt, gezeigt]);

  // Kein Zeitgeber über die Lebensdauer des Knotens hinaus.
  useEffect(
    () => () => {
      if (uhr.current !== null) window.clearTimeout(uhr.current);
    },
    []
  );

  const tip = gestureTipAt(gezeigt.idx);
  const pfadId = recordArcPathId(tip.side);
  const ausblenden = phase === "out" || verdeckt ? " ps-record-hint-out" : "";
  const sichtbar = phase === "in" && !verdeckt ? "1" : "0";

  return (
    <>
      <span
        data-testid="record-ghost"
        data-ps-gesture={tip.kind}
        data-ps-hint-side={tip.side}
        data-ps-hint-visible={sichtbar}
        data-ps-hint-phase={phase}
        aria-hidden="true"
        className={`ps-record-ghost ${tip.anim}${ausblenden} ${RECORD_BUTTON_SHAPE}`}
      >
        <span className="ps-record-ghost-ring" />
        <GestureIcon kind={tip.kind} />
      </span>
      <div
        data-testid="record-tip"
        data-ps-hint-side={tip.side}
        data-ps-hint-visible={sichtbar}
        data-ps-hint-phase={phase}
        className={`ps-record-tip${ausblenden}`}
      >
        {/* Der Hinweis läuft als gebogener Text auf einem KREIS um den Knopf
            (Bauart wie im css-tricks-Rezept „curved text along path"):
            <defs><path id=…></defs>, dann <text><textPath href=…>.
            text-anchor: middle + startOffset 50% setzen den Text mittig auf den
            Scheitel SEINER Seite (Change 222: top/bottom/left/right, siehe
            recordArcPathD). Der Text steht still — keine Drehung mehr. */}
        <svg
          className="ps-record-arc"
          viewBox={RECORD_ARC_VIEWBOX}
          width={RECORD_ARC.width}
          height={RECORD_ARC.height}
          focusable="false"
        >
          <defs>
            <path id={pfadId} d={recordArcPathD(tip.side)} />
          </defs>
          <text className="ps-record-arc-text" textAnchor="middle">
            {/* Beide Schreibweisen: `href` ist die aktuelle (SVG 2), `xlinkHref`
                die alte Fassung. Browser, die `href` an textPath nicht kennen
                (ältere Safari-Fassungen), zeichnen sonst still gar keinen Text. */}
            <textPath href={`#${pfadId}`} xlinkHref={`#${pfadId}`} startOffset="50%">
              {gezeigt.label}
            </textPath>
          </text>
        </svg>
      </div>
    </>
  );
}
