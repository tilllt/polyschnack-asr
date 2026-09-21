/**
 * Change 216 (Nutzer-Vorgabe 20.09.2026) — Gestenhinweise am Aufnahmeknopf.
 *
 * Der Nutzer wollte die Hilfe NICHT als Block neben dem Knopf, sondern als
 * halbtransparente Kopie des Knopfes, die über dem echten Knopf liegt und die
 * Geste selbst vorführt: nach oben wischen, nach unten wischen, senken
 * (Halten), heben (Loslassen) — alles auf der Kreisform des Knopfes.
 *
 * Change 218/219 (20.09.2026) — Nachbesserungen: echter Kreis (keine Ellipse),
 * Deckkraft 0,85, Puls nur nach außen, EIN Aus- und EIN Einblenden je Hinweis,
 * längere Überblendzeiten (Change 221: 900 ms aus / 1100 ms ein).
 *
 * Change 222 (20.09.2026, drei Punkte): jeder Hinweis steht auf SEINER Seite
 * des Knopfes (wischen nach oben → oben, nach unten → unten, halten → links,
 * loslassen → rechts), die Textdrehung ist entfallen, und bei laufender
 * Aufnahme werden die Hinweise ausgeblendet (`verdeckt`).
 *
 * Change 223 (Nutzer-Vorgaben 20.09.2026, spät):
 *   1. „Die ui hints im record Menü sind immer noch sehr weit vom Button weg,
 *      auch hier 5px Entfernung." — Der Textkreis hat jetzt DENSELBEN Sitz wie
 *      die Beschriftung an den Kreisen der Zonen: Ringaußenkante + 5 px
 *      (genau: 4 px am 64-px-Knopf, 5 px am 80-px-Knopf, weil die
 *      Zeichenfläche prozentual mit dem Knopf wächst).
 *   2. „Entferne aus den overlay Animationen die Inhalte der Kreise, man
 *      versteht die Gesten auch ohne den Pfeil in der Mitte usw." — Das Zeichen
 *      IN der Kopie (Pfeil/Mikrofon/Pause-Balken) ist entfallen. Es bleibt die
 *      pulsierende Ring-Kopie des Knopfes; die Erklärung trägt allein der Text
 *      auf dem Kreis.
 *
 * Aufbau (Bauteile, die sich nicht beeinflussen können):
 *   .ps-record-stage  — Bezugsrahmen; genau so groß wie der Knopf, weil nur
 *                       der Knopf im Fluss liegt. Kopie und Hinweistext sind
 *                       absolut positioniert und damit nicht layoutwirksam.
 *   .ps-record-ghost  — Kopie in gleicher Größe und Form (inset: 0), Deckkraft
 *                       0,85, pointer-events: none (fängt keine Klicks ab).
 *   .ps-record-tip    — die Zeichenfläche des gebogenen Textes; MITTIG auf der
 *                       Knopfmitte (`left: 50%` + `top: 50%` + translate(-50%),
 *                       damit alle vier Seiten gleich weit reichen), Größe
 *                       PROZENTUAL zur Knopfgröße (218,75 % = 140/64, siehe
 *                       index.css), ebenfalls ohne Einfluss auf die Zonenhöhe.
 *
 * Der Textknoten trägt bewusst KEINEN key: beim Wechsel des Hinweises bleibt
 * derselbe DOM-Knoten bestehen (nur Inhalt und Pfad wechseln nach dem
 * Ausblenden). Dadurch kann nichts neu aufgebaut werden und nichts springen.
 */
import { useEffect, useRef, useState } from "react";

/** Größe und Form des Aufnahmeknopfes — gilt für Knopf UND Kopie. */
export const RECORD_BUTTON_SHAPE = "w-16 h-16 sm:w-20 sm:h-20 rounded-full";

/** Kennung des ersten SVG-Pfades; je Seite gibt es eine eigene (siehe unten). */
export const RECORD_ARC_PATH_ID = "ps-gesture-arc-path";

export type HintSide = "top" | "bottom" | "left" | "right";

/**
 * Maße des KREISES (px in der Zeichenfläche des SVG).
 *
 * Die Zahlen sind ABSICHTLICH dieselben wie bei den Kreisen in den Zonen
 * (SOURCE_CIRCLE_ARC in SourceCircle.tsx): 140 × 140 Zeichenfläche,
 * Mittelpunkt in der Mitte (70/70), r = 36, Schrift 10 px. Dadurch sitzt der
 * Hinweistext genauso nah am Knopf wie die Beschriftung „Upload"/„Download"
 * am Ring — Nutzer-Vorgabe 20.09.2026: „auch hier 5px Entfernung".
 *
 * Gerechnet (die Zeichenfläche wächst prozentual mit dem Knopf, ×1 am 64-px-
 * Knopf und ×1,25 am 80-px-Knopf):
 *   Knopfradius            32 / 40 px (halbe Knopfbreite, der Ring ist ein
 *                          `border` in border-box).
 *   Textkreis              36 × 1   = 36 px → 4 px Abstand zur Ringaußenkante
 *                          36 × 1,25 = 45 px → 5 px Abstand.
 *   Schrift                10 px bzw. 12,5 px.
 *   Bogenlänge             π × 36 ≈ 113 px (mobil) / 141 px (Desktop) — die
 *                          Halbkreise aller vier Seiten sind gleich lang.
 *   Tinte über der Mitte   r + Versalhöhe (7,2 px bei 10 px Schrift) = 43,2 px,
 *                          ab 640 px 54 px. Beides bleibt innerhalb der
 *                          Innenhalbhöhe der Zone (≥ 68 px) — nichts wird von
 *                          `overflow: hidden` abgeschnitten; nachgemessen im
 *                          Browser, siehe references/quellen-zeichen-kreise-zonen.md.
 * Die Maße sind in recordGestureHint.test.tsx gegen genau diese Grenzen
 * nachgerechnet; wer sie ändert, muss dort mitziehen.
 */
export const RECORD_ARC = {
  width: 140,
  height: 140,
  /** Kreismittelpunkt in der Zeichenfläche (= Knopfmitte). */
  cx: 70,
  cy: 70,
  /** EIN Radius für beide Achsen — ein echter Kreis, keine Ellipse. */
  r: 36,
  /** Schriftgröße des Hinweistextes in px. */
  fontSize: 10,
} as const;

export const RECORD_ARC_VIEWBOX = `0 0 ${RECORD_ARC.width} ${RECORD_ARC.height}`;

/**
 * Die Zeichenfläche wächst prozentual mit dem Knopf — dieselbe Prozentangabe
 * wie bei den Kreis-Beschriftungen in den Zonen (index.css, .ps-src-arc).
 * Werte: 218,75 % = 140/64. Damit gilt der Textabstand in beiden
 * Knopfgrößen (siehe RECORD_ARC).
 */
export const RECORD_ARC_SIZE_PERCENT = "218.75%";

/** Kennung des SVG-Pfades EINER Seite (je Seite eigener Pfad, sonst kollidieren sie). */
export function recordArcPathId(side: HintSide): string {
  return `${RECORD_ARC_PATH_ID}-${side}`;
}

/**
 * Radius des UNTEREN Bogens (Change 224, Nutzer: „Swipe down label that über den
 * Button."). Er ist größer als r, weil die Schrift auf dem Bogen mit ihrer
 * GRUNDLINIE aufliegt und sich quer zur Laufrichtung ausdehnt: beim unteren
 * Bogen zeigen die GROSSBUCHSTABEN zur Knopfmitte (beim oberen sind es die
 * Unterlängen, also nur „p" statt „S-D"). Mit demselben Radius saß „swipe down"
 * deshalb 3,2 px IM Ring — also optisch auf dem Knopf. Im Browser nachgemessen
 * und der Wert so gewählt, dass die Tinte unten genauso weit vom Ring weg liegt
 * wie oben (siehe recordGestureHint.test.tsx).
 *
 * `d` des Bogens für eine Seite: immer ein HALBKREIS, dessen Laufrichtung so
 * gewählt ist, dass die Schrift aufrecht bzw. mit dem Rücken nach außen steht
 * (Change 222):
 *   top     links → rechts über den Scheitel   (sweep 1, aufrecht)
 *   bottom  links → rechts unter dem Knopf     (sweep 0, aufrecht, Rücken zur
 *           Knopfmitte — wie eine Bildunterschrift); mit RECORD_ARC_BOTTOM_R
 *   left    unten → oben die linke Seite hoch  (sweep 1, Rücken nach links)
 *   right   oben → unten die rechte Seite ab   (sweep 1, Rücken nach rechts)
 */
export function recordArcPathD(side: HintSide): string {
  const { cx, cy, r } = RECORD_ARC;
  if (side === "bottom") {
    const R = RECORD_ARC_BOTTOM_R;
    return `M ${cx - R} ${cy} A ${R} ${R} 0 0 0 ${cx + R} ${cy}`;
  }
  if (side === "left") return `M ${cx} ${cy + r} A ${r} ${r} 0 0 1 ${cx} ${cy - r}`;
  if (side === "right") return `M ${cx} ${cy - r} A ${r} ${r} 0 0 1 ${cx} ${cy + r}`;
  return `M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`;
}

/** Radius des unteren Bogens — siehe recordArcPathD. */
export const RECORD_ARC_BOTTOM_R = 44;

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
 *
 * Change 223: Die Texte sind KURZ. Der Textkreis sitzt jetzt dicht am Knopf
 * (5 px), damit ist der Halbkreis nur noch ~113 px lang (mobil) — lange Sätze
 * wie „nach oben wischen: Aufnahme sperren" (35 Zeichen ≈ 190 px) passen darauf
 * nicht mehr und würden ineinander laufen. Die Kürzung ist die Folge der
 * Nutzer-Vorgabe, nicht eine eigene Geschmacksentscheidung.
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
 * Change 223: Die Kopie trägt KEIN Zeichen mehr (Nutzer: „Entferne aus den
 * overlay Animationen die Inhalte der Kreise, man versteht die Gesten auch ohne
 * den Pfeil in der Mitte"). Sichtbar sind nur der pulsierende Ring der Kopie
 * und der Text auf dem Kreis.
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
        {/* Change 223: NUR der Ring — das Zeichen in der Kopie ist entfallen. */}
        <span className="ps-record-ghost-ring" />
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
