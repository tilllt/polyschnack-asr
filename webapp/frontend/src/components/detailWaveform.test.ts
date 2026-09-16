/** Change 199: Detail-Ebene — Sichtbarkeit, Blenden-Zustandsmaschine,
 *  Spalten-Abbildung des Detailfensters. Reine Logik, kein Canvas. */
import { describe, expect, it } from "vitest";

import {
  ENHANCE_NOISE_MS,
  ENHANCE_TOTAL_MS,
  columnRect,
  detailLayerVisible,
  enhancePhase,
  enhanceRunning,
  grainAmount,
  grainValue,
  prefersReducedMotion,
  windowColumns,
} from "./detailWaveform";

describe("detailLayerVisible (Change 199)", () => {
  it("nur im Timing-Modus UND pausiert", () => {
    expect(detailLayerVisible(true, false)).toBe(true);
    expect(detailLayerVisible(true, true)).toBe(false);
    expect(detailLayerVisible(false, false)).toBe(false);
    expect(detailLayerVisible(false, true)).toBe(false);
  });

  it("im normalen Zoom auch pausiert aus", () => {
    expect(detailLayerVisible(false, false)).toBe(false);
  });
});

describe("Enhance-Blende (Change 199)", () => {
  it("Phasen laufen idle → noise → resolve → sharp", () => {
    expect(enhancePhase(-1)).toBe("idle");
    expect(enhancePhase(0)).toBe("noise");
    expect(enhancePhase(ENHANCE_NOISE_MS - 1)).toBe("noise");
    expect(enhancePhase(ENHANCE_NOISE_MS)).toBe("resolve");
    expect(enhancePhase(ENHANCE_TOTAL_MS - 1)).toBe("resolve");
    expect(enhancePhase(ENHANCE_TOTAL_MS)).toBe("sharp");
    expect(enhancePhase(10_000)).toBe("sharp");
  });

  it("prefers-reduced-motion überspringt die Animation", () => {
    // Kein Rauschen, sofort scharf — die Information ist dieselbe.
    expect(enhancePhase(0, true)).toBe("sharp");
    expect(enhancePhase(50, true)).toBe("sharp");
    expect(grainAmount(50, true)).toBe(0);
    expect(enhanceRunning(50, true)).toBe(false);
  });

  it("Körnung ist in der Rauschphase voll und blendet linear aus", () => {
    expect(grainAmount(-1)).toBe(0);
    expect(grainAmount(ENHANCE_NOISE_MS - 1)).toBe(1);
    const mitte = (ENHANCE_NOISE_MS + ENHANCE_TOTAL_MS) / 2;
    expect(grainAmount(mitte)).toBeCloseTo(0.5, 6);
    expect(grainAmount(ENHANCE_TOTAL_MS)).toBe(0);
    expect(grainAmount(5000)).toBe(0);
  });

  it("enhanceRunning steuert die Animationsschleife", () => {
    expect(enhanceRunning(0)).toBe(true);
    expect(enhanceRunning(ENHANCE_TOTAL_MS - 1)).toBe(true);
    expect(enhanceRunning(ENHANCE_TOTAL_MS)).toBe(false);
    expect(enhanceRunning(-1)).toBe(false);
  });

  it("Körnungs-Zufall ist deterministisch und in [0,1]", () => {
    const a = grainValue(42, 7);
    expect(a).toBe(grainValue(42, 7));       // gleicher Seed → gleicher Wert
    expect(a).toBeGreaterThanOrEqual(0);
    expect(a).toBeLessThanOrEqual(1);
    expect(grainValue(1, 0)).not.toBe(grainValue(2, 0));
  });
});

describe("windowColumns (Change 199)", () => {
  it("1 Bin pro Pixel bei gleicher Auflösung", () => {
    const bytes = new Uint8Array(1000);
    bytes[123] = 200;
    const cols = windowColumns(bytes, 0, { start: 0, end: 1 }, 1000, 1000);
    expect(cols.length).toBe(1000);
    expect(cols[123]).toBe(200);
    expect(cols[124]).toBe(0);
  });

  it("Maximum je Pixel, wenn mehr Bins als Pixel vorhanden sind", () => {
    const bytes = new Uint8Array(1000);
    bytes[10] = 255;                          // 1000 Bins auf 100 px → 10 je Pixel
    const cols = windowColumns(bytes, 0, { start: 0, end: 1 }, 100, 1000);
    expect(cols.length).toBe(100);
    // Pixel 0 deckt Bin 0..9 ab, Bin 10 gehört zu Pixel 1.
    expect(cols[0]).toBe(0);
    expect(cols[1]).toBe(255);
    expect(cols[2]).toBe(0);
  });

  it("berücksichtigt den Versatz des geladenen Fensters", () => {
    // Geladen ab Bin 5000; sichtbar ist 5,0–6,0 s → Pixel 0 trifft Bin 5000
    // (bytes[0]), der letzte Pixel Bin 5999 (bytes[999]).
    const bytes = new Uint8Array(2000);
    bytes[0] = 77;
    bytes[999] = 42;
    bytes[1000] = 99;                         // außerhalb des sichtbaren Fensters
    const cols = windowColumns(bytes, 5000, { start: 5, end: 6 }, 1000, 1000);
    expect(cols[0]).toBe(77);
    expect(cols[999]).toBe(42);
    expect(Math.max(...Array.from(cols))).toBe(77);  // die 99 bleibt draußen
  });

  it("das GANZE geladene Fenster wird NICHT über die Breite gestreckt", () => {
    // Geladen 0–1999 (2 s), sichtbar nur 0–1 s. Pixel 999 muss Bin 999
    // treffen — nicht Bin 1999 (das wäre die Streckung über alles).
    const bytes = new Uint8Array(2000);
    bytes[999] = 111;
    const cols = windowColumns(bytes, 0, { start: 0, end: 1 }, 1000, 1000);
    expect(cols[999]).toBe(111);
    expect(cols[500]).toBe(0);
  });

  it("weniger Bins als Pixel: jeder Bin wird gestreckt", () => {
    const bytes = new Uint8Array([10, 20, 30]);
    const cols = windowColumns(bytes, 0, { start: 0, end: 3 }, 9, 1);
    expect(Array.from(cols)).toEqual([10, 10, 10, 20, 20, 20, 30, 30, 30]);
  });

  it("leere Eingabe und Fenster außerhalb der Daten", () => {
    expect(windowColumns(new Uint8Array(0), 0, { start: 0, end: 1 }, 10).length).toBe(10);
    const bytes = new Uint8Array([5, 6, 7]);
    const cols = windowColumns(bytes, 0, { start: 900, end: 901 }, 4, 1000);
    // Ausschnitt liegt weit hinter den Daten → auf den Rand geclampt, kein Absturz
    expect(cols.length).toBe(4);
    expect(Array.from(cols)).toEqual([7, 7, 7, 7]);
  });
});

describe("columnRect (Change 199)", () => {
  it("Vollausschlag füllt fast die ganze Höhe, zentriert", () => {
    const r = columnRect(255, 5, 80);
    expect(r.x).toBe(5);
    expect(r.w).toBe(1);
    expect(r.y).toBeCloseTo(1, 6);
    expect(r.h).toBeCloseTo(78, 6);
  });

  it("Null hat trotzdem 1 px Höhe (sonst Lücken im Rauschen)", () => {
    const r = columnRect(0, 0, 80);
    expect(r.h).toBe(1);
    expect(r.y).toBeCloseTo(39.5, 6);
  });

  it("halber Ausschlag ist halb so hoch", () => {
    const r = columnRect(128, 0, 81);
    expect(r.h).toBeLessThan(columnRect(255, 0, 81).h);
    expect(r.h).toBeGreaterThan(1);
  });
});

describe("prefersReducedMotion (Change 199)", () => {
  it("ohne Browser-Umgebung sicher false", () => {
    expect(prefersReducedMotion()).toBe(false);
  });
});
