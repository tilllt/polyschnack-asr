/** Change 209: Nachbar-Marker (n-1/n+1) und ihr Mitschrumpfen. */
import { describe, expect, test } from "vitest";
import type { Segment } from "./api";
import { neighborWords, shrinkNeighborEdges, type TimingNeighbor } from "./timingNeighbors";

const SEGS: Segment[] = [
  {
    start: 0,
    end: 2,
    text: "Hallo Welt",
    words: [
      { word: "Hallo", start: 0, end: 1 },
      { word: "Welt", start: 1, end: 2 },
    ],
  },
  {
    start: 2,
    end: 4,
    text: "zweiter Satz",
    words: [
      { word: "zweiter", start: 2, end: 3 },
      { word: "Satz", start: 3, end: 4 },
    ],
  },
] as unknown as Segment[];

describe("neighborWords", () => {
  test("Wort in der Mitte: beide Nachbarn", () => {
    const { prev, next } = neighborWords(SEGS, 0, 1); // „Welt"
    expect(prev?.text).toBe("Hallo");
    expect(next?.text).toBe("zweiter");
    expect(next?.segIdx).toBe(1); // segmentübergreifend gefunden
  });

  test("erstes Wort eines Segments: Vorgänger aus dem Segment davor", () => {
    const { prev, next } = neighborWords(SEGS, 1, 0); // „zweiter"
    expect(prev?.text).toBe("Welt");
    expect(prev?.segIdx).toBe(0);
    expect(prev?.wordIdx).toBe(1);
    expect(next?.text).toBe("Satz");
  });

  test("Rand der Aufnahme: kein Nachbar", () => {
    expect(neighborWords(SEGS, 0, 0).prev).toBeNull();
    expect(neighborWords(SEGS, 1, 1).next).toBeNull();
  });

  test("defensiv: fehlende Segmente/Wörter", () => {
    expect(neighborWords(null, 0, 0)).toEqual({ prev: null, next: null });
    expect(neighborWords(SEGS, 5, 0)).toEqual({ prev: null, next: null });
  });
});

const PREV: TimingNeighbor = { segIdx: 0, wordIdx: 0, text: "Hallo", start: 0, end: 1 };
const NEXT: TimingNeighbor = { segIdx: 1, wordIdx: 0, text: "zweiter", start: 2, end: 3 };

describe("shrinkNeighborEdges", () => {
  test("Start nach links: Vorgänger endet am neuen Wortanfang", () => {
    const { prev, next } = shrinkNeighborEdges({ start: 0.5, end: 2 }, PREV, NEXT);
    expect(prev?.end).toBeCloseTo(0.5, 6);
    expect(prev?.start).toBe(0); // Anfang bleibt
    expect(next).toEqual(NEXT); // nicht berührt
  });

  test("Ende nach rechts: Nachfolger beginnt am neuen Wortende", () => {
    const { prev, next } = shrinkNeighborEdges({ start: 1, end: 2.5 }, PREV, NEXT);
    expect(next?.start).toBeCloseTo(2.5, 6);
    expect(next?.end).toBe(3); // Ende bleibt
    expect(prev).toEqual(PREV);
  });

  test("weit über den Vorgänger hinaus: er behält die Mindestdauer", () => {
    const { prev } = shrinkNeighborEdges({ start: -5, end: 2 }, PREV, NEXT);
    expect(prev?.end).toBeCloseTo(0.02, 6); // 0 + MIN_WORD_DURATION_S
  });

  test("kleiner ziehen lässt die Nachbarn unangetastet (kein Nachwachsen)", () => {
    const { prev, next } = shrinkNeighborEdges({ start: 1.2, end: 1.6 }, PREV, NEXT);
    expect(prev).toEqual(PREV);
    expect(next).toEqual(NEXT);
  });

  test("GANZE Markierung nach links: nur der Vorgänger schrumpft", () => {
    // Körper-Zug (start UND end wandern gleich): der Nachbar rechts bleibt.
    const { prev, next } = shrinkNeighborEdges({ start: 0.5, end: 1.5 }, PREV, NEXT);
    expect(prev?.end).toBeCloseTo(0.5, 6);
    expect(next).toEqual(NEXT);
  });

  test("GANZE Markierung nach rechts: nur der Nachfolger rückt nach", () => {
    const { prev, next } = shrinkNeighborEdges({ start: 1.5, end: 2.5 }, PREV, NEXT);
    expect(next?.start).toBeCloseTo(2.5, 6);
    expect(prev).toEqual(PREV);
  });

  test("beide Kanten gleichzeitig: beide Nachbarn schrumpfen", () => {
    const { prev, next } = shrinkNeighborEdges({ start: 0.5, end: 2.5 }, PREV, NEXT);
    expect(prev?.end).toBeCloseTo(0.5, 6);
    expect(next?.start).toBeCloseTo(2.5, 6);
  });

  test("ohne Nachbarn kein Fehler", () => {
    expect(shrinkNeighborEdges({ start: 0, end: 1 }, null, null)).toEqual({
      prev: null,
      next: null,
    });
  });
});
