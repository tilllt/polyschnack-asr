/**
 * Change 220 (Nutzer-Vorgabe 20.09.2026) — EINE Bauart für die Quellen-Zeichen:
 * Datei-Upload, Aufnahme, Download (URL).
 *
 * Change 222 (Klarstellung des Nutzers, 20.09.2026): Der Umbau aus Change 220
 * war so NICHT gemeint — die drei Kreise sollten die Tabs nicht ersetzen.
 * Jetzt gilt:
 *   · Die Tab-Reihe besteht aus drei NACKTEN Zeichen (`SourceTab`): kein Kreis,
 *     keine Beschriftung am Zeichen, keine Bewegung. Der gewählte Tab ist
 *     doppelt kodiert — grünes Zeichen UND grüner Strich darunter UND
 *     `aria-pressed` (Zustand nie allein über Farbe, siehe Change 215).
 *   · Der Kreis (`ZoneCircle`) sitzt IN der Zone der jeweiligen Quelle: in der
 *     Ablegefläche (Upload) und in der Adress-Zone (Download). Größe und Form
 *     sind dieselben wie beim bestehenden Aufnahmeknopf
 *     (`RECORD_BUTTON_SHAPE` in RecordGestureHint.tsx) — beide ziehen ihre
 *     Klassen aus dieser Datei bzw. aus jener Konstante.
 *   · Die Beschriftung des Kreises steht STILL am oberen Rand des Kreises,
 *     gekrümmt entlang des Pfades (Nutzer: „Bei Upload und Download steht der
 *     Text am Rand des Kreises statisch entlang des Pfades gekrümmt oben").
 *     Die Drehung ist entfallen (Nutzer: „Generell lassen wir die Animation der
 *     Texte sein, die ist zu unruhig").
 *
 * „Vereinheitlichen" heißt hier: alle Kreise ziehen ALLE Maße, Schriftgröße,
 * Schriftfarbe und Ringstärke aus den Konstanten dieser Datei. Es gibt genau
 * eine Quelle für Größe (SOURCE_CIRCLE_SHAPE), Ringstärke
 * (SOURCE_CIRCLE_BORDER) und die Zeichenfläche des Kreistextes
 * (SOURCE_CIRCLE_ARC). Wer einen Wert ändert, ändert ihn für alle — ein
 * Auseinanderlaufen ist baulich nicht möglich, und die Tests in
 * sourceCircles.test.tsx rechnen das nach.
 *
 * Farben: ausschließlich aus der eigenen Palette (--ps-accent #2ea043,
 * --ps-err #f85149, Amber #d99e2b, dazu die Grautöne). Die Zeichen zeichnen
 * mit `currentColor`; die Farbe kommt aus der Klasse des Elements
 * (.ps-src-btn / .ps-src-btn.ps-src-on / .ps-src-tab-btn in index.css). Kein
 * Fremdmaterial, keine Icon-Bibliothek, kein npm-Paket, kein Lottie.
 */
import type { ReactNode, Ref } from "react";

/** Die drei Quellen — mehr gibt es nicht (Reihenfolge der Tab-Reihe). */
export type SourceKind = "upload" | "record" | "download";

export const SOURCE_KINDS: readonly SourceKind[] = ["upload", "record", "download"];

/**
 * Größe und Form der Kreise: dieselbe Klasse wie der bestehende Aufnahmeknopf
 * (RECORD_BUTTON_SHAPE in RecordGestureHint.tsx) — die Kreise sind dadurch
 * immer gleich groß, auch auf dem Gerät.
 */
export const SOURCE_CIRCLE_SHAPE = "w-16 h-16 sm:w-20 sm:h-20 rounded-full";

/** Ringstärke der Outline (px). Für alle Kreise dieselbe. */
export const SOURCE_CIRCLE_BORDER = 2;

/** Kantenlänge des Zeichens in der Tab-Reihe (px) — nackt, ohne Kreis. */
export const SOURCE_TAB_ICON_SIZE = 26;

/**
 * Maße des Kreistextes (px in der Zeichenfläche des SVG) — EIN Satz für alle
 * Kreise.
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
 *   Höhe 52 px      Zeichenfläche; sie ragt damit 20 px über die Oberkante des
 *                   Knopfes hinaus (Desktop ×1,25 = 25 px). Diesen Platz
 *                   reserviert index.css in der Zone
 *                   (--ps-arc-reserve), sonst schneidet `overflow: hidden`
 *                   die Schrift ab.
 *   Breite 140 px   = 2 × 35 + 70 px Luft für die Textlänge links/rechts.
 *   Länge des Halbkreises π × 35 ≈ 110 px. Die längste Beschriftung
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
   *  Abstand Ringaußenkante → Schriftgrundlinie (Nutzer-Vorgabe 20.09.2026:
   *  „Texte entlang des Pfades näher am Kreis ca. 5px Abstand"): 5 px beim
   *  80-px-Knopf (36 × 1,25 - 40) und 4 px beim 64-px-Knopf (36 - 32) — die
   *  Zeichenfläche wächst prozentual mit dem Knopf (×1,25), beide Stufen
   *  liegen damit im selben „rund 5 px". Die Unterlänge des „p" in „Upload"
   *  reicht bis auf ~2 px (mobil) bzw. ~2,4 px (Desktop) an die Ringlinie
   *  heran — sie berührt sie nicht. */
  r: 36,
  /** Schriftgröße des Kreistextes in px. */
  fontSize: 10,
} as const;

export const SOURCE_CIRCLE_ARC_VIEWBOX = `0 0 ${SOURCE_CIRCLE_ARC.width} ${SOURCE_CIRCLE_ARC.height}`;

/**
 * `d` des Bogens: Halbkreis von links nach rechts über dem Knopf (sweep-flag 1
 * = im Uhrzeigersinn, also über die obere Hälfte). Beide Radien sind gleich —
 * das ist der Kreis. Der Text läuft STILL auf diesem Bogen (Change 222).
 */
export const SOURCE_CIRCLE_ARC_PATH_D =
  `M ${SOURCE_CIRCLE_ARC.cx - SOURCE_CIRCLE_ARC.r} ${SOURCE_CIRCLE_ARC.cy} ` +
  `A ${SOURCE_CIRCLE_ARC.r} ${SOURCE_CIRCLE_ARC.r} 0 0 1 ${SOURCE_CIRCLE_ARC.cx + SOURCE_CIRCLE_ARC.r} ${SOURCE_CIRCLE_ARC.cy}`;

/**
 * Auf welcher Seite des Kreises steht seine Beschriftung? (Change 223)
 *
 *   top    — Vorgabe: Bogen ÜBER dem Kreis (Zeichenfläche endet mit der
 *            Knopfmitte, `bottom: 50%` in index.css).
 *   bottom — Bogen UNTER dem Kreis, aufrecht lesbar wie eine Bildunterschrift
 *            (Nutzer-Vorgabe 20.09.2026 zum Kreis „Download": „Mache die Button
 *            Beschreibung unten an den Kreis.").
 *
 * WICHTIG: Die Lage der Beschriftung ändert die Lage des KREISES nicht — das
 * Label ist absolut positioniert (`.ps-src-arc`) und damit nicht layoutwirksam.
 * Nutzer-Vorgabe 20.09.2026: „Achte darauf das alle Kreise an der gleichen
 * Position bleiben."
 */
export type LabelSide = "top" | "bottom";

/**
 * Radius des UNTEREN Bogens (Change 224, Nutzer-Vorgabe 20.09.2026:
 * „Die ‚download' Beschriftung des Buttons hat einen anderen Abstand als
 * ‚Upload' und die UI Hints.").
 *
 * Warum muss er größer sein? Bei Text auf einem Pfad sitzen die Buchstaben mit
 * ihrer GRUNDLINIE auf dem Bogen und dehnen sich quer zur Laufrichtung aus:
 *   obere Lage (sweep 1)  der Rücken zeigt nach außen (weg vom Kreis) — dem
 *                         Ring am nächsten kommen die Unterlängen („p").
 *   untere Lage (sweep 0) der Rücken zeigt nach unten (weg vom Kreis) — dem
 *                         Ring am nächsten kommen die GROSSBUCHSTABEN, denn sie
 *                         stehen genau in Richtung Kreismitte.
 * Dieselbe Grundlinie (36) ergibt deshalb unten einen sichtbar kleineren
 * Abstand: im Browser gemessen (80-px-Knopf, Ringlinie bei 40 px) waren es
 *   oben    2,59 px ÜBERLAPPUNG mit der Ringlinie (Tinte bei 37,41 px)
 *   unten  13,66 px ÜBERLAPPUNG (Tinte bei 26,34 px).
 * Mit 44 px liegt die Tinte unten bei ~37,5 px — derselbe Sitz wie oben
 * (37,41 px bei „Upload", im Browser gemessen).
 */
export const SOURCE_CIRCLE_ARC_BOTTOM_R = 44;

/**
 * `d` des Bogens für eine Seite. Die Zeichenfläche ist für BEIDE Seiten
 * 140 × 52 px; sie liegt beim unteren Bogen nur auf der anderen Seite der
 * Knopfmitte (deshalb cy = 0 statt 52):
 *   top     M (cx-r, cy) A r r 0 0 1 (cx+r, cy)  → Bogen nach oben (sweep 1)
 *   bottom  M (cx-R, 0)  A R R 0 0 0 (cx+R, 0)   → Bogen nach unten (sweep 0),
 *           R = SOURCE_CIRCLE_ARC_BOTTOM_R (siehe dort)
 * Beim unteren Bogen zeigt der Buchstabenrücken nach UNTEN (weg vom Kreis) —
 * der Text steht also aufrecht unter dem Kreis, nicht auf dem Kopf.
 */
export function sourceArcPathD(side: LabelSide): string {
  const { cx, cy, r } = SOURCE_CIRCLE_ARC;
  if (side === "bottom") {
    const R = SOURCE_CIRCLE_ARC_BOTTOM_R;
    return `M ${cx - R} 0 A ${R} ${R} 0 0 0 ${cx + R} 0`;
  }
  return `M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`;
}

/** Bogen der Beschriftung UNTER dem Kreis (Change 223). */
export const SOURCE_CIRCLE_ARC_BOTTOM_PATH_D = sourceArcPathD("bottom");

/** Kennung des SVG-Pfades einer Quelle (je Kreis eigener Pfad, sonst kollidieren sie). */
export function sourceArcPathId(kind: SourceKind): string {
  return `ps-source-arc-${kind}`;
}

/**
 * Die drei Zeichen — selbst gezeichnet (Inline-SVG), monochrom (currentColor),
 * reine Striche. 24×24-Zeichenfläche, Strichstärke 1,8 px.
 */
export function SourceIcon({ kind, size = SOURCE_TAB_ICON_SIZE }: { kind: SourceKind; size?: number }): ReactNode {
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

/**
 * Die Beschriftung eines Kreises — gebogener Text auf einem Kreis, STILL
 * (Change 222; die Drehung aus Change 220/219 ist entfallen).
 * Bewusst ohne eigenen React-Zustand: der Text steht fest im DOM, es gibt
 * keine Animation, die laufen oder angehalten werden könnte.
 *
 * Change 223: Die Seite ist wählbar (`side`, Vorgabe „top"). Beide Lagen sind
 * absolut positioniert und verschieben den Kreis nicht (siehe LabelSide).
 */
export function CircleLabel({
  kind,
  label,
  side = "top",
}: {
  kind: SourceKind;
  label: string;
  side?: LabelSide;
}): ReactNode {
  const pfadId = sourceArcPathId(kind);
  return (
    <span className={`ps-src-arc${side === "bottom" ? " ps-src-arc--bottom" : ""}`} aria-hidden="true">
      <svg
        className="ps-src-arc-svg"
        viewBox={SOURCE_CIRCLE_ARC_VIEWBOX}
        width={SOURCE_CIRCLE_ARC.width}
        height={SOURCE_CIRCLE_ARC.height}
        focusable="false"
      >
        <defs>
          <path id={pfadId} d={sourceArcPathD(side)} />
        </defs>
        <text className="ps-src-arc-text" textAnchor="middle">
          {/* Beide Schreibweisen: `href` ist SVG 2, `xlinkHref` die alte
              Fassung — ältere Safari-Fassungen zeichnen sonst still nichts. */}
          <textPath href={`#${pfadId}`} xlinkHref={`#${pfadId}`} startOffset="50%">
            {label}
          </textPath>
        </text>
      </svg>
    </span>
  );
}

export interface SourceTabProps {
  kind: SourceKind;
  /** Name der Quelle — nur noch aria-label/title (Change 222: kein Text am Zeichen). */
  label: string;
  /** Ist diese Quelle gerade gewählt? */
  selected: boolean;
  /** Gesperrt (z. B. während einer laufenden Aufnahme). */
  disabled?: boolean;
  onSelect: () => void;
}

/**
 * Ein Zeichen der Tab-Reihe: NACKT (Change 222) — kein Kreis, kein Text, keine
 * Bewegung. Der gewählte Tab ist doppelt kodiert (Farbe + Strich darunter,
 * siehe index.css) und trägt `aria-pressed`; der Name steht in `aria-label`
 * und `title`, also nicht nur visuell.
 */
export function SourceTab({ kind, label, selected, disabled, onSelect }: SourceTabProps) {
  return (
    <span
      className="ps-src-tab"
      data-testid={`source-${kind}`}
      data-ps-source={kind}
      data-ps-selected={selected ? "true" : "false"}
    >
      <button
        type="button"
        aria-label={label}
        aria-pressed={selected}
        title={label}
        disabled={disabled}
        onClick={onSelect}
        className={`ps-src-tab-btn${selected ? " ps-src-on" : ""}${disabled ? " ps-src-off" : ""}`}
      >
        <SourceIcon kind={kind} />
      </button>
    </span>
  );
}

export interface ZoneCircleProps {
  kind: SourceKind;
  /** Beschriftung: Knopfname (aria-label) UND Text auf dem Kreis. */
  label: string;
  /**
   * Seite der Beschriftung: „top" (Vorgabe, Bogen über dem Kreis) oder
   * „bottom" (Bogen unter dem Kreis, Change 223). Ändert die Lage des Kreises
   * NICHT — das Label ist absolut positioniert.
   */
  labelSide?: LabelSide;
  /** Zusätzliche Klasse für den Knopf (z. B. Aufnahmezustand). */
  buttonClassName?: string;
  /** Ref auf den echten Knopf (der Aufnahmeknopf bleibt der bestehende). */
  buttonRef?: Ref<HTMLButtonElement>;
  disabled?: boolean;
  onActivate: () => void;
  /** Kennung für die Tests (z. B. „upload-button"). */
  testId?: string;
}

/**
 * Ein Kreis IN einer Zone: Outline-Ring mit monochromem Zeichen darin und dem
 * Namen der Quelle als gebogener, STILLER Text (Change 222) — über dem Ring
 * (`labelSide="top"`, Vorgabe) oder darunter (`labelSide="bottom"`,
 * Change 223).
 *
 * Der Kreis ist ein echter `<button>`: Tastatur, Fokusrahmen und
 * Bedienhilfe-Standard verhalten sich damit wie überall sonst. Er liegt in
 * einer Zone, die selbst anklickbar ist (Ablegefläche) — der Aufrufer stoppt
 * die Weitergabe des Klicks, damit die Aktion nicht zweimal läuft.
 */
export function ZoneCircle({
  kind,
  label,
  labelSide = "top",
  buttonClassName,
  buttonRef,
  disabled,
  onActivate,
  testId,
}: ZoneCircleProps) {
  return (
    <span className="ps-zone-circle" data-ps-source={kind}>
      <button
        ref={buttonRef}
        type="button"
        data-testid={testId ? `${testId}-button` : undefined}
        aria-label={label}
        title={label}
        disabled={disabled}
        onClick={(e) => {
          // Der Kreis liegt oft in einer Zone, die selbst auf Klicks hört (die
          // Ablegefläche). Ohne dieses Stoppen liefe die Aktion zweimal — die
          // Dateiauswahl ginge zweimal auf.
          e.stopPropagation();
          onActivate();
        }}
        className={`ps-src-btn ${SOURCE_CIRCLE_SHAPE}${disabled ? " ps-src-off" : ""}${
          buttonClassName ? ` ${buttonClassName}` : ""
        }`}
      >
        <SourceIcon kind={kind} />
      </button>
      <CircleLabel kind={kind} label={label} side={labelSide} />
    </span>
  );
}
