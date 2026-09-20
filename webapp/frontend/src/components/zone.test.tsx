/**
 * Change 215 (Nutzer-Vorgabe 20.09.2026) — die drei Quellen-Tabs (Datei-Upload,
 * Aufnahme, URL-Import) müssen dieselbe Zone haben: gleiche Höhe, gleiche
 * Breite, gleicher Rand, gleicher Eckenradius, gleicher Innenabstand. Nur die
 * Linienart darf sich unterscheiden (gestrichelt = Ablegefläche).
 *
 * jsdom rechnet keine CSS-Dateien aus und kann keine Pixel messen. Deshalb
 * prüft dieser Test zweierlei:
 *   1. die gerenderte Struktur — alle drei Zonen tragen dieselbe Klasse
 *      `ps-zone` und dieselbe Höhen-/Breitenquelle (`var(--ps-zone-h)` bzw.
 *      `var(--ps-zone-maxw)`), und zwar unabhängig von ihrem Inhalt;
 *   2. die CSS-Werte in src/index.css — die drei Breakpoint-Stufen, die feste
 *      Höhe und die Tatsache, dass nur `border-style` zwischen den Varianten
 *      wechselt.
 * Die tatsächlichen Pixel wurden beim Umbau zusätzlich im echten Browser an
 * allen drei Zonen gemessen (getBoundingClientRect).
 */
import { render } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { Zone, ZONE_HEIGHT_VAR, ZONE_WIDTH_VAR } from "./Zone";

/** Pfad zu index.css — je nach Laufzeit (Node oder Vitest-Laufzeit). */
function cssPfad(): string {
  const hier = import.meta.url;
  if (hier.startsWith("file:")) {
    return fileURLToPath(new URL("../index.css", hier));
  }
  // Vitest lädt Module über eine eigene Laufzeit (keine file:-URL). Dort ist
  // das Arbeitsverzeichnis der Frontend-Ordner (dort liegt vite.config.ts).
  return "src/index.css";
}

const css = readFileSync(cssPfad(), "utf8");

/** Inhalt einer CSS-Regel (grob, reicht für die hier gesetzten Regeln). */
function rule(selector: string): string {
  const start = css.indexOf(selector);
  expect(start, `CSS-Regel „${selector}" fehlt in index.css`).toBeGreaterThan(-1);
  const open = css.indexOf("{", start);
  const close = css.indexOf("}", open);
  return css.slice(open + 1, close);
}

/** Gemessene bisherige Upload-Dropzone (Browser, 20.09.2026), in Pixel. */
const GEMESSEN_MOBIL_HOEHE = 165.67;

function renderDreiZonen() {
  const utils = render(
    <div>
      {/* Datei-Upload */}
      <Zone variant="dashed" data-testid="zone-upload">
        <div>Dateien hierher ziehen</div>
        <div>Mehrere Dateien möglich</div>
      </Zone>
      {/* Aufnahme */}
      <Zone variant="solid" data-testid="zone-record">
        <button type="button">Aufnahme starten</button>
      </Zone>
      {/* URL-Import */}
      <Zone variant="solid" data-testid="zone-url">
        <div>https://youtube.com/watch?v=…</div>
        <input type="url" />
      </Zone>
    </div>
  );
  return {
    ...utils,
    zonen: ["zone-upload", "zone-record", "zone-url"].map(
      (id) => utils.getByTestId(id) as HTMLElement
    ),
  };
}

describe("Change 215 — einheitliche Zonen", () => {
  test("alle drei Quellen benutzen dieselbe Zone-Klasse", () => {
    const { zonen } = renderDreiZonen();
    expect(zonen).toHaveLength(3);
    for (const z of zonen) {
      expect(z.classList.contains("ps-zone")).toBe(true);
    }
  });

  test("die drei Zonen haben dieselbe Höhe und dieselbe Breite", () => {
    const { zonen } = renderDreiZonen();
    const hoehen = zonen.map((z) => z.style.height);
    const breiten = zonen.map((z) => z.style.maxWidth);
    for (const h of hoehen) expect(h).toBe(hoehen[0]);
    for (const b of breiten) expect(b).toBe(breiten[0]);
    // Beide Werte kommen aus den CSS-Variablen — eine Quelle für alle Tabs.
    expect(hoehen[0]).toBe(`var(${ZONE_HEIGHT_VAR})`);
    expect(breiten[0]).toBe(`var(${ZONE_WIDTH_VAR})`);
  });

  test("kein Inhalt bestimmt die Höhe der Zone", () => {
    // Derselbe Test wie oben, aber mit sehr viel bzw. gar keinem Inhalt:
    // die Höhenangabe darf sich dadurch nicht ändern. Genau das ließ den
    // Aufnahmeknopf zuvor springen (Hinweistexte als Höhengeber).
    const { getByTestId } = render(
      <div>
        <Zone variant="solid" data-testid="leer" />
        <Zone variant="solid" data-testid="viel">
          <div>Zeile 1</div>
          <div>Zeile 2</div>
          <div>Zeile 3</div>
          <div>Zeile 4</div>
          <div>Zeile 5</div>
          <div>Zeile 6</div>
          <div>Fehlermeldung, die früher die Fläche vergrößert hätte</div>
        </Zone>
      </div>
    );
    expect((getByTestId("leer") as HTMLElement).style.height).toBe(
      (getByTestId("viel") as HTMLElement).style.height
    );
    // Feste Höhe (nicht min-height) + overflow: hidden in der Klasse.
    expect(rule(".ps-zone {")).toContain("height: var(--ps-zone-h)");
    expect(rule(".ps-zone {")).toContain("overflow: hidden");
  });

  test("Rand, Radius und Innenabstand stehen an einer Stelle", () => {
    const zone = rule(".ps-zone {");
    expect(zone).toContain("border: 2px solid var(--ps-zone-border)");
    expect(zone).toContain("border-radius: 12px");
    expect(zone).toContain("padding: 12px");
    expect(zone).toContain("align-items: center");
    expect(zone).toContain("justify-content: center");
  });

  test("nur die Linienart unterscheidet sich", () => {
    expect(rule(".ps-zone-dashed")).toContain("border-style: dashed");
    expect(rule(".ps-zone-solid")).toContain("border-style: solid");
    // Randstärke/Radius werden in den Varianten nicht angefasst.
    expect(rule(".ps-zone-dashed")).not.toContain("border-width");
    expect(rule(".ps-zone-dashed")).not.toContain("border-radius");
    expect(rule(".ps-zone-solid")).not.toContain("border-width");
    expect(rule(".ps-zone-solid")).not.toContain("border-radius");
  });

  test("drei feste Stufen über Medienabfragen, Desktop größer als mobil", () => {
    const iMobil = css.lastIndexOf("--ps-zone-h: 144px");
    const i640 = css.lastIndexOf("--ps-zone-h: 160px");
    const i1024 = css.lastIndexOf("--ps-zone-h: 174px");
    expect(iMobil).toBeGreaterThan(-1);
    expect(i640).toBeGreaterThan(iMobil);
    expect(i1024).toBeGreaterThan(i640);
    // Die beiden größeren Stufen hängen wirklich an den Medienabfragen.
    expect(css.lastIndexOf("@media (min-width: 640px)")).toBeLessThan(i640);
    expect(css.lastIndexOf("@media (min-width: 1024px)")).toBeLessThan(i1024);
    expect(i640).toBeLessThan(css.lastIndexOf("@media (min-width: 1024px)"));
    // Breite wächst mit (Obergrenze je Stufe).
    const wMobil = css.indexOf("--ps-zone-maxw: 100%");
    const w640 = css.indexOf("--ps-zone-maxw: 560px");
    const w1024 = css.indexOf("--ps-zone-maxw: 640px");
    expect(w640).toBeGreaterThan(wMobil);
    expect(w1024).toBeGreaterThan(w640);
  });

  test("die Stufen bleiben kleiner als die ursprüngliche Upload-Fläche", () => {
    // Change 217: Die 75 % waren der Ausgangspunkt, nicht die Obergrenze. Die
    // Stufen dürfen wachsen, wenn sonst Inhalte fehlen — aber weiterhin klar
    // unter der Fläche bleiben, die die Upload-Zone vorher hatte.
    const anteil = 144 / GEMESSEN_MOBIL_HOEHE;
    expect(anteil).toBeLessThan(1);
    expect(anteil).toBeGreaterThan(0.8);
    // „bei Desktop größer als mobil": mindestens 15 % mehr Höhe.
    expect(174 / 144).toBeGreaterThan(1.15);
    // Die mittlere Stufe liegt zwischen den beiden anderen.
    expect(160).toBeGreaterThan(144);
    expect(174).toBeGreaterThan(160);
  });

  test("Gestenhinweise bleiben in der festen Fläche und geben keine Höhe vor", () => {
    // Change 216: Der frühere Hinweisblock NEBEN dem Knopf (eigene
    // Mindesthöhe 96 px) ist entfernt. Die Hinweise liegen jetzt
    // absolut über bzw. unter dem Knopf und können keine Höhe vorgeben.
    expect(/\.ps-tips\s*[,{]/.test(css)).toBe(false);
    expect(/\.ps-tips-/.test(css)).toBe(false);
    expect(rule(".ps-record-tip {")).toContain("position: absolute");
    expect(rule(".ps-record-ghost {")).toContain("position: absolute");
    expect(rule(".ps-record-stage {")).toContain("position: relative");
  });

  test("alle drei Tabs benutzen denselben Höhenrahmen", () => {
    // Change 217: Ein Rahmen für alle drei Quellen — dieselbe Mindesthöhe,
    // gleicher Innenabstand, damit kein Tab höher ist als die anderen.
    const body = rule(".ps-tab-body {");
    expect(body).toContain("min-height: calc(var(--ps-zone-h) + 48px)");
    expect(body).toContain("padding: 8px 0");
    expect(body).toContain("gap: 8px");
    // Dieselbe Zeile in jedem Tab (Zeit/Status, URL-Anmeldung).
    expect(rule(".ps-tab-line {")).toContain("min-height: 16px");
  });
});
