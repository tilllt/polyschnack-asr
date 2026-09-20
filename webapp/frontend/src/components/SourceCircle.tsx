/**
 * Change 220 (Nutzer-Vorgabe 20.09.2026) — EINE Bauart für die drei
 * Quellen-Kreise: Datei-Upload, Aufnahme, Download (URL).
 *
 * Der Nutzer wollte die Quellen-Auswahl als drei gleichrangige Kreis-Knöpfe:
 * monochromes Zeichen IM Kreis, der Kreis selbst nur als Outline, und der
 * Name der Quelle läuft animiert auf einem Kreis AUSSEN um den Ring.
 *
 * Bauart (genau wie die Gestenhinweise in RecordGestureHint.tsx — dort ist das
 * Vorbild): <defs><path id=…></defs>, dann <text><textPath href=…>, gedreht
 * wird die SVG-Gruppe langsam um den Kreismittelpunkt
 * (transform-box: view-box + transform-origin = cx/cy, siehe index.css).
 *
 * „Vereinheitlichen" heißt hier: die drei Kreise ziehen ALLE ihre Maße,
 * Schriftgröße, Schriftfarbe und Drehzeit aus den Konstanten dieser Datei.
 * Es gibt genau eine Quelle für Größe (SOURCE_CIRCLE_SHAPE), Ringstärke
 * (SOURCE_CIRCLE_BORDER), Schriftgröße des Kreistextes
 * (SOURCE_CIRCLE_ARC.fontSize) und Drehzeit (SOURCE_CIRCLE_SPIN_MS). Wer einen
 * Wert ändert, ändert ihn für alle drei — ein Auseinanderlaufen ist baulich
 * nicht möglich, und die Tests in sourceCircles.test.tsx rechnen das nach.
 *
 * Farben: ausschließlich aus der eigenen Palette (--ps-accent #2ea043,
 * --ps-err #f85149, Amber #d99e2b, dazu die Grautöne). Die Zeichen zeichnen
 * mit `currentColor`; die Farbe kommt aus der Klasse des Knopfes
 * (.ps-src-btn / .ps-src-btn.ps-src-on in index.css). Kein Fremdmaterial,
 * keine Icon-Bibliothek, kein npm-Paket, kein Lottie.
 */
import type { ReactNode, Ref } from "react";

/** Die drei Quellen — mehr gibt es nicht (Reihenfolge der Knopfreihe). */
export type SourceKind = "upload" | "record" | "download";

export const SOURCE_KINDS: readonly SourceKind[] = ["upload", "record", "download"];

/**
 * Größe und Form: dieselbe Klasse wie der bestehende Aufnahmeknopf
 * (RECORD_BUTTON_SHAPE in RecordGestureHint.tsx) — die Kreise sind dadurch
 * immer gleich groß, auch auf dem Gerät.
 */
export const SOURCE_CIRCLE_SHAPE = "w-16 h-16 sm:w-20 sm:h-20 rounded-full";

/** Ringstärke der Outline (px). Für alle drei Kreise dieselbe. */
export const SOURCE_CIRCLE_BORDER = 2;

/**
 * Maße des Kreistextes (px in der Zeichenfläche des SVG) — EIN Satz für alle
 * drei Knöpfe.
 *   Ringradius      32 px (mobil) bzw. 40 px (ab 640 px), siehe SOURCE_CIRCLE_SHAPE.
 *   r = 35 px       Der Textkreis liegt unmittelbar am Ring: bei 64-px-Knopf
 *                   (Ringaußenkante 32 px) sind das 3 px Luft zur Grundlinie.
 *                   Ab 640 px ist der Knopf 80 px groß (Ringaußenkante 40 px) —
 *                   die Zeichenfläche in index.css wächst prozentual mit dem
 *                   Knopf (218,75 % × 81,25 % → ×1,25), dort sind es 3,75 px.
 *                   Schrift und Kreis wachsen mit (10 → 12,5 px); das
 *                   Verhältnis Knopf/Ring/Schrift ist in jeder Größe gleich.
 *                   Nur Unterlängen („p" in „Upload") reichen bis auf ~0,8 px
 *                   (mobil) bzw. ~1,4 px (Desktop) an die Ringlinie heran —
 *                   im Browser nachgemessen, sie berühren sie nicht.
 *   Höhe 52 px      Zeichenfläche — bleibt bewusst, damit die Luft über der
 *                   Reihe (28 px) unverändert ist; der Text sitzt jetzt nur
 *                   weiter innen in dieser Fläche.
 *   Breite 140 px   = 2 × 37 + 66 px Luft für die Textlänge links/rechts.
 *   Länge des Halbkreises π × 37 ≈ 116 px. Die längste Beschriftung
 *                   („Aufnehmen", 9 Zeichen) braucht bei 10 px rund 50 px —
 *                   sie läuft also nie ineinander und wird nie abgeschnitten.
 */
export const SOURCE_CIRCLE_ARC = {
  width: 140,
  height: 52,
  /** Kreismittelpunkt in der Zeichenfläche (= Knopfmitte). */
  cx: 70,
  cy: 52,
  /** EIN Radius für beide Achsen — ein echter Kreis, keine Ellipse.
   *  Abstand Ringaußenkante → Schriftgrundlinie (im Browser nachgemessen,
   *  Chrome, Messprobe mit dem gebauten CSS): 3 px beim 64-px-Knopf,
   *  3,75 px beim 80-px-Knopf (Zeichenfläche ×1,25). Die Unterlänge des „p"
   *  in „Upload" reicht bis auf ~0,8 px (mobil) bzw. ~1,4 px (Desktop) an die
   *  Ringlinie heran — sie berührt sie nicht. */
  r: 35,
  /** Schriftgröße des Kreistextes in px. */
  fontSize: 10,
} as const;

export const SOURCE_CIRCLE_ARC_VIEWBOX = `0 0 ${SOURCE_CIRCLE_ARC.width} ${SOURCE_CIRCLE_ARC.height}`;

/** Klasse der SVG-Gruppe, die den Kreistext langsam dreht (index.css). */
export const SOURCE_CIRCLE_SPIN_CLASS = "ps-src-arc-spin";

/** Dauer einer vollen Umdrehung — langsam, wie beim Gestenhinweis (30 s). */
export const SOURCE_CIRCLE_SPIN_MS = 30000;

/**
 * `d` des Bogens: Halbkreis von links nach rechts über dem Knopf (sweep-flag 1
 * = im Uhrzeigersinn, also über die obere Hälfte). Beide Radien sind gleich —
 * das ist der Kreis.
 */
export const SOURCE_CIRCLE_ARC_PATH_D =
  `M ${SOURCE_CIRCLE_ARC.cx - SOURCE_CIRCLE_ARC.r} ${SOURCE_CIRCLE_ARC.cy} ` +
  `A ${SOURCE_CIRCLE_ARC.r} ${SOURCE_CIRCLE_ARC.r} 0 0 1 ${SOURCE_CIRCLE_ARC.cx + SOURCE_CIRCLE_ARC.r} ${SOURCE_CIRCLE_ARC.cy}`;

/** Kennung des SVG-Pfades einer Quelle (je Knopf eigener Pfad, sonst kollidieren sie). */
export function sourceArcPathId(kind: SourceKind): string {
  return `ps-source-arc-${kind}`;
}

/**
 * Die drei Zeichen — selbst gezeichnet (Inline-SVG), monochrom (currentColor),
 * reine Striche. 24×24-Zeichenfläche, Strichstärke 1,8 px.
 */
export function SourceIcon({ kind, size = 26 }: { kind: SourceKind; size?: number }): ReactNode {
  const svgProps = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    "aria-hidden": true as const,
    focusable: "false" as const,
    "data-ps-icon": kind,
    className: `ps-src-icon ps-src-icon-${kind}`,
    style: { display: "block" as const },
  };
  const stroke = {
    fill: "none" as const,
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };

  // Upload: Pfeil nach oben aus einer Ablage (Tray).
  if (kind === "upload") {
    return (
      <svg {...svgProps}>
        <path d="M12 16.2V4.8" {...stroke} />
        <path d="M8.1 8.7 12 4.8l3.9 3.9" {...stroke} />
        <path d="M4.8 14.4v3.6a1.2 1.2 0 0 0 1.2 1.2h12a1.2 1.2 0 0 0 1.2-1.2v-3.6" {...stroke} />
      </svg>
    );
  }

  // Aufnahme: Mikrofon (Kapsel, Bügel, Fuß).
  if (kind === "record") {
    return (
      <svg {...svgProps}>
        <path d="M12 4.4a2.9 2.9 0 0 1 2.9 2.9v4.3a2.9 2.9 0 0 1-5.8 0V7.3A2.9 2.9 0 0 1 12 4.4Z" {...stroke} />
        <path d="M6.7 11.2a5.3 5.3 0 0 0 10.6 0" {...stroke} />
        <path d="M12 16.5v3.1" {...stroke} />
        <path d="M9.3 19.6h5.4" {...stroke} />
      </svg>
    );
  }

  // Download (URL): zwei ineinandergreifende Kettenglieder.
  return (
    <svg {...svgProps}>
      <path
        d="M10.3 13.7a3.5 3.5 0 0 1 0-5l2.4-2.4a3.5 3.5 0 0 1 5 5l-1.1 1.1"
        {...stroke}
      />
      <path
        d="M13.7 10.3a3.5 3.5 0 0 1 0 5l-2.4 2.4a3.5 3.5 0 0 1-5-5l1.1-1.1"
        {...stroke}
      />
    </svg>
  );
}

export interface SourceCircleProps {
  kind: SourceKind;
  /** Beschriftung: Knopfname (aria-label) UND Text auf dem Kreis. */
  label: string;
  /** Ist diese Quelle gerade gewählt? */
  selected: boolean;
  /** Gesperrt (z. B. während einer laufenden Aufnahme). */
  disabled?: boolean;
  onSelect: () => void;
  /** Zusätzliche Klasse für den Knopf (z. B. Aufnahmezustand). */
  buttonClassName?: string;
  /** Ref auf den echten Knopf (der Aufnahmeknopf bleibt der bestehende). */
  buttonRef?: Ref<HTMLButtonElement>;
}

/**
 * Ein Quellen-Kreis: Outline-Ring mit monochromem Zeichen darin, außen der
 * animiert drehende Name auf einem Kreis.
 *
 * Der gewählte Kreis ist NICHT nur an der Farbe zu erkennen:
 *   - Ring: durchgezogen (.ps-src-on) statt gestrichelt (ungewählt) —
 *     dieselbe Linien-Logik wie bei den Zonen (.ps-zone-solid/dashed);
 *   - zusätzlicher Innenring (::after, 4 px eingerückt);
 *   - Zeichen und Kreistext in Grün (--ps-accent) statt Grau;
 *   - `aria-pressed="true"` und `data-ps-selected="true"` für die Bedienhilfe.
 * Der Zustand ist damit doppelt kodiert (Ring + Schrift) und nie still.
 */
export function SourceCircle({
  kind,
  label,
  selected,
  disabled,
  onSelect,
  buttonClassName,
  buttonRef,
}: SourceCircleProps) {
  const pfadId = sourceArcPathId(kind);
  return (
    <span className="ps-src" data-testid={`source-${kind}`} data-ps-source={kind} data-ps-selected={selected ? "true" : "false"}>
      <button
        ref={buttonRef}
        type="button"
        aria-label={label}
        aria-pressed={selected}
        title={label}
        disabled={disabled}
        onClick={onSelect}
        className={`ps-src-btn ${SOURCE_CIRCLE_SHAPE}${selected ? " ps-src-on" : ""}${
          disabled ? " ps-src-off" : ""
        }${buttonClassName ? ` ${buttonClassName}` : ""}`}
      >
        <SourceIcon kind={kind} />
      </button>
      {/* Der Name der Quelle — gebogener Text auf einem Kreis um den Ring.
          Bewusst ohne eigenen React-Zustand: der Text steht still im DOM und
          dreht sich ausschließlich per CSS. */}
      <span className="ps-src-arc" aria-hidden="true">
        <svg
          className="ps-src-arc-svg"
          viewBox={SOURCE_CIRCLE_ARC_VIEWBOX}
          width={SOURCE_CIRCLE_ARC.width}
          height={SOURCE_CIRCLE_ARC.height}
          focusable="false"
        >
          <defs>
            <path id={pfadId} d={SOURCE_CIRCLE_ARC_PATH_D} />
          </defs>
          <g className={SOURCE_CIRCLE_SPIN_CLASS}>
            <text className="ps-src-arc-text" textAnchor="middle">
              {/* Beide Schreibweisen: `href` ist SVG 2, `xlinkHref` die alte
                  Fassung — ältere Safari-Fassungen zeichnen sonst still nichts. */}
              <textPath href={`#${pfadId}`} xlinkHref={`#${pfadId}`} startOffset="50%">
                {label}
              </textPath>
            </text>
          </g>
        </svg>
      </span>
    </span>
  );
}
