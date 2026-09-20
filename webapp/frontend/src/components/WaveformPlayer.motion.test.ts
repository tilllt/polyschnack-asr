/**
 * Change 217 (Nutzer-Vorgabe 20.09.2026): animierte Übergänge beim Wortwechsel
 * im Timing-Modus. Wörtlich: „… es zoomt rein (oder raus), die Markierung
 * wechselt ihre Farbe von Nachbar zu markiertem Wort, markiertes Wort wechselt
 * auf Nachbarfarbe, Zentrierung scrollt smooth (mit ease out)?"
 *
 * Geprüft wird die MASCHINERIE, nicht die Optik: weiche Kurve, Zwischenwerte,
 * Zoom und Zentrierung in DENSELBEN Bildern (eine Bewegung), Abbruch beim
 * nächsten Klick (danach schreibt kein Bild mehr) und reduzierte Bewegung
 * (Endwert sofort, keine Animation).
 *
 * Die Farbgleitung selbst macht CSS — hier wird nur geprüft, dass Start- und
 * Zielwert so gesetzt werden, dass der Browser dazwischen gleiten kann.
 */
import { describe, expect, it } from "vitest";
import {
  TIMING_ACTIVE_REGION,
  TIMING_MOTION_MS,
  TIMING_NEIGHBOR_REGION,
  animateTimingView,
  crossfadeStyle,
  easeOutCubic,
  lerp,
  reduceMotionRequested,
} from "./WaveformPlayer";

/** Handgesteuerte „Zeit + Bilder" — kein Timer, voll deterministisch. */
function fakeClock() {
  let t = 0;
  let nextId = 0;
  const frames = new Map<number, (x: number) => void>();
  return {
    raf: (cb: (x: number) => void) => {
      nextId += 1;
      frames.set(nextId, cb);
      return nextId;
    },
    cancelRaf: (id: number) => {
      frames.delete(id);
    },
    tick: (ms: number) => {
      t += ms;
      const due = Array.from(frames.entries());
      frames.clear();
      for (const [, cb] of due) cb(t);
    },
    now: () => t,
    pending: () => frames.size,
  };
}

describe("Change 217 — weiche Kurve (Ease-out)", () => {
  it("Start 0, Ende 1, in der Mitte weiter als linear", () => {
    expect(easeOutCubic(0)).toBe(0);
    expect(easeOutCubic(1)).toBe(1);
    // Ease-out: nach der halben Zeit ist mehr als die halbe Strecke geschafft
    expect(easeOutCubic(0.5)).toBeGreaterThan(0.5);
  });

  it("klemmt über das Ziel hinaus — nie über 1 oder unter 0", () => {
    expect(easeOutCubic(1.7)).toBe(1);
    expect(easeOutCubic(-0.3)).toBe(0);
  });

  it("lerp liefert Zwischenwerte zwischen Start und Ziel", () => {
    expect(lerp(10, 20, 0)).toBe(10);
    expect(lerp(10, 20, 0.5)).toBe(15);
    expect(lerp(10, 20, 1)).toBe(20);
  });

  it("reduzierte Bewegung ist abfragbar und wirft nie", () => {
    expect(typeof reduceMotionRequested()).toBe("boolean");
  });
});

describe("Change 217 — Zoom + Zentrierung als EINE Fahrt", () => {
  it("setzt Zwischenwerte und am Ende exakt den Zielwert", () => {
    const c = fakeClock();
    const applied: Array<[number, number]> = [];
    animateTimingView({
      from: { pps: 5, scroll: 0 },
      to: { pps: 100, scroll: 4000 },
      raf: c.raf,
      cancelRaf: c.cancelRaf,
      now: c.now,
      apply: (p, s) => applied.push([p, s]),
    });

    c.tick(0); // erstes Bild: steht noch am Ausgangswert
    c.tick(TIMING_MOTION_MS / 2); // halbe Zeit
    expect(applied.length).toBe(2);
    expect(applied[0]).toEqual([5, 0]);
    const [midPps, midScroll] = applied[1];
    expect(midPps).toBeGreaterThan(5);
    expect(midPps).toBeLessThan(100);
    // Zentrierung läuft in DENSELBEN Bildern mit (eine Bewegung, nicht zwei)
    expect(midScroll).toBeGreaterThan(0);
    expect(midScroll).toBeLessThan(4000);

    c.tick(TIMING_MOTION_MS / 2); // Ende
    expect(applied[applied.length - 1]).toEqual([100, 4000]);
    expect(c.pending()).toBe(0); // Fahrt beendet: kein Bild mehr offen
  });

  it("Abbruch beim nächsten Klick: danach schreibt kein Bild mehr", () => {
    const c = fakeClock();
    const applied: number[] = [];
    const cancel = animateTimingView({
      from: { pps: 5, scroll: 0 },
      to: { pps: 100, scroll: 4000 },
      raf: c.raf,
      cancelRaf: c.cancelRaf,
      now: c.now,
      apply: (p) => applied.push(p),
    });
    c.tick(0);
    c.tick(TIMING_MOTION_MS / 3);
    const before = applied.length;
    expect(before).toBe(2);

    cancel();
    c.tick(TIMING_MOTION_MS);
    expect(applied.length).toBe(before); // kein Nachlauf
    expect(c.pending()).toBe(0);
  });

  it("reduzierte Bewegung: Endwert sofort, ohne Bild", () => {
    const c = fakeClock();
    const applied: Array<[number, number]> = [];
    const cancel = animateTimingView({
      from: { pps: 5, scroll: 0 },
      to: { pps: 100, scroll: 4000 },
      reduced: true,
      raf: c.raf,
      cancelRaf: c.cancelRaf,
      now: c.now,
      apply: (p, s) => applied.push([p, s]),
    });
    expect(applied).toEqual([[100, 4000]]);
    expect(c.pending()).toBe(0);
    expect(() => cancel()).not.toThrow();
  });

  it("meldet dem Aufrufer den Endstand (sichtbares Fenster)", () => {
    const c = fakeClock();
    const done: Array<[number, number]> = [];
    const applied: Array<[number, number]> = [];
    animateTimingView({
      from: { pps: 5, scroll: 0 },
      to: { pps: 100, scroll: 4000 },
      raf: c.raf,
      cancelRaf: c.cancelRaf,
      now: c.now,
      apply: (p, s) => applied.push([p, s]),
      done: (p, s) => done.push([p, s]),
    });
    c.tick(0);
    expect(done).toEqual([]);
    c.tick(TIMING_MOTION_MS);
    expect(done).toEqual([[100, 4000]]);
  });
});

describe("Change 217 — Farbgleitung (interpoliert der Browser per CSS)", () => {
  it("setzt den Startwert ohne Übergang und danach den Zielwert", async () => {
    const el = document.createElement("div");
    document.body.appendChild(el);
    el.style.backgroundColor = TIMING_ACTIVE_REGION;

    crossfadeStyle(el, "backgroundColor", TIMING_NEIGHBOR_REGION, TIMING_ACTIVE_REGION);

    // Startwert steht sofort; die Übergangs-Sperre ist wieder abgenommen,
    // damit CSS von hier zum Zielwert gleiten kann.
    const startVal = el.style.backgroundColor;
    expect(startVal).not.toBe("");
    expect(startVal).not.toBe(TIMING_ACTIVE_REGION);
    expect(el.classList.contains("ps-no-transition")).toBe(false);

    await new Promise<void>((r) => {
      if (typeof requestAnimationFrame === "function") requestAnimationFrame(() => r());
      else r();
    });

    expect(el.style.backgroundColor).not.toBe(startVal); // Zielwert gesetzt
    el.remove();
  });

  it("ohne Element (Fläche schon weg) passiert nichts", () => {
    expect(() => crossfadeStyle(null, "color", "#7ee787", "#ffffff")).not.toThrow();
    expect(() => crossfadeStyle(undefined, "backgroundColor", "#000", "#fff")).not.toThrow();
  });
});
