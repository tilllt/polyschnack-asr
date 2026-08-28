/** Change 083: Waveform-Klick-Zeitberechnung (fit + zoom + scroll). */
import { describe, expect, it } from "vitest";

import {
  MAX_TIMING_PPS,
  MIN_PPS,
  clampWordTiming,
  fitPps,
  timeFromClick,
  timingPps,
} from "./waveformTime";

describe("timeFromClick (Change 083)", () => {
  it("Fit-Ansicht: Klick-Verhältnis = Zeit-Verhältnis (95-min-Audio)", () => {
    // 5710 s, Container 800 px → pps ≈ 0.14; Klick bei 50 % der Breite
    const t = timeFromClick(400, 0, fitPps(800, 5710), 5710);
    expect(t).toBeCloseTo(2855, 0);
  });

  it("gezoomt: Scroll-Position + Klick-Position ergeben absolute Zeit", () => {
    // pps = 50, View gescrollt auf 5000 px (= 100 s); Klick 400 px weiter (= +8 s)
    expect(timeFromClick(400, 5000, 50, 600)).toBeCloseTo(108, 0);
  });

  it("kurzes Audio im Fit: volle Länge sichtbar", () => {
    const pps = fitPps(800, 60); // ≈ 13.3 px/s
    expect(timeFromClick(400, 0, pps, 60)).toBeCloseTo(30, 0);
  });

  it("clamped auf [0, duration]", () => {
    expect(timeFromClick(99999, 0, 1, 100)).toBe(100);
    expect(timeFromClick(0, 0, 1, 100)).toBe(0);
    expect(timeFromClick(-50, 0, 1, 100)).toBe(0);
  });

  it("pps 0/NaN-fest: fällt auf MIN_PPS zurück statt Division durch 0", () => {
    // 100px / 0.05 = 2000 s — innerhalb der Dauer, kein NaN/Infinity
    expect(timeFromClick(100, 0, 0, 10000)).toBeCloseTo(100 / MIN_PPS, 0);
  });
});

describe("fitPps (Change 083)", () => {
  it("lange Audios: fit < 1 px/s (vorher unmöglich, minPxPerSec=1)", () => {
    expect(fitPps(800, 5710)).toBeCloseTo(800 / 5710, 3);
    expect(fitPps(800, 5710)).toBeLessThan(1);
  });

  it("kurze Audios: fit = Breite/Dauer", () => {
    expect(fitPps(800, 60)).toBeCloseTo(13.33, 1);
  });

  it("nie kleiner als MIN_PPS", () => {
    expect(fitPps(800, 1_000_000)).toBe(MIN_PPS);
  });
});

// ── Change 137: Timing-Tab (30 %-Zoom + Wort-Timing-Clamp) ──

describe("timingPps (Change 137)", () => {
  it("Wortdauer belegt ~30 % der sichtbaren Zeitspanne", () => {
    // 800 px Container, Wort 1 s → pps = 0.3*800/1 = 240 px/s →
    // sichtbare Zeitspanne = 800/240 ≈ 3.33 s → Wort = 30 %.
    const pps = timingPps(800, 1);
    expect(pps).toBeCloseTo(240, 6);
    expect(800 / pps).toBeCloseTo(1 / 0.3, 6);
  });

  it("langes Wort (10 s): pps bleibt im Verhältnis (24 px/s)", () => {
    expect(timingPps(800, 10)).toBeCloseTo(24, 6);
  });

  it("sehr kurzes Wort: clamped auf MAX_TIMING_PPS statt Explosion", () => {
    expect(timingPps(800, 0.01)).toBe(MAX_TIMING_PPS);
    expect(timingPps(800, 0.001)).toBe(MAX_TIMING_PPS);
  });

  it("nie kleiner als MIN_PPS (riesige Wörter)", () => {
    expect(timingPps(800, 100_000)).toBe(MIN_PPS);
  });
});

describe("clampWordTiming (Change 137)", () => {
  it("innerhalb der Grenzen: unverändert", () => {
    expect(clampWordTiming(1.2, 1.9, 1.0, 2.0)).toEqual({ start: 1.2, end: 1.9 });
  });

  it("Start-Handle: nicht vor das Vorgänger-Ende ziehen (minStart)", () => {
    expect(clampWordTiming(0.5, 1.9, 1.0, 2.0).start).toBe(1.0);
  });

  it("Ende-Handle: nicht über den Folgewort-Start ziehen (maxEnd)", () => {
    expect(clampWordTiming(1.2, 2.5, 1.0, 2.0).end).toBe(2.0);
  });

  it("Mindestdauer 20 ms bleibt erhalten", () => {
    const c = clampWordTiming(1.0, 1.005, 0.9, 3.0);
    expect(c.end - c.start).toBeGreaterThanOrEqual(0.019);
  });

  it("ohne Nachbarn (undefined): keine Grenzen, nur Mindestdauer", () => {
    expect(clampWordTiming(5, 6, undefined, undefined)).toEqual({ start: 5, end: 6 });
    // Start weit nach rechts: end-minDur hält die Mindestdauer
    const c = clampWordTiming(100, 6, undefined, undefined);
    expect(c.end - c.start).toBeGreaterThanOrEqual(0.019);
    expect(c.end).toBe(6);
  });
});
