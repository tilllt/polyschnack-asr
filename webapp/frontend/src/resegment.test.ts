/* ============================================================
   RESEGMENT-Tests: Segmentlängen-Auswahl (Feature 2026-08-15)
   ============================================================ */
import { describe, it, expect } from "vitest";
import { resegmentByDuration, moveBoundary } from "./resegment.ts";

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
});
