/** Change 083: Waveform-Klick-Zeitberechnung (fit + zoom + scroll). */
import { describe, expect, it } from "vitest";

import { MIN_PPS, fitPps, timeFromClick } from "./waveformTime";

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
