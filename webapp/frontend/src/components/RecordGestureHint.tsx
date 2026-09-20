/**
 * Change 216 (Nutzer-Vorgabe 20.09.2026) — Gestenhinweise am Aufnahmeknopf.
 *
 * Der Nutzer wollte die Hilfe NICHT als Block neben dem Knopf (genau das war
 * die frühere, ausdrücklich verworfene Lösung), sondern als halbtransparente
 * Kopie des Knopfes, die über dem echten Knopf liegt und die Geste selbst
 * vorführt: nach oben wischen, nach unten wischen, senken (Halten), heben
 * (Loslassen) — alles auf der Kreisform des Knopfes.
 *
 * Change 218 (Nutzer-Vorgabe 20.09.2026) — vier Nachbesserungen: Deckkraft der
 * Kopie 0,85, größerer Weg, gebogener Hinweistext, weiches Überblenden.
 *
 * Change 219 (Nutzer-Vorgabe 20.09.2026, sechs Punkte) — Nachbesserung dieser
 * Nachbesserung. Der Nutzer hat die ELLIPSE ausdrücklich abgelehnt:
 *   1. ECHTER KREIS statt Ellipse: RECORD_ARC hat nur noch EINEN Radius
 *      (r = 60 px), das `d`-Attribut trägt ihn in beiden Achsen
 *      (`A 60 60 …`). Der Kreis läuft außen um den Knopf herum — der Knopf
 *      selbst bleibt mittig und unbewegt, die ZONE behält ihre feste Höhe
 *      (Regel aus Change 215), weil der Hinweiskasten absolut positioniert
 *      ist und nicht am Layout teilnimmt.
 *      Schriftgröße 10 → 9 px: der längste Hinweis („nach oben wischen:
 *      Aufnahme sperren", 35 Zeichen) braucht bei 9 px rund 167 px; der
 *      Halbkreis über dem Knopf ist π × 60 ≈ 188 px lang. Damit ist kein
 *      Buchstabe abgeschnitten und die Buchstaben laufen nicht ineinander.
 *   2. Pro Hinweis GENAU EIN Aus- und EIN Einblenden. Ursache des doppelten
 *      Aufblendens war die getrennte Steuerung: Die Geste (CSS-Klasse der
 *      Kopie) wechselte SOFORT beim neuen Hinweis und startete damit die
 *      CSS-Animation der sichtbaren Kopie neu (sichtbarer Sprung = erstes
 *      Aufblenden), während der Text erst nach dem Ausblenden umsprang
 *      (zweites Aufblenden). Außerdem wurde das Ausblenden bei jedem
 *      Effekt-Lauf über die zweite Abhängigkeit (`sichtbar`) neu angestoßen.
 *      Jetzt gibt es EINEN Ablauf mit EINEM Zeitgeber (useRef, kein
 *      Neuaufsetzen): Phase `out` → Text UND Geste wechseln gemeinsam →
 *      Phase `in`. Die Kopie bewegt sich nie mehr, während sie sichtbar ist.
 *   3. Der Hinweistext dreht langsam um den Knopf: die SVG-Gruppe
 *      `<g class="ps-record-arc-spin">` rotiert per CSS um den Kreismittelpunkt
 *      (transform-box: view-box; transform-origin = 120px 68px = cx/cy),
 *      30 s je Umdrehung, linear — ruhig, ohne Flackern. Bei
 *      `prefers-reduced-motion: reduce` steht sie still.
 *   4. Alle vier Hinweise sind gleich sichtbar: Farbe, Deckkraft und
 *      Schriftgröße des Textes stehen genau EINMAL in `.ps-record-arc-text`
 *      (Farbe aus `--ps-hint-ink`), keine Gestenklasse übersteuert sie. Der
 *      gefühlte Unterschied bei „halten: aufnehmen" kam von der Kopie: sie
 *      pulsierte als einzige nach INNEN (scale 0,72) und zog sich damit genau
 *      dort zurück, wo der Text steht. Jetzt pulsiert jede Kopie nach außen.
 *   5. Der Puls geht NUR nach außen: kein `scale` unter 1 mehr (senken
 *      1 → 1,16, heben 1 → 1,22, Ring 1 → 1,35). Hoch/runter bleiben
 *      unverändert bei 26 px / 18 px.
 *   6. Längere Ein-/Ausblendzeiten: aus 180 → 360 ms, ein 220 → 440 ms,
 *      Verhältnis unverändert weich (ease-in / ease-out). Bei
 *      `prefers-reduced-motion` nach wie vor ohne Übergang.
 *
 * Aufbau (Bauteile, die sich nicht beeinflussen können):
 *   .ps-record-stage  — Bezugsrahmen; genau so groß wie der Knopf, weil nur
 *                       der Knopf im Fluss liegt. Kopie und Hinweiskreis sind
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
import { useEffect, useRef, useState, type ReactNode } from "react";

/** Größe und Form des Aufnahmeknopfes — gilt für Knopf UND Kopie. */
export const RECORD_BUTTON_SHAPE = "w-16 h-16 sm:w-20 sm:h-20 rounded-full";

/** Kennung des SVG-Pfades, auf dem der Hinweistext läuft. */
export const RECORD_ARC_PATH_ID = "ps-gesture-arc-path";

/** Klasse der SVG-Gruppe, die den Text langsam um den Knopf dreht. */
export const RECORD_ARC_SPIN_CLASS = "ps-record-arc-spin";

/**
 * Maße des KREISES (px in der Zeichenfläche des SVG).
 *
 * Der Knopf ist 64 px (ab 640 px: 80 px) breit, sein Mittelpunkt liegt auf der
 * unteren Kante der Zeichenfläche (`bottom: 50%` in .ps-record-tip). Damit gilt
 * für alle drei Breakpoint-Stufen:
 *   Knopfradius            32 / 40 px. Der Kreis liegt mit r = 60 px außen
 *                          vor dem Rand (kleinster Abstand 20 px).
 *   Kopie nach außen       1,22 × 40 = 48,8 px < 60 px — die pulsierende Kopie
 *                          bleibt immer INNERHALB des Textkreises. Der Text
 *                          kann deshalb zu keinem Zeitpunkt von der Kopie
 *                          überdeckt werden.
 *   Höhe der Zeichenfläche 68 px = r + Versalhöhe (60 + 7,2). Die Zone ist
 *                          144/160/174 px hoch, Innenabstand 12 px, Rand 2 px
 *                          → die Schnittkante von `overflow: hidden` liegt
 *                          72/80/87 px über der Knopfmitte. Der höchste Punkt
 *                          des Textes (60 + 7,2 = 67,2 px) bleibt darunter,
 *                          also wird nichts abgeschnitten — auch nicht, wenn
 *                          der Text beim Drehen unter den Knopf wandert.
 *   Breite der Zeichenfläche 240 px, Kreis also ±60 px um die Knopfmitte; auf
 *                          dem schmalsten Handy (320 px Fenster) bleiben
 *                          ±134 px. Kein Überlaufen.
 *   Länge des Halbkreises  π × 60 ≈ 188 px. Der längste Hinweis („nach oben
 *                          wischen: Aufnahme sperren", 35 Zeichen bei 9 px)
 *                          braucht rund 167 px — der Text wird also nicht
 *                          abgeschnitten (13 % Luft) und die Buchstaben laufen
 *                          nicht ineinander.
 * Die Maße sind in recordGestureHint.test.tsx gegen genau diese Grenzen
 * nachgerechnet; wer sie ändert, muss dort mitziehen.
 */
export const RECORD_ARC = {
  width: 240,
  height: 68,
  /** Kreismittelpunkt in der Zeichenfläche (untere Kante = Knopfmitte). */
  cx: 120,
  cy: 68,
  /** EIN Radius für beide Achsen — ein echter Kreis, keine Ellipse. */
  r: 60,
  /** Schriftgröße des Hinweistextes in px. */
  fontSize: 9,
} as const;

export const RECORD_ARC_VIEWBOX = `0 0 ${RECORD_ARC.width} ${RECORD_ARC.height}`;

/**
 * `d` des Bogens: Halbkreis von links nach rechts über den Knopf
 * (sweep-flag 1 = im Uhrzeigersinn, also über die obere Hälfte).
 * Beide Radien sind gleich — das ist der Kreis.
 */
export const RECORD_ARC_PATH_D =
  `M ${RECORD_ARC.cx - RECORD_ARC.r} ${RECORD_ARC.cy} ` +
  `A ${RECORD_ARC.r} ${RECORD_ARC.r} 0 0 1 ${RECORD_ARC.cx + RECORD_ARC.r} ${RECORD_ARC.cy}`;

/**
 * Wechsel der Hinweise (Change 219, Punkt 6): Ausblenden dauert
 * TIP_FADE_OUT_MS, danach wechseln Text und Geste gemeinsam und blenden
 * TIP_FADE_IN_MS ein. Beide Werte stehen genauso in src/index.css — alt waren
 * 180 ms / 220 ms, dann 360 ms / 440 ms; auf Nutzerwunsch (20.09.2026:
 * „Fade out / fade in ist immer noch viel zu schnell") jetzt 900 ms / 1100 ms.
 * Hintergrund: Der Hinweis läuft 30 s je Umdrehung um den Knopf — ein
 * Überblenden von einer knappen Sekunde passt zu dieser Ruhe. Kürzer wirkt
 * wie ein Zucken, und der Nutzer sieht den Wechsel der Geste nicht.
 */
export const TIP_FADE_OUT_MS = 900;
export const TIP_FADE_IN_MS = 1100;

/** Dauer einer vollen Umdrehung des Textes um den Knopf (langsam). */
export const RECORD_ARC_SPIN_MS = 30000;

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
 */
export function RecordGestureHint({ tipIdx, label }: RecordGestureHintProps) {
  /** Was wirklich auf dem Kreis steht — hinkt dem neuen Hinweis um das Ausblenden nach. */
  const [gezeigt, setGezeigt] = useState<GezeigtHint>(() => ({ idx: tipIdx, label }));
  const [phase, setPhase] = useState<HintPhase>("in");
  /** Der neueste Wunsch des Aufrufers — wird beim Wechsel übernommen. */
  const ziel = useRef<GezeigtHint>({ idx: tipIdx, label });
  /** Der EINE laufende Zeitgeber des Ausblendens. */
  const uhr = useRef<number | null>(null);

  useEffect(() => {
    ziel.current = { idx: tipIdx, label };
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
  }, [tipIdx, label, gezeigt]);

  // Kein Zeitgeber über die Lebensdauer des Knotens hinaus.
  useEffect(
    () => () => {
      if (uhr.current !== null) window.clearTimeout(uhr.current);
    },
    []
  );

  const tip = gestureTipAt(gezeigt.idx);
  const ausblenden = phase === "out" ? " ps-record-hint-out" : "";
  const sichtbar = phase === "in" ? "1" : "0";

  return (
    <>
      <span
        data-testid="record-ghost"
        data-ps-gesture={tip.kind}
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
        data-ps-hint-visible={sichtbar}
        data-ps-hint-phase={phase}
        className={`ps-record-tip${ausblenden}`}
      >
        {/* Der Hinweis läuft als gebogener Text auf einem KREIS um den Knopf
            (Bauart wie im css-tricks-Rezept „curved text along path"):
            <defs><path id=…></defs>, dann <text><textPath href=…>.
            text-anchor: middle + startOffset 50% setzen den Text mittig auf
            den oberen Scheitel; er bleibt in beiden Wischrichtungen gleich
            lesbar. Die Gruppe dreht den Text langsam um den Kreismittelpunkt
            (.ps-record-arc-spin in src/index.css). */}
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
          <g className={RECORD_ARC_SPIN_CLASS}>
            <text className="ps-record-arc-text" textAnchor="middle">
              {/* Beide Schreibweisen: `href` ist die aktuelle (SVG 2), `xlinkHref`
                  die alte Fassung. Browser, die `href` an textPath nicht kennen
                  (ältere Safari-Fassungen), zeichnen sonst still gar keinen Text. */}
              <textPath
                href={`#${RECORD_ARC_PATH_ID}`}
                xlinkHref={`#${RECORD_ARC_PATH_ID}`}
                startOffset="50%"
              >
                {gezeigt.label}
              </textPath>
            </text>
          </g>
        </svg>
      </div>
    </>
  );
}
