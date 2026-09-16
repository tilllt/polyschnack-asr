/** Change 083: Waveform-Klick-Zeitberechnung (fit + zoom + scroll). */
import { describe, expect, it } from "vitest";

import {
  HI_BPS,
  MAX_ELEMENT_PX,
  MAX_TIMING_PPS,
  MIN_WORD_DURATION_S,
  MIN_PPS,
  RESIDENT_BIN_BUDGET,
  clampMoveWordTiming,
  clampWordTiming,
  detailByteRange,
  effectiveMaxPps,
  fitPps,
  hiBinCount,
  markerPct,
  residentBinCount,
  residentBinsPerSecond,
  timeFromClick,
  timingPps,
  timingTargetReachable,
  visibleWindow,
  windowBinRange,
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
    // Der Clamp greift erst unterhalb von 0.3*W/MAX_TIMING_PPS.
    expect(timingPps(800, 0.001)).toBe(MAX_TIMING_PPS);
    expect(timingPps(800, 0.0001)).toBe(MAX_TIMING_PPS);
  });

  it("Zielfenster ohne Breitengrenze: Mindest-Wortdauer erreicht 30 %", () => {
    // Gilt für die reine Formel. Auf langen Dateien ist das NICHT erreichbar,
    // weil die Browser-Breitengrenze den Zoom deckelt — siehe
    // timingTargetReachable (Change 199).
    const W = 1000;
    const pps = timingPps(W, MIN_WORD_DURATION_S);
    expect(pps).toBeLessThan(MAX_TIMING_PPS);
    expect((MIN_WORD_DURATION_S * pps) / W).toBeCloseTo(0.3, 6);
  });

  it("Change 199: das 30-%-Fenster ist auf langen Dateien nicht haltbar", () => {
    // Genau diese Zusicherung stand bis Change 197 im Code, ohne dass der
    // Browser sie einhalten kann: bei 262 min sind nur 2135 px/s erreichbar
    // (2^25 / 15718), ein 0,1-s-Wort bekommt damit 213 px statt 300.
    const W = 1000;
    expect(timingPps(W, 0.1)).toBeGreaterThan(0);         // Formel will 3000
    expect(timingTargetReachable(W, 15718, 0.1)).toBe(false);
    expect(timingTargetReachable(W, 15718, 1.0)).toBe(true);
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

// ── Change 155: Timing-Zoom (Marker-Position + Verschieben) ──

describe("visibleWindow (Change 155)", () => {
  it("Fit: Fenster = [0, duration]", () => {
    expect(visibleWindow(800, 0, fitPps(800, 600), 600)).toEqual({ start: 0, end: 600 });
  });

  it("gezoomt + gescrollt: Fenster folgt der Scroll-Position", () => {
    const w = visibleWindow(800, 5000, 50, 600);
    expect(w.start).toBeCloseTo(100, 0);
    expect(w.end).toBeCloseTo(116, 0);
  });
});

describe("markerPct (Change 155)", () => {
  it("Fit: Position relativ zur Gesamtdauer (wie vorher)", () => {
    const win = { start: 0, end: 1800 };
    const pct = markerPct(win, 300, 301);
    expect(pct.left).toBeCloseTo(300 / 18, 9);
    expect(pct.width).toBeCloseTo(1 / 18, 9);
  });

  it("Zoom: Wort bei 300s liegt im sichtbaren Fenster [299,302.33] → 30%", () => {
    const win = { start: 299, end: 302.33 };
    const pct = markerPct(win, 300, 301);
    expect(pct.left).toBeCloseTo((1 / 3.33) * 100, 1); // ≈ 30 %
    expect(pct.width).toBeCloseTo((1 / 3.33) * 100, 1);
  });

  it("Wort vor dem Fenster: left negativ (geclampt durch CSS overflow)", () => {
    expect(markerPct({ start: 100, end: 110 }, 90, 91).left).toBeLessThan(0);
  });
});

describe("clampMoveWordTiming (Change 155)", () => {
  it("Verschieben hält die Länge, beide Grenzen wandern", () => {
    expect(clampMoveWordTiming(1.0, 2.0, 0.5, 0.0, 5.0)).toEqual({ start: 1.5, end: 2.5 });
  });

  it("Rückwärts-Verschieben an die Nachbar-Grenze geclampt", () => {
    expect(clampMoveWordTiming(1.0, 2.0, -2.0, 0.5, 5.0)).toEqual({ start: 0.5, end: 1.5 });
  });

  it("Vorwärts-Verschieben nicht über maxEnd hinaus", () => {
    // Länge 1s, maxEnd 2.5 → start darf max. 1.5 sein (sonst ragt end drüber)
    expect(clampMoveWordTiming(1.0, 2.0, 5.0, 0.0, 2.5)).toEqual({ start: 1.5, end: 2.5 });
  });

  it("ohne Nachbarn: frei verschiebbar", () => {
    expect(clampMoveWordTiming(10, 11, 3, undefined, undefined)).toEqual({ start: 13, end: 14 });
  });
});

// ── Change 199: residentes Budget, Breitengrenze, Detailfenster ──

describe("residentes Envelope-Budget (Change 199)", () => {
  it("kurze Dateien: das Budget greift nicht, Auflösung = Detailauflösung", () => {
    expect(residentBinsPerSecond(600)).toBe(HI_BPS);
    expect(residentBinCount(600)).toBe(hiBinCount(600));
  });

  it("lange Dateien: die Nutzlast ist konstant, nicht die Auflösung", () => {
    for (const d of [3600, 15718, 36000]) {
      expect(residentBinCount(d)).toBe(RESIDENT_BIN_BUDGET);
      expect(residentBinsPerSecond(d)).toBeLessThan(HI_BPS);
    }
  });

  it("Invariante: Balken im Maximalzoom sind von der Dauer unabhängig", () => {
    // Weil sich die Dauer herauskürzt: BUDGET × Breite / 2^25.
    const erwartet = (RESIDENT_BIN_BUDGET * 1000) / MAX_ELEMENT_PX;
    for (const d of [3600, 15718]) {
      const pps = effectiveMaxPps(d);
      const fenster = 1000 / pps;                    // sichtbare Sekunden
      const balken = fenster * residentBinsPerSecond(d);
      expect(balken).toBeCloseTo(erwartet, 4);
    }
  });

  it("Auflösung sinkt monoton mit der Länge", () => {
    expect(residentBinsPerSecond(15718)).toBeLessThan(residentBinsPerSecond(3600));
    expect(residentBinsPerSecond(3600)).toBeLessThan(HI_BPS);
  });
});

describe("effectiveMaxPps (Change 199)", () => {
  it("kurze Dateien: MAX_TIMING_PPS bleibt die Grenze", () => {
    expect(effectiveMaxPps(600)).toBe(MAX_TIMING_PPS);
    expect(effectiveMaxPps(699)).toBe(MAX_TIMING_PPS);
  });

  it("ab ~11,7 min deckelt die Browser-Breite", () => {
    expect(effectiveMaxPps(720)).toBeCloseTo(MAX_ELEMENT_PX / 720, 6);
    expect(effectiveMaxPps(720)).toBeLessThan(MAX_TIMING_PPS);
  });

  it("262 min: 2135 px/s statt 48000", () => {
    expect(effectiveMaxPps(15718)).toBeCloseTo(2134.8, 1);
  });

  it("robust gegen 0/negative Dauer", () => {
    expect(effectiveMaxPps(0)).toBe(MAX_TIMING_PPS);
    expect(effectiveMaxPps(-5)).toBe(MAX_TIMING_PPS);
  });
});

describe("Detailfenster im Sidecar (Change 199)", () => {
  it("1-s-Fenster ± 50 % = 2 KB statt 6 MB", () => {
    const r = detailByteRange({ start: 100, end: 101 }, 15718);
    expect(r.start).toBe(99500);          // 100 s − 0,5 s
    expect(r.end).toBe(101499);           // 101 s + 0,5 s
    expect(r.end - r.start + 1).toBe(2000);
  });

  it("Fenster am Anfang wird nicht negativ", () => {
    const r = detailByteRange({ start: 0, end: 1 }, 100);
    expect(r.start).toBe(0);
    expect(r.end).toBe(1499);             // bis 1,5 s, nicht weiter
  });

  it("Fenster am Ende bleibt im Sidecar", () => {
    const r = detailByteRange({ start: 99, end: 100 }, 100);
    expect(r.end).toBe(hiBinCount(100) - 1);
    expect(r.start).toBeLessThanOrEqual(r.end);
  });

  it("Überabtastung deckt Scrollen bis zur Pufferbreite ohne neue Anfrage ab", () => {
    // Angefordert wird ± 50 %: bei 1 s Fenster also 99,5–101,5 s.
    const a = detailByteRange({ start: 100, end: 101 }, 15718, 0.5);
    // Verschieben um 0,5 s (die Pufferbreite) bleibt im Geladenen …
    const b = windowBinRange({ start: 100.5, end: 101.5 }, 15718);
    expect(b.start).toBeGreaterThanOrEqual(a.start);
    expect(b.end).toBeLessThanOrEqual(a.end);
    // … mehr verlangt eine neue Anfrage (sonst würde still nichts gezeichnet).
    const c = windowBinRange({ start: 101.2, end: 102.2 }, 15718);
    expect(c.end).toBeGreaterThan(a.end);
  });

  it("pad=0 liefert genau das sichtbare Fenster", () => {
    const r = detailByteRange({ start: 10, end: 11 }, 15718, 0);
    expect(r.start).toBe(10000);
    expect(r.end).toBe(10999);
    expect(r.end - r.start + 1).toBe(1000);   // 1 s bei 1000 Bins/s
  });

  it("der Puffer klebt nicht am Fenster (sonst deckt er nie etwas ab)", () => {
    // Hätte man die GEPUFFERTEN Bereiche verglichen, wäre jede Verschiebung
    // außerhalb gelegen — deshalb prüft die Komponente windowBinRange.
    const gepuffertVorher = detailByteRange({ start: 100, end: 101 }, 15718, 0.5);
    const gepuffertNachher = detailByteRange({ start: 100.1, end: 101.1 }, 15718, 0.5);
    expect(gepuffertNachher.end).toBeGreaterThan(gepuffertVorher.end);
  });
});
