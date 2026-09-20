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
  children?: ReactNode;
}

export function Zone({ variant, className, style, children, ...rest }: ZoneProps) {
  const zoneStyle: CSSProperties = {
    height: `var(${ZONE_HEIGHT_VAR})`,
    maxWidth: `var(${ZONE_WIDTH_VAR})`,
    width: "100%",
    ...style,
  };
  return (
    <div
      {...rest}
      data-ps-zone={variant}
      className={`ps-zone ps-zone-${variant}${className ? ` ${className}` : ""}`}
      style={zoneStyle}
    >
      {children}
    </div>
  );
}
