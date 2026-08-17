/* ============================================================
   RESEGMENT-Tests: Segmentlängen-Auswahl (Feature 2026-08-15)
   ============================================================ */
import { describe, it, expect } from "vitest";
import { resegmentByDuration, moveBoundary, insertSegment, deleteSegment, splitSegmentAtRange, deriveSegments, wordRangeToCharRange } from "./resegment.ts";

function seg(start: number, end: number, words: [string, number, number][], speaker?: string) {
  return {
    start,
    end,
    text: words.map((w) => w[0]).join(" "),
    speaker,
    words: words.map(([word, s, e]) => ({ word, start: s, end: e })),
  };
}

describe("deriveSegments (Change 009: Anzeige = reine Funktion des Modells)", () => {
  // 10 Wörter à 1 s lückenlos ab 0 → 10-s-Segment (wird bei Dauer 4 in 3+ Buckets geteilt)
  const words: [string, number, number][] = [];
  for (let i = 0; i < 10; i++) words.push([`w${i}`, i, i + 1]);
  const input = [seg(0, 10, words)];

  it("segments_manual=true → segments DIREKT (keine Re-Segmentierung)", () => {
    const out = deriveSegments(input, 4, true);
    // Manuelle Aufteilung ist die Wahrheit — die Segmentlänge darf sie
    // nicht mehr zerlegen (Bug-Klasse „Anzeige springt zurück").
    expect(out).toBe(input);
    expect(out.length).toBe(1);
  });

  it("segments_manual=false + Segmentlänge → resegmentByDuration (Auto-Vorschau)", () => {
    const out = deriveSegments(input, 4, false);
    expect(out.length).toBeGreaterThan(1);
    for (const s of out as { start?: unknown; end?: unknown }[]) {
      expect(Number(s.end) - Number(s.start)).toBeLessThanOrEqual(4 + 1e-9);
    }
  });

  it("segments_manual=false + keine Segmentlänge → segments direkt", () => {
    const out = deriveSegments(input, null, false);
    expect(out).toBe(input);
    expect(out.length).toBe(1);
  });

  it("null/leere Liste → []", () => {
    expect(deriveSegments(null, 4, false)).toEqual([]);
    expect(deriveSegments(undefined, null, true)).toEqual([]);
    expect(deriveSegments([], 4, false)).toEqual([]);
  });

  it("segments_manual=true + keine Segmentlänge → segments direkt", () => {
    const out = deriveSegments(input, null, true);
    expect(out).toBe(input);
  });

  it("Anzeige == Modell nach jedem Commit (kein Desync-Pfad möglich)", () => {
    // Simuliert den Commit: Modell enthält die manuelle Liste + Flag true.
    const manual = [seg(0, 10, words)]; // z. B. vom Server nach PUT zurück
    const out = deriveSegments(manual, 4, true);
    expect(out).toBe(manual); // exakt dieselbe Referenz — Anzeige kann nicht abweichen
  });
});

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

  it("REPRO 2026-08-17: ZWEI Grenzen nacheinander — zweiter Drag auf dem Ergebnis des ersten (keine Duplikate)", () => {
    // UI-Ablauf nach dem 16.08.-Fix: Drag 1 (Grenze 0) → onBoundaryDragEnd
    // speichert `d.currentList`; der NÄCHSTE Drag beginnt auf DER GESPEICHERTEN
    // Liste (nicht auf der Original-Basis — die ist pro Drag neu eingefroren).
    // Reproduziert die Sequenz Grenze-0-ziehen → Grenze-1-ziehen auf dem
    // Ergebnis. Wortzahl + Wort-Menge müssen konstant bleiben.
    // 3 Segmente: A(a0..a2) B(b0..b2) C(c0..c2)
    const wa: [string, number, number][] = [];
    const wb: [string, number, number][] = [];
    const wc: [string, number, number][] = [];
    for (let i = 0; i < 3; i++) {
      wa.push([`a${i}`, i, i + 1]);
      wb.push([`b${i}`, 3 + i, 4 + i]);
      wc.push([`c${i}`, 6 + i, 7 + i]);
    }
    const base = [seg(0, 3, wa), seg(3, 6, wb), seg(6, 9, wc)];
    const countWords = (list: ReturnType<typeof moveBoundary>) =>
      list.reduce((n, s) => n + (s.words?.length ?? 0), 0);
    const allWords = (list: ReturnType<typeof moveBoundary>) =>
      list.flatMap((s) => s.words ?? []).map((w) => w.word).sort().join(",");

    // Drag 1: Grenze 0 um 1 Wort nach unten (b0 → A)
    const after1 = moveBoundary(base, 0, 1);
    expect(countWords(after1)).toBe(9);
    expect(allWords(after1)).toBe("a0,a1,a2,b0,b1,b2,c0,c1,c2");

    // Drag 2: Grenze 1 um 1 Wort nach unten (c0 → B) — auf after1
    const after2 = moveBoundary(after1, 1, 1);
    expect(countWords(after2)).toBe(9);
    expect(allWords(after2)).toBe("a0,a1,a2,b0,b1,b2,c0,c1,c2");
    // b0 liegt seit Drag 1 in A; Drag 2 schiebt c0 von C nach B
    expect(after2[0].text).toBe("a0 a1 a2 b0");
    expect(after2[1].text).toBe("b1 b2 c0");
    expect(after2[2].text).toBe("c1 c2");

    // Drag 3: Grenze 0 wieder zurück (b0 → B) — kumulativ auf after1-Basis
    const after3 = moveBoundary(after1, 0, -1);
    expect(countWords(after3)).toBe(9);
    expect(allWords(after3)).toBe("a0,a1,a2,b0,b1,b2,c0,c1,c2");
  });

  it("REPRO 2026-08-17: Grenze über die Kante hinaus und zurück — Clamp + Rückweg dupliziert nichts", () => {
    // User zieht weit über die verfügbare Wortzahl hinaus (Clamp), dann
    // zurück. moveBoundary clammt n auf Segment-Größe; der Rückweg muss von
    // der kumulativen Zahl aus konsistent bleiben (kein Duplikat durch
    // doppeltes Clampen).
    const base = twoSegs(); // 5+5 Wörter
    const countWords = (list: ReturnType<typeof moveBoundary>) =>
      list.reduce((n, s) => n + (s.words?.length ?? 0), 0);

    // delta 100 → clamp auf 4 (B behält 1 Wort)
    const over = moveBoundary(base, 0, 100);
    expect(countWords(over)).toBe(10);
    expect(over[0].text).toBe("a0 a1 a2 a3 a4 b0 b1 b2 b3");
    // zurück auf delta 2 (kumulativ, gleiche Basis)
    const back = moveBoundary(base, 0, 2);
    expect(countWords(back)).toBe(10);
    expect(back[0].text).toBe("a0 a1 a2 a3 a4 b0 b1");
    // und delta -100 → clamp -4 (A behält 1 Wort)
    const overNeg = moveBoundary(base, 0, -100);
    expect(countWords(overNeg)).toBe(10);
    expect(overNeg[0].text).toBe("a0");
  });

  it("REPRO 2026-08-17: moveBoundary auf RE-SEGMENTIERTER Liste (segMaxDuration gesetzt) — Invariante hält", () => {
    // UI-Pfad: segMaxDuration gesetzt → displaySegments = resegmentByDuration()
    // → Grenz-Drag arbeitet auf den Wort-Buckets. Wörter sind in Buckets
    // gruppiert, deren Grenzen NICHT mit den Original-Segmentgrenzen
    // zusammenfallen müssen; moveBoundary verschiebt Bucket-Wörter.
    const base = twoSegsWords(); // A(0-5) B(5-10), je 5 Wörter mit Lücken
    const reseg = resegmentByDuration(base, 2.5) as {
      start: number; end: number; text: string; words: { word: string; start: number; end: number }[];
    }[];
    const before = flattenWords(reseg as never);

    // Grenze 0 auf der resegmentierten Liste ziehen
    const moved = moveBoundary(reseg as never, 0, 1) as typeof reseg;
    expect(flattenWords(moved as never)).toEqual(before);

    // Grenze 1 ebenfalls
    const moved2 = moveBoundary(moved as never, 1, -1) as typeof reseg;
    expect(flattenWords(moved2 as never)).toEqual(before);
  });

  it("REPRO 2026-08-17: PUT-Roundtrip nach Drag — Server-Normalisierung erhält Wort-Zuordnung (keine Dopplungen)", () => {
    // UI-Ablauf: handleBoundaryDragEnd → replaceSegments(next) → Server
    // speichert json.loads(json.dumps(segs)) und liefert rec.segments zurück
    // → handleEdited setzt Cache → displaySegments = result.segments.
    // Der Roundtrip (JSON-Serialisierung wie segments.py) darf die
    // Wort-Zuordnung nicht verändern (Dopplung/Verlust).
    const base = twoSegsWords();
    const moved = moveBoundary(base, 0, 2) as never;
    const roundtrip = JSON.parse(JSON.stringify(moved)) as typeof base;
    expect(flattenWords(roundtrip)).toEqual(flattenWords(base));
    // Und: die Grenze ist nach dem Roundtrip noch da (nicht zurückgesprungen)
    expect(roundtrip[0].text).toBe("a0 a1 a2 a3 a4 b0 b1");
    expect(roundtrip[1].text).toBe("b2 b3 b4");
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

describe("splitSegmentAtRange (Edit: Markierung → eigenes Segment)", () => {
  // text = "a b c d e", Wörter lückenlos 1 s ab 0. Wort-Char-Ranges:
  // a[0,1) b[2,3) c[4,5) d[6,7) e[8,9)
  function fiveWords() {
    const words: [string, number, number][] = [
      ["a", 0.0, 1.0],
      ["b", 1.0, 2.0],
      ["c", 2.0, 3.0],
      ["d", 3.0, 4.0],
      ["e", 4.0, 5.0],
    ];
    return [seg(0, 5, words, "SPEAKER_00")];
  }

  it("teilt mitten: 3 Segmente, markierter Teil bekommt neuen Sprecher", () => {
    const input = fiveWords();
    const before = flattenWords(input);
    // Markiere "b c" (Zeichen 2..5)
    const out = splitSegmentAtRange(input, 0, 2, 5, "SPEAKER_07");
    expect(out.length).toBe(3);
    expect(out[0].text).toBe("a");
    expect(out[0].speaker).toBe("SPEAKER_00");
    expect(out[0].start).toBeCloseTo(0, 6);
    expect(out[0].end).toBeCloseTo(1, 6);
    expect(out[1].text).toBe("b c");
    expect(out[1].speaker).toBe("SPEAKER_07");
    expect(out[1].start).toBeCloseTo(1, 6);
    expect(out[1].end).toBeCloseTo(3, 6);
    expect(out[2].text).toBe("d e");
    expect(out[2].speaker).toBe("SPEAKER_00");
    expect(out[2].start).toBeCloseTo(3, 6);
    expect(out[2].end).toBeCloseTo(5, 6);
    // Invariante: alle Wörter + Timestamps exakt erhalten
    expect(flattenWords(out)).toEqual(before);
  });

  it("Selektion am Anfang → nur 2 Segmente (kein leeres Vorderteil)", () => {
    const input = fiveWords();
    const before = flattenWords(input);
    // Markiere nur "a" (Zeichen 0..1)
    const out = splitSegmentAtRange(input, 0, 0, 1, "SPEAKER_01");
    expect(out.length).toBe(2);
    expect(out[0].text).toBe("a");
    expect(out[0].speaker).toBe("SPEAKER_01");
    expect(out[1].text).toBe("b c d e");
    expect(out[1].speaker).toBe("SPEAKER_00");
    expect(flattenWords(out)).toEqual(before);
  });

  it("Selektion am Ende → nur 2 Segmente (kein leeres Hinterteil)", () => {
    const input = fiveWords();
    const before = flattenWords(input);
    // Markiere "e" (Zeichen 8..9 = Ende)
    const out = splitSegmentAtRange(input, 0, 8, 9, "SPEAKER_02");
    expect(out.length).toBe(2);
    expect(out[0].text).toBe("a b c d");
    expect(out[0].speaker).toBe("SPEAKER_00");
    expect(out[1].text).toBe("e");
    expect(out[1].speaker).toBe("SPEAKER_02");
    expect(flattenWords(out)).toEqual(before);
  });

  it("ohne Wort-Timestamps: Zeit proportional zur Zeichenposition", () => {
    const input = [{ start: 0, end: 4, text: "abcd", speaker: "SPEAKER_00" }];
    const out = splitSegmentAtRange(input, 0, 1, 3, "SPEAKER_09");
    expect(out.length).toBe(3);
    expect(out[0].text).toBe("a");
    expect(out[0].start).toBeCloseTo(0, 6);
    expect(out[0].end).toBeCloseTo(1, 6);
    expect(out[1].text).toBe("bc");
    expect(out[1].speaker).toBe("SPEAKER_09");
    expect(out[1].start).toBeCloseTo(1, 6);
    expect(out[1].end).toBeCloseTo(3, 6);
    expect(out[2].text).toBe("d");
    expect(out[2].start).toBeCloseTo(3, 6);
    expect(out[2].end).toBeCloseTo(4, 6);
  });

  it("ungültige Selektion / Index → unverändert", () => {
    const input = fiveWords();
    expect(splitSegmentAtRange(input, -1, 0, 3, "S")).toEqual(input);
    expect(splitSegmentAtRange(input, 5, 0, 3, "S")).toEqual(input);
    expect(splitSegmentAtRange(input, 0, 3, 3, "S")).toEqual(input);
    expect(splitSegmentAtRange(input, 0, 2, 2, "S")).toEqual(input);
    expect(splitSegmentAtRange(input, 0, 9, 10, "S")).toEqual(input); // leerer Text
  });

  it("mehrere Segmente: teilt nur das Ziel-Segment, Rest bleibt unangetastet", () => {
    const input = [seg(0, 5, [["a", 0, 1], ["b", 1, 2], ["c", 2, 3]], "SPEAKER_00"), seg(10, 12, [["x", 10, 11], ["y", 11, 12]], "SPEAKER_01")];
    const before = flattenWords(input);
    const out = splitSegmentAtRange(input, 1, 0, 2, "SPEAKER_05"); // nur "x"
    expect(out.length).toBe(3);
    expect(out[0].text).toBe("a b c");
    expect(out[1].text).toBe("x");
    expect(out[2].text).toBe("y");
    expect(flattenWords(out)).toEqual(before);
  });
});

/* ============================================================
   wordRangeToCharRange (Change 013: Split-Anker/Touch-Markierung)
   Übersetzt einen Wort-Index-Range in einen Zeichen-Range —
   EXAKT dieselbe Logik wie splitSegmentAtRange (Wort + Trenn-Space;
   der Space gehört keinem Wort-Span). text = "a b c d e" →
   a[0,1) b[2,3) c[4,5) d[6,7) e[8,9). (2026-08-17)
   ============================================================ */
describe("wordRangeToCharRange (Change 013: Wort-Range → Char-Range)", () => {
  function fiveWords() {
    return [
      { word: "a", start: 0, end: 1 },
      { word: "b", start: 1, end: 2 },
      { word: "c", start: 2, end: 3 },
      { word: "d", start: 3, end: 4 },
      { word: "e", start: 4, end: 5 },
    ];
  }

  it("einzelnes Wort → dessen Char-Range (ohne Trenn-Space)", () => {
    expect(wordRangeToCharRange(fiveWords(), 0, 0)).toEqual({ start: 0, end: 1 });
    expect(wordRangeToCharRange(fiveWords(), 2, 2)).toEqual({ start: 4, end: 5 });
    expect(wordRangeToCharRange(fiveWords(), 4, 4)).toEqual({ start: 8, end: 9 });
  });

  it("Wort-Range → Char-Range inkl. Trenn-Spaces dazwischen", () => {
    // "b c" = Zeichen 2..5
    expect(wordRangeToCharRange(fiveWords(), 1, 2)).toEqual({ start: 2, end: 5 });
    // "a b c" = Zeichen 0..5
    expect(wordRangeToCharRange(fiveWords(), 0, 2)).toEqual({ start: 0, end: 5 });
    // "d e" = Zeichen 6..9
    expect(wordRangeToCharRange(fiveWords(), 3, 4)).toEqual({ start: 6, end: 9 });
  });

  it("Reihenfolge egal (Touch-Drag rückwärts): hi/lo werden normalisiert", () => {
    expect(wordRangeToCharRange(fiveWords(), 2, 1)).toEqual({ start: 2, end: 5 });
    expect(wordRangeToCharRange(fiveWords(), 4, 0)).toEqual({ start: 0, end: 9 });
  });

  it("Konsistenz mit splitSegmentAtRange: Char-Range ergibt exakt denselben Split", () => {
    const input = [seg(0, 5, [["a", 0, 1], ["b", 1, 2], ["c", 2, 3], ["d", 3, 4], ["e", 4, 5]], "SPEAKER_00")];
    const before = flattenWords(input);
    // Touch markiert Wörter 1..2 ("b c") → Char-Range 2..5 → Split wie Desktop
    const r = wordRangeToCharRange(input[0].words as { word: string; start: number; end: number }[], 1, 2)!;
    const out = splitSegmentAtRange(input, 0, r.start, r.end, "SPEAKER_07");
    expect(out.length).toBe(3);
    expect(out[1].text).toBe("b c");
    expect(out[1].speaker).toBe("SPEAKER_07");
    expect(flattenWords(out)).toEqual(before);
  });

  it("ungültige Eingaben → null", () => {
    expect(wordRangeToCharRange([], 0, 0)).toBeNull();
    expect(wordRangeToCharRange(fiveWords(), -1, 0)).toBeNull();
    expect(wordRangeToCharRange(fiveWords(), 0, 5)).toBeNull();
    expect(wordRangeToCharRange(fiveWords(), 5, 5)).toBeNull();
    expect(wordRangeToCharRange(null as unknown as { word: string }[], 0, 0)).toBeNull();
  });
});
