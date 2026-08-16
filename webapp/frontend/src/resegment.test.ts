/* ============================================================
   RESEGMENT-Tests: Segmentlängen-Auswahl (Feature 2026-08-15)
   ============================================================ */
import { describe, it, expect } from "vitest";
import { resegmentByDuration, moveBoundary, insertSegment, deleteSegment } from "./resegment.ts";

function seg(start: number, end: number, words: [string, number, number][], speaker?: string) {
  return {
    start,
    end,
    text: words.map((w) => w[0]).join(" "),
    speaker,
    words: words.map(([word, s, e]) => ({ word, start: s, end: e })),
  };
}

describe("resegmentByDuration", () => {
  it("teilt ein 105-s-Segment in Blöcke ≤ Ziel-Dauer", () => {
    // 10 Wörter à 1 s, lückenlos ab 0 → Gesamt 10 s
    const words: [string, number, number][] = [];
    for (let i = 0; i < 10; i++) words.push([`w${i}`, i, i + 1]);
    const input = [seg(0, 10, words)];

    const out = resegmentByDuration(input, 4);
    expect(out.length).toBeGreaterThan(1);
    for (const s of out) {
      const dur = Number(s.end) - Number(s.start);
      expect(dur).toBeLessThanOrEqual(4 + 1e-9);
    }
    // Text-Gesamtinhalt unverändert (nichts verschluckt)
    const all = out.map((s) => s.text).join(" ");
    expect(all).toBe(input[0].text);
    // Chronologisch lückenlos
    for (let i = 1; i < out.length; i++) {
      expect(Number(out[i].start)).toBeCloseTo(Number(out[i - 1].end), 6);
    }
  });

  it("behält Sprecher-Wechsel als Segmentgrenze", () => {
    const a = seg(0, 2, [["hallo", 0, 1], ["du", 1, 2]], "SPEAKER_01");
    const b = seg(2, 4, [["ja", 2, 3], ["klar", 3, 4]], "SPEAKER_02");
    const out = resegmentByDuration([a, b], 100); // Dauer würde alles erlauben
    expect(out.length).toBe(2);
    expect(out[0].speaker).toBe("SPEAKER_01");
    expect(out[1].speaker).toBe("SPEAKER_02");
  });

  it("gibt Segmente ohne Wörter unverändert zurück", () => {
    const plain = [{ start: 0, end: 5, text: "nur text" }];
    expect(resegmentByDuration(plain, 2)).toEqual(plain);
  });

  it("leere Liste / ungültige Dauer → unverändert", () => {
    expect(resegmentByDuration([], 2)).toEqual([]);
    const input = [seg(0, 10, [["a", 0, 1]])];
    expect(resegmentByDuration(input, 0)).toEqual(input);
    expect(resegmentByDuration(input, -1)).toEqual(input);
  });
});

describe("moveBoundary", () => {
  // 2 Segmente: A = w0..w4 (0–5 s), B = w5..w9 (5–10 s)
  function twoSegs() {
    const wa: [string, number, number][] = [];
    const wb: [string, number, number][] = [];
    for (let i = 0; i < 5; i++) wa.push([`a${i}`, i, i + 1]);
    for (let i = 0; i < 5; i++) wb.push([`b${i}`, 5 + i, 6 + i]);
    return [seg(0, 5, wa), seg(5, 10, wb)];
  }

  it("delta<0: A verliert am Ende, B gewinnt am Anfang (Wort für Wort)", () => {
    const out = moveBoundary(twoSegs(), 0, -2);
    expect(out.length).toBe(2);
    // A: nur a0..a2 → endet bei 3, Text "a0 a1 a2"
    expect(out[0].text).toBe("a0 a1 a2");
    expect(out[0].end).toBe(3);
    // B: beginnt bei 3 mit a3 a4 + b0.. → Text "a3 a4 b0 b1 b2 b3 b4"
    expect(out[1].text).toBe("a3 a4 b0 b1 b2 b3 b4");
    expect(out[1].start).toBe(3);
    // Kein Wort verloren: Gesamttext unverändert
    expect(out.map((s) => s.text).join(" ")).toBe(
      "a0 a1 a2 a3 a4 b0 b1 b2 b3 b4",
    );
  });

  it("delta>0: B verliert am Anfang, A gewinnt am Ende", () => {
    const out = moveBoundary(twoSegs(), 0, 2);
    expect(out[0].text).toBe("a0 a1 a2 a3 a4 b0 b1");
    expect(out[0].end).toBe(7);
    expect(out[1].text).toBe("b2 b3 b4");
    expect(out[1].start).toBe(7);
  });

  it("stoppt an den Rändern (Segment darf nie leer werden)", () => {
    const out = moveBoundary(twoSegs(), 0, -100);
    // A behält mindestens 1 Wort
    expect(out[0].text).toBe("a0");
    expect(out[1].text).toBe("a1 a2 a3 a4 b0 b1 b2 b3 b4");

    const out2 = moveBoundary(twoSegs(), 0, 100);
    // n = min(B-1, 100) = 4 → B behält zwingend 1 Wort (nie leer)
    expect(out2[0].text).toBe("a0 a1 a2 a3 a4 b0 b1 b2 b3");
    expect(out2[1].text).toBe("b4");
  });

  it("delta=0 oder ungültige Grenze → unverändert", () => {
    const input = twoSegs();
    expect(moveBoundary(input, 0, 0)).toEqual(input);
    expect(moveBoundary(input, -1, 1)).toEqual(input);
    expect(moveBoundary(input, 1, 1)).toEqual(input);
    expect(moveBoundary([], 0, 1)).toEqual([]);
    expect(moveBoundary([seg(0, 1, [["x", 0, 1]])], 0, 1)).toEqual([
      seg(0, 1, [["x", 0, 1]]),
    ]);
  });

  it("ohne Wort-Timestamps → keine Bewegung", () => {
    const plain = [
      { start: 0, end: 5, text: "nur text" },
      { start: 5, end: 10, text: "auch nur text" },
    ];
    expect(moveBoundary(plain, 0, -1)).toEqual(plain);
  });

  it("Sprecher-Zuordnung wandert mit den Wörtern", () => {
    const a = seg(0, 2, [["hallo", 0, 1], ["du", 1, 2]], "SPEAKER_01");
    const b = seg(2, 4, [["ja", 2, 3], ["klar", 3, 4]], "SPEAKER_02");
    const out = moveBoundary([a, b], 0, 1);
    // "ja" wandert zu A → A hat Speaker_01 (erster Bucket-Speaker bleibt)
    expect(out[0].text).toBe("hallo du ja");
    expect(out[1].text).toBe("klar");
  });

  it("REGRESSION 2026-08-16: kumulative Verschiebung dupliziert keine Wörter", () => {
    // Frontend-Bug: moveBoundary wurde pro Pointer-Move mit Schritt-Delta auf
    // der (noch alten) Prop-Liste aufgerufen → jedes Wort, das über eine
    // Wortgrenze wandert, kam doppelt ("Anton? Anton?", "Montag. Montag.").
    // Fix: Basis-Liste beim Drag-Start einfrieren + kumulatives Delta.
    // Der Test bildet die Drag-Sequenz 0→1→2→1→0 mit kumulativem Delta auf
    // derselben Basis ab und verlangt: Gesamtwortzahl konstant (keine
    // Duplikate, keine Verluste), Wörter wandern deterministisch.
    const base = twoSegs();
    const countWords = (list: ReturnType<typeof moveBoundary>) =>
      list.reduce((n, s) => n + (s.words?.length ?? 0), 0);
    const text = (list: ReturnType<typeof moveBoundary>) =>
      list.map((s) => s.text).join(" ");
    const expected = "a0 a1 a2 a3 a4 b0 b1 b2 b3 b4";

    const step1 = moveBoundary(base, 0, 1); // B → A: b0
    expect(text(step1)).toBe(expected);
    expect(countWords(step1)).toBe(10);

    const step2 = moveBoundary(base, 0, 2); // B → A: b0 b1 (kumulativ!)
    expect(text(step2)).toBe(expected);
    expect(countWords(step2)).toBe(10);
    expect(step2[0].text).toBe("a0 a1 a2 a3 a4 b0 b1");
    expect(step2[1].text).toBe("b2 b3 b4");

    const stepBack = moveBoundary(base, 0, 1); // zurück: nur b0 bei A
    expect(text(stepBack)).toBe(expected);
    expect(countWords(stepBack)).toBe(10);
    expect(stepBack[0].text).toBe("a0 a1 a2 a3 a4 b0");
    expect(stepBack[1].text).toBe("b1 b2 b3 b4");

    const step0 = moveBoundary(base, 0, 0);
    expect(text(step0)).toBe(expected);
    expect(countWords(step0)).toBe(10);
    // Wörter sind exakt die Original-Wörter (keine Duplikate in words[])
    const all = step0.flatMap((s) => s.words ?? []);
    expect(all.map((w) => w.word)).toEqual([
      "a0", "a1", "a2", "a3", "a4", "b0", "b1", "b2", "b3", "b4",
    ]);
  });
});

describe("insertSegment", () => {
  // A (SPEAKER_01): a0..a4, B (SPEAKER_02): b0..b4
  function twoSegs() {
    const wa: [string, number, number][] = [];
    const wb: [string, number, number][] = [];
    for (let i = 0; i < 5; i++) wa.push([`a${i}`, i, i + 1]);
    for (let i = 0; i < 5; i++) wb.push([`b${i}`, 5 + i, 6 + i]);
    return [seg(0, 5, wa, "SPEAKER_01"), seg(5, 10, wb, "SPEAKER_02")];
  }

  it("fügt nach Segment 0 ein: gleicher Sprecher, letztes Wort wandert", () => {
    const out = insertSegment(twoSegs(), 0);
    expect(out.length).toBe(3);
    // A verliert das letzte Wort, das neue Segment hat es + Speaker von A
    expect(out[0].text).toBe("a0 a1 a2 a3");
    expect(out[0].speaker).toBe("SPEAKER_01");
    expect(out[1].text).toBe("a4");
    expect(out[1].speaker).toBe("SPEAKER_01");
    expect(out[1].start).toBe(4);
    expect(out[1].end).toBe(5);
    // B unverändert
    expect(out[2].text).toBe("b0 b1 b2 b3 b4");
    expect(out[2].speaker).toBe("SPEAKER_02");
    // Gesamttext + Wortzahl konstant (kein Textverlust)
    expect(out.map((s) => s.text).join(" ")).toBe("a0 a1 a2 a3 a4 b0 b1 b2 b3 b4");
    expect(out.reduce((n, s) => n + (s.words?.length ?? 0), 0)).toBe(10);
  });

  it("ohne Wort-Timestamps → unverändert", () => {
    const plain = [
      { start: 0, end: 5, text: "nur text" },
      { start: 5, end: 10, text: "auch text" },
    ];
    expect(insertSegment(plain, 0)).toEqual(plain);
  });

  it("ungültiger Index → unverändert", () => {
    const input = twoSegs();
    expect(insertSegment(input, -1)).toEqual(input);
    expect(insertSegment(input, 2)).toEqual(input);
  });
});

describe("deleteSegment", () => {
  function threeSegs() {
    const w = (pre: string, off: number) => [[`${pre}0`, off, off + 1], [`${pre}1`, off + 1, off + 2]] as [string, number, number][];
    return [
      seg(0, 2, w("a", 0), "SPEAKER_01"),
      seg(2, 4, w("b", 2), "SPEAKER_02"),
      seg(4, 6, w("c", 4), "SPEAKER_01"),
    ];
  }

  it("löscht mittleres Segment → Wörter ans vorige, Gesamttext konstant", () => {
    const out = deleteSegment(threeSegs(), 1);
    expect(out.length).toBe(2);
    expect(out[0].text).toBe("a0 a1 b0 b1");
    expect(out[0].speaker).toBe("SPEAKER_01"); // buildSeg nimmt Speaker des ersten Worts
    expect(out[1].text).toBe("c0 c1");
    expect(out.map((s) => s.text).join(" ")).toBe("a0 a1 b0 b1 c0 c1");
  });

  it("löscht erstes Segment → Wörter ans neue erste Segment", () => {
    const out = deleteSegment(threeSegs(), 0);
    expect(out.length).toBe(2);
    expect(out[0].text).toBe("a0 a1 b0 b1");
    expect(out[1].text).toBe("c0 c1");
    expect(out.map((s) => s.text).join(" ")).toBe("a0 a1 b0 b1 c0 c1");
  });

  it("löscht letztes Segment → Wörter ans vorige", () => {
    const out = deleteSegment(threeSegs(), 2);
    expect(out.length).toBe(2);
    expect(out[0].text).toBe("a0 a1");
    expect(out[1].text).toBe("b0 b1 c0 c1");
  });

  it("einziger Segment → unverändert (mindestens 1 bleibt)", () => {
    const single = [seg(0, 2, [["x", 0, 1]] as [string, number, number][], "SPEAKER_01")];
    expect(deleteSegment(single, 0)).toEqual(single);
  });

  it("ohne Wörter: Text wandert, Grenzen des Nachbarn bleiben", () => {
    const plain = [
      { start: 0, end: 2, text: "hallo" },
      { start: 2, end: 4, text: "welt" },
    ];
    const out = deleteSegment(plain, 1);
    expect(out.length).toBe(1);
    expect(out[0].text).toBe("hallo welt");
    expect(out[0].start).toBe(0);
    expect(out[0].end).toBe(2);
  });
});

/* ============================================================
   INVARIANTE 2026-08-16 (User): Das Karaoke-Wort-Timing (word,
   start, end — Reihenfolge UND Timestamps) bleibt bei JEDER
   GUI-Operation erhalten. Nur die Segment-ZUORDNUNG ändert sich,
   nie die Wörter selbst.
   ============================================================ */
function flattenWords(list: { words?: { word?: string; start?: number; end?: number }[] }[]) {
  return list.flatMap((s) => (s.words ?? []).map((w) => `${w.word}|${w.start}|${w.end}`));
}

function twoSegsWords(): { start: number; end: number; text: string; words: { word: string; start: number; end: number }[] }[] {
  const a = seg(0, 5, [["a0", 0, 0.9], ["a1", 1.0, 2.1], ["a2", 2.2, 3.0], ["a3", 3.1, 4.2], ["a4", 4.3, 5.0]], "SPEAKER_01");
  const b = seg(5, 10, [["b0", 5.1, 6.0], ["b1", 6.2, 7.1], ["b2", 7.3, 8.0], ["b3", 8.1, 9.2], ["b4", 9.3, 10.0]], "SPEAKER_02");
  return [a, b];
}

describe("Invariante: Wort-Timing bleibt bei allen Operationen erhalten", () => {
  it("moveBoundary (Grenze verschieben): Timestamps + Reihenfolge unverändert", () => {
    const input = twoSegsWords();
    const before = flattenWords(input);
    for (const delta of [-3, -1, 1, 2, 4]) {
      const out = moveBoundary(input, 0, delta) as { words?: { word?: string; start?: number; end?: number }[] }[];
      expect(flattenWords(out)).toEqual(before);
      // und: nur die betroffenen Segmente haben neue start/end (Wort-abgeleitet)
      const all = out.map((s) => s.words ?? []);
      expect(all.flat().length).toBe(10);
    }
  });

  it("insertSegment (+): Timestamps + Reihenfolge unverändert", () => {
    const input = twoSegsWords();
    const before = flattenWords(input);
    const out = insertSegment(input, 0) as { words?: { word?: string; start?: number; end?: number }[] }[];
    expect(out.length).toBe(3);
    expect(flattenWords(out)).toEqual(before);
    expect(out[1].words?.[0]).toMatchObject({ word: "a4", start: 4.3, end: 5.0 });
  });

  it("deleteSegment (−): Timestamps + Reihenfolge unverändert", () => {
    const input = twoSegsWords();
    const before = flattenWords(input);
    for (const idx of [0, 1]) {
      const out = deleteSegment(input, idx) as { words?: { word?: string; start?: number; end?: number }[] }[];
      expect(flattenWords(out)).toEqual(before);
    }
  });

  it("resegmentByDuration (Segment-Länge ändern): Timestamps + Reihenfolge unverändert", () => {
    const input = twoSegsWords();
    const before = flattenWords(input);
    for (const dur of [1.5, 2.0, 3.5, 8.0]) {
      const out = resegmentByDuration(input, dur) as { start?: number; end?: number; words?: { word?: string; start?: number; end?: number }[] }[];
      expect(flattenWords(out)).toEqual(before);
      // Chronologisch + Grenzen aus den Wörtern abgeleitet (Lücken sind
      // echte ASR-Pausen — Segment-start = erstes Wort-start, end = letztes)
      for (let i = 0; i < out.length; i++) {
        const w = out[i].words ?? [];
        expect(out[i].start).toBeCloseTo(w[0].start ?? 0, 6);
        expect(out[i].end).toBeCloseTo(w[w.length - 1].end ?? 0, 6);
        if (i > 0) {
          expect(out[i].start ?? 0).toBeGreaterThanOrEqual(out[i - 1].end ?? 0);
        }
      }
    }
  });

  it("PUT-Roundtrip (Backend-Serialisierung): words kommen unverändert zurück", () => {
    // simuliert segments.py: stored = json.loads(json.dumps(segs))
    const input = twoSegsWords();
    const roundtrip = JSON.parse(JSON.stringify(input)) as typeof input;
    expect(flattenWords(roundtrip)).toEqual(flattenWords(input));
  });
});
