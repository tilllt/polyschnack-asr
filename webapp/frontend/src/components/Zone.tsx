/**
 * Change 215 (Nutzer-Vorgabe 20.09.2026) — EINE Zone für alle drei Quellen.
 *
 * Alle drei Tabs (Datei-Upload, Aufnahme, URL-Import) benutzen dieselbe
 * Fläche: gleiche Breite, gleiche Höhe, gleicher Eckenradius, gleiche
 * Randstärke, gleicher Innenabstand, gleiche Ausrichtung. Nur der Inhalt
 * unterscheidet sich — und die Linienart (gestrichelt als Ablege-Hinweis im
 * Upload, durchgezogen in den anderen Zonen).
 *
 * Die Maße stehen an EINER Stelle: `index.css` (Klassen `.ps-zone*`) mit den
 * CSS-Variablen `--ps-zone-h` (Höhe je Breakpoint) und `--ps-zone-maxw`
 * (Breiten-Obergrenze je Breakpoint). Höhe und Breite werden hier als
 * Inline-Variablen gesetzt, damit die Fläche unabhängig vom Inhalt fest ist:
 * kein Text, keine Dateiliste, keine Fortschrittszeile und keine Fehlermeldung
 * kann die Fläche aufspannen.
 */
import type { CSSProperties, HTMLAttributes, ReactNode } from "react";

/** CSS-Variable mit der festen Zonenhöhe (in index.css je Breakpoint gesetzt). */
export const ZONE_HEIGHT_VAR = "--ps-zone-h";
/** CSS-Variable mit der Breiten-Obergrenze (in index.css je Breakpoint gesetzt). */
export const ZONE_WIDTH_VAR = "--ps-zone-maxw";

export type ZoneVariant = "dashed" | "solid";

interface ZoneProps extends HTMLAttributes<HTMLDivElement> {
  /** `dashed` = Ablegefläche (Upload), `solid` = Aufnahme und URL-Import. */
  variant: ZoneVariant;
  /**
   * Change 225 (Nutzer-Vorgabe 20.09.2026): Diese Zone darf nach UNTEN wachsen
   * — für die ausklappbaren Optionen, die IN der Ablegefläche stehen sollen
   * („Die ausklappenden Optionen müssen mit in die drop zone und diese,
   * animiert, nach unten vergrößern. Zusammengeklappt sind alle dropzones
   * gleich gross."). Zugeklappt ist sie über `min-height` genauso groß wie die
   * anderen — die feste Höhe der übrigen Zonen bleibt unangetastet (Change 215:
   * kein Inhalt darf die Fläche aufspannen).
   */
  waechst?: boolean;
  children?: ReactNode;
}

export function Zone({ variant, className, style, children, waechst, ...rest }: ZoneProps) {
  const maße: CSSProperties = {
    maxWidth: `var(${ZONE_WIDTH_VAR})`,
    width: "100%",
    ...style,
  };
  const zoneStyle: CSSProperties = waechst
    ? { minHeight: `var(${ZONE_HEIGHT_VAR})`, ...maße }
    : { height: `var(${ZONE_HEIGHT_VAR})`, ...maße };
  return (
    <div
      {...rest}
      data-ps-zone={variant}
      className={`ps-zone ps-zone-${variant}${waechst ? " ps-zone--waechst" : ""}${
        className ? ` ${className}` : ""
      }`}
      style={zoneStyle}
    >
      {children}
    </div>
  );
}
