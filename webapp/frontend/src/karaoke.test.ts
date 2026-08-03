/* ============================================================
   KARAOKE-Tests: Wort-Hervorhebung nach Diarization-Merge & Edit
   ============================================================ */
import { describe, it, expect } from "vitest";
import {
  isWordActive,
  activeWordIndex,
  activeSegmentIndex,
  isKaraokeReady,
  shouldScrollIntoView,
  type KaraokeSegment,
} from "./karaoke.ts";

describe("isWordActive (Karaoke-Highlight-Regel)", () => {
  it("highlightet Wörter während ihres Zeitfensters", () => {
    const w = { word: "hallo", start: 1.0, end: 2.0 };
    expect(isWordActive(w, 0.5)).toBe(false); // vor dem Wort
    expect(isWordActive(w, 1.0)).toBe(true); // start inklusive
    expect(isWordActive(w, 1.5)).toBe(true); // mitten im Wort
    expect(isWordActive(w, 2.0)).toBe(false); // end exklusive
    expect(isWordActive(w, 3.0)).toBe(false); // nach dem Wort
  });

  it("funktioniert mit Merge/Edit-Wörtern (float-Timestamps)", () => {
    const w = { word: "weiblich", start: 4.32, end: 6.24 };
    expect(isWordActive(w, 4.319)).toBe(false);
    expect(isWordActive(w, 4.32)).toBe(true);
    expect(isWordActive(w, 6.239)).toBe(true);
    expect(isWordActive(w, 6.24)).toBe(false);
  });

  it("behandelt 0-Dauer-Wörter (defekt) als nie aktiv", () => {
    const w = { word: "x", start: 2.0, end: 2.0 };
    expect(isWordActive(w, 2.0)).toBe(false);
  });
});

describe("activeWordIndex (lückenlose Karaoke-Markierung — Glitch-Fix)", () => {
  const words = [
    { word: "hallo", start: 0.0, end: 1.0 },
    { word: "hier", start: 1.0, end: 2.0 },
    { word: "spricht", start: 2.0, end: 3.0 },
  ];

  it("wandert nahtlos durch aufeinanderfolgende Wörter", () => {
    expect(activeWordIndex(words, 0.0)).toBe(0);
    expect(activeWordIndex(words, 0.99)).toBe(0);
    expect(activeWordIndex(words, 1.0)).toBe(1); // exakte Grenze → nächstes
    expect(activeWordIndex(words, 2.0)).toBe(2);
    expect(activeWordIndex(words, 5.0)).toBe(2); // nach dem Ende → letztes
  });

  it("KEIN Glitch bei Timestamp-Lücken (kein Wort-Ausfall)", () => {
    // w[0].end=1.0, w[1].start=1.2 → Lücke 1.0–1.2
    const gappy = [
      { word: "a", start: 0.0, end: 1.0 },
      { word: "b", start: 1.2, end: 2.0 },
    ];
    // Alte isWordActive-Logik: bei t=1.1 wäre KEIN Wort aktiv (Glitch)
    expect(isWordActive(gappy[0], 1.1)).toBe(false);
    expect(isWordActive(gappy[1], 1.1)).toBe(false);
    // Neue Logik: das letzte gestartete Wort bleibt aktiv → kein Sprung
    expect(activeWordIndex(gappy, 1.1)).toBe(0);
    expect(activeWordIndex(gappy, 1.2)).toBe(1);
  });

  it("KEIN Doppel-Highlight bei Überlappungen (neueres Wort gewinnt)", () => {
    // w[0].end=1.5, w[1].start=1.2 → Überlappung 1.2–1.5
    const overlap = [
      { word: "a", start: 0.0, end: 1.5 },
      { word: "b", start: 1.2, end: 2.0 },
    ];
    expect(isWordActive(overlap[0], 1.3)).toBe(true);
    expect(isWordActive(overlap[1], 1.3)).toBe(true);
    // Neue Logik: genau EIN aktives Wort
    expect(activeWordIndex(overlap, 1.3)).toBe(1);
  });

  it("vor dem ersten Wort → -1 (nichts aktiv)", () => {
    expect(activeWordIndex(words, -0.5)).toBe(-1);
  });

  it("leere/fehlende Wortliste → -1", () => {
    expect(activeWordIndex([], 1.0)).toBe(-1);
    expect(activeWordIndex(undefined, 1.0)).toBe(-1);
  });
});

describe("activeSegmentIndex (Auto-Scroll + Karaoke-Basis)", () => {
  const segments: KaraokeSegment[] = [
    { start: 0.0, end: 4.32, text: "A" },
    { start: 4.32, end: 6.24, text: "B" },
    { start: 6.24, end: 21.44, text: "C" },
  ];

  it("findet das Segment zur aktuellen Zeit", () => {
    expect(activeSegmentIndex(segments, 0.0)).toBe(0);
    expect(activeSegmentIndex(segments, 4.319)).toBe(0);
    expect(activeSegmentIndex(segments, 4.32)).toBe(1);
    expect(activeSegmentIndex(segments, 10.0)).toBe(2);
  });

  it("liefert -1 vor dem ersten Segment", () => {
    expect(activeSegmentIndex(segments, -1)).toBe(-1);
  });

  it("bleibt nach dem Ende am letzten Segment", () => {
    expect(activeSegmentIndex(segments, 25.0)).toBe(2);
  });

  it("leere Liste → -1", () => {
    expect(activeSegmentIndex([], 1.0)).toBe(-1);
  });
});

describe("isKaraokeReady (nach Merge/Edit)", () => {
  it("true wenn alle Wörter gültige Timestamps haben", () => {
    const seg: KaraokeSegment = {
      start: 0, end: 2, text: "a b",
      words: [
        { word: "a", start: 0.0, end: 1.0 },
        { word: "b", start: 1.0, end: 2.0 },
      ],
    };
    expect(isKaraokeReady(seg)).toBe(true);
  });

  it("false wenn Wörter ohne Timestamps (z.B. proportionaler Fallback)", () => {
    const seg: KaraokeSegment = {
      start: 0, end: 2, text: "a b",
      words: [{ word: "a" }, { word: "b" }] as unknown as KaraokeSegment["words"],
    };
    expect(isKaraokeReady(seg)).toBe(false);
  });

  it("false bei leerer Wortliste oder fehlendem words-Feld", () => {
    expect(isKaraokeReady({ start: 0, end: 2, text: "x" })).toBe(false);
    expect(isKaraokeReady({ start: 0, end: 2, text: "x", words: [] })).toBe(false);
  });
});

describe("shouldScrollIntoView (Autoscroll-Entscheidung)", () => {
  // Container: scrollTop=100, clientHeight=200 → sichtbarer Bereich 100..300
  it("scrollt, wenn Segment unten abgeschnitten ist (top sichtbar, bottom nicht)", () => {
    expect(shouldScrollIntoView(100, 200, 250, 340)).toBe(true);
  });
  it("scrollt nicht, wenn Segment vollständig sichtbar", () => {
    expect(shouldScrollIntoView(100, 200, 120, 280)).toBe(false);
  });
  it("scrollt, wenn Segment oberhalb des Viewports liegt", () => {
    expect(shouldScrollIntoView(100, 200, 40, 90)).toBe(true);
  });
  it("scrollt nicht, wenn es kein aktives Segment gibt (NaN-Positionen)", () => {
    expect(shouldScrollIntoView(100, 200, NaN, NaN)).toBe(false);
  });
  it("scrollt nicht bei leerem/0-Container", () => {
    expect(shouldScrollIntoView(0, 0, 10, 20)).toBe(false);
  });
});
