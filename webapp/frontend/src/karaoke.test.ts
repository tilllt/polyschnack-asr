/* ============================================================
   KARAOKE-Tests: Wort-Hervorhebung nach Diarization-Merge & Edit
   ============================================================ */
import { describe, it, expect } from "vitest";
import {
  isWordActive,
  activeWordIndex,
  activeSegmentIndex,
  isKaraokeReady,
  confidenceTier,
  confidenceClass,
  hasConfidence,
  nextWordTarget,
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
  // leadS: 0 = reine Glitch-Logik ohne Vorlauf (die alten Erwartungen);
  // der Vorlauf selbst wird separat getestet.

  it("wandert nahtlos durch aufeinanderfolgende Wörter (leadS=0)", () => {
    expect(activeWordIndex(words, 0.0, 0)).toBe(0);
    expect(activeWordIndex(words, 0.99, 0)).toBe(0);
    expect(activeWordIndex(words, 1.0, 0)).toBe(1); // exakte Grenze → nächstes
    expect(activeWordIndex(words, 2.0, 0)).toBe(2);
  });

  it("nach dem letzten Wort-Ende → -1 (kein Kleben, Fix 2026-08-18)", () => {
    // Vorher klebte das letzte Wort für alle t >= last.start — dadurch
    // markierten SEGMENTE VOR currentTime fälschlich ihr letztes Wort
    // (Doppel-Highlight; Autoscroll sprang zum ersten data-active-word,
    // d.h. nach oben). Nach dem Ende ist KEIN Wort mehr aktiv.
    expect(activeWordIndex(words, 3.0, 0)).toBe(-1);
    expect(activeWordIndex(words, 5.0, 0)).toBe(-1);
    expect(activeWordIndex(words, 2.99, 0)).toBe(2); // letztes Wort läuft noch
  });

  it("KEIN Glitch bei Timestamp-Lücken (kein Wort-Ausfall, leadS=0)", () => {
    // w[0].end=1.0, w[1].start=1.2 → Lücke 1.0–1.2
    const gappy = [
      { word: "a", start: 0.0, end: 1.0 },
      { word: "b", start: 1.2, end: 2.0 },
    ];
    // Alte isWordActive-Logik: bei t=1.1 wäre KEIN Wort aktiv (Glitch)
    expect(isWordActive(gappy[0], 1.1)).toBe(false);
    expect(isWordActive(gappy[1], 1.1)).toBe(false);
    // Neue Logik: das letzte gestartete Wort bleibt aktiv → kein Sprung
    expect(activeWordIndex(gappy, 1.1, 0)).toBe(0);
    expect(activeWordIndex(gappy, 1.2, 0)).toBe(1);
  });

  it("KEIN Doppel-Highlight bei Überlappungen (neueres Wort gewinnt, leadS=0)", () => {
    // w[0].end=1.5, w[1].start=1.2 → Überlappung 1.2–1.5
    const overlap = [
      { word: "a", start: 0.0, end: 1.5 },
      { word: "b", start: 1.2, end: 2.0 },
    ];
    expect(isWordActive(overlap[0], 1.3)).toBe(true);
    expect(isWordActive(overlap[1], 1.3)).toBe(true);
    // Neue Logik: genau EIN aktives Wort
    expect(activeWordIndex(overlap, 1.3, 0)).toBe(1);
  });

  it("vor dem ersten Wort → -1 (nichts aktiv, leadS=0)", () => {
    expect(activeWordIndex(words, -0.5, 0)).toBe(-1);
  });

  it("leere/fehlende Wortliste → -1", () => {
    expect(activeWordIndex([], 1.0, 0)).toBe(-1);
    expect(activeWordIndex(undefined, 1.0, 0)).toBe(-1);
  });

  it("Vorlauf (Default KARAOKE_LEAD_S=0.15): Highlight am ANFANG des Wortes", () => {
    // Aligner-Timestamps liegen ~0.1–0.2 s nach dem akustischen Start —
    // ohne Vorlauf sprang das Highlight erst, wenn das Wort fast vorbei war.
    // t=0.85 → +0.15 = 1.0 → Wort 1 (start 1.0) wird schon VOR dem
    // hörbaren Beginn markiert; t=1.0 → Wort 1 (nicht mehr Wort 0).
    expect(activeWordIndex(words, 0.84)).toBe(0);
    expect(activeWordIndex(words, 0.85)).toBe(1);
    expect(activeWordIndex(words, 1.0)).toBe(1);
    // Ein frei wählbarer, größerer Vorlauf (z.B. 0.3) verschiebt weiter.
    expect(activeWordIndex(words, 1.7, 0.3)).toBe(2);
    // Sehr früh (noch nicht mal der Vorlauf erreicht Wort 0) → -1.
    expect(activeWordIndex(words, -0.16)).toBe(-1);
    expect(activeWordIndex(words, -0.14)).toBe(0);
  });

  it("REPRO 2026-08-17: Stop nahe Wortgrenze springt auf das NÄCHSTE Wort (Lead im Pausenzustand)", () => {
    // User-Befund: „Karaoke-Hervorhebung springt auf ein Wort weiter vorne
    // im Text wenn man stopp drückst“. activeWordIndex addiert den Vorlauf
    // IMMER (auch pausiert) — `leadS` ist ein Parameter des Aufrufers, aber
    // SegmentList übergibt ihn nicht und RecordingCard verdrahtet
    // onPlayStateChange nicht → die Anzeige rechnet mit 0.15 auch im Stop.
    // words: hallo[0,1) hier[1,2) spricht[2,3)
    // Gestoppt bei t=1.0 (Wort „hier“ beginnt EXAKT) → +0.15 → t=1.15 →
    // letztes Wort mit start <= 1.15 ist „hier“ (1.0) — OK.
    // Gestoppt bei t=1.1 (mitten in „hier“) → +0.15 → 1.25 → immer „hier“.
    // ABER gestoppt bei t=1.85 (fast am Ende von „hier“) → +0.15 → 2.0 →
    // „spricht“ (start 2.0) wird markiert, obwohl die Wiedergabe bei 1.85
    // steht — der sichtbare Sprung.
    expect(activeWordIndex(words, 1.85)).toBe(2); // mit Default-Lead 0.15
    expect(activeWordIndex(words, 1.85, 0)).toBe(1); // pausiert exakt
    // Und der umgekehrte Fall: gestoppt bei 0.9 (fast am Ende von „hallo“)
    // → +0.15 = 1.05 → „hier“, obwohl man „hallo“ zuletzt gehört hat.
    expect(activeWordIndex(words, 0.9)).toBe(1); // mit Lead
    expect(activeWordIndex(words, 0.9, 0)).toBe(0); // exakt
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

  it("Lücke vor dem ersten Segment → erstes Segment (Change 104)", () => {
    // Klick in der Waveform auf eine Stelle ohne Dialog VOR dem ersten
    // Segment (z. B. t=0.5 bei Start=1.0) → das nächste Segment wird aktiv.
    expect(activeSegmentIndex(segments, -1)).toBe(0);
  });

  it("Lücke zwischen Segmenten → nächstes Segment (Change 104)", () => {
    // 2 Segmente mit Dialog-Lücke dazwischen (kein nahtloser Anschluss).
    const gap: KaraokeSegment[] = [
      { start: 1.0, end: 5.0, text: "A" },
      { start: 6.0, end: 9.0, text: "B" },
    ];
    expect(activeSegmentIndex(gap, 5.5)).toBe(1); // Lücke → nächstes
    expect(activeSegmentIndex(gap, 0.2)).toBe(0); // vor Segment 1 → Segment 1
    expect(activeSegmentIndex(gap, 7.0)).toBe(1); // innerhalb Segment 2
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

describe("confidenceTier (Ampel pro Wort)", () => {
  it("high ab 0.90", () => {
    expect(confidenceTier(0.9)).toBe("high");
    expect(confidenceTier(0.95)).toBe("high");
    expect(confidenceTier(1.0)).toBe("high");
  });
  it("medium ab 0.70", () => {
    expect(confidenceTier(0.7)).toBe("medium");
    expect(confidenceTier(0.89)).toBe("medium");
  });
  it("low unter 0.70", () => {
    expect(confidenceTier(0.69)).toBe("low");
    expect(confidenceTier(0.0)).toBe("low");
    expect(confidenceTier(0.42)).toBe("low");
  });
  it("null bei undefined/NaN (kein Fake-Wert)", () => {
    expect(confidenceTier(undefined)).toBeNull();
    expect(confidenceTier(NaN)).toBeNull();
  });
});

describe("confidenceClass (CSS-Klassen)", () => {
  it("mappt Tier auf conf-*-Klasse", () => {
    expect(confidenceClass(0.95)).toBe("conf-high");
    expect(confidenceClass(0.8)).toBe("conf-medium");
    expect(confidenceClass(0.3)).toBe("conf-low");
  });
  it("leer ohne Confidence", () => {
    expect(confidenceClass(undefined)).toBe("");
  });
});

describe("hasConfidence (Färbung nur bei echten Daten)", () => {
  it("true wenn mindestens ein Wort Confidence hat", () => {
    expect(hasConfidence([{ word: "a", start: 0, end: 1, confidence: 0.9 }])).toBe(true);
    expect(hasConfidence([
      { word: "a", start: 0, end: 1 },
      { word: "b", start: 1, end: 2, confidence: 0.5 },
    ])).toBe(true);
  });
  it("false ohne Confidence-Daten", () => {
    expect(hasConfidence(undefined)).toBe(false);
    expect(hasConfidence([])).toBe(false);
    expect(hasConfidence([{ word: "a", start: 0, end: 1 }])).toBe(false);
    expect(hasConfidence([{ word: "a", start: 0, end: 1, confidence: NaN }])).toBe(false);
  });
});

describe("nextWordTarget (Cursor ←/→ Wort-Navigation)", () => {
  const segs: KaraokeSegment[] = [
    { start: 0, end: 5, text: "a b c", words: [
      { word: "a", start: 0, end: 1 }, { word: "b", start: 1, end: 2 }, { word: "c", start: 2, end: 5 } ] },
    { start: 5, end: 9, text: "d e", words: [
      { word: "d", start: 5, end: 7 }, { word: "e", start: 7, end: 9 } ] },
    { start: 9, end: 12, text: "f", words: [{ word: "f", start: 9, end: 12 }] },
  ];
  const empty: KaraokeSegment[] = [{ start: 0, end: 9, text: "leer" }]; // keine Wörter

  it("ArrowRight: nächstes Wort im Segment", () => {
    // t=1.2 → aktives Wort b (wIdx 1) → Ziel c (wIdx 2)
    expect(nextWordTarget(segs, 0, 1.2, 1)).toEqual({ segIdx: 0, wIdx: 2 });
  });
  it("ArrowRight am Segmentende: erstes Wort des nächsten Segments", () => {
    expect(nextWordTarget(segs, 0, 2.5, 1)).toEqual({ segIdx: 1, wIdx: 0 });
  });
  it("ArrowRight am Ende der Transkription: null", () => {
    expect(nextWordTarget(segs, 2, 9.5, 1)).toBeNull();
  });
  it("ArrowRight nach dem Segment-Ende: nächstes Segment (Fix 2026-08-18)", () => {
    // t=6.0 liegt hinter Segment 0 (Ende 5.0) — activeWordIndex liefert
    // dort -1; die Navigation muss trotzdem zum nächsten Segment springen.
    expect(nextWordTarget(segs, 0, 6.0, 1)).toEqual({ segIdx: 1, wIdx: 0 });
  });
  it("ArrowLeft: vorheriges Wort im Segment", () => {
    expect(nextWordTarget(segs, 0, 1.2, -1)).toEqual({ segIdx: 0, wIdx: 0 });
  });
  it("ArrowLeft am Segmentanfang: letztes Wort des vorherigen Segments", () => {
    expect(nextWordTarget(segs, 1, 5.2, -1)).toEqual({ segIdx: 0, wIdx: 2 });
  });
  it("ArrowLeft am Anfang der Transkription: null", () => {
    expect(nextWordTarget(segs, 0, 0.2, -1)).toBeNull();
  });
  it("vor dem ersten Wort (aw=-1): Right → erstes Wort, Left → voriges Segment", () => {
    expect(nextWordTarget(segs, 0, -0.5, 1)).toEqual({ segIdx: 0, wIdx: 0 });
    expect(nextWordTarget(segs, 1, -1, -1)).toEqual({ segIdx: 0, wIdx: 2 });
  });
  it("überspringt Segmente ohne Wörter", () => {
    const mixed: KaraokeSegment[] = [segs[0], empty[0], segs[1]];
    expect(nextWordTarget(mixed, 0, 2.5, 1)).toEqual({ segIdx: 2, wIdx: 0 });
    expect(nextWordTarget(mixed, 2, 5.2, -1)).toEqual({ segIdx: 0, wIdx: 2 });
  });
  it("ungültige Eingaben → null", () => {
    expect(nextWordTarget([], 0, 0, 1)).toBeNull();
    expect(nextWordTarget(segs, -1, 0, 1)).toBeNull();
    expect(nextWordTarget(segs, 99, 0, 1)).toBeNull();
    expect(nextWordTarget(empty, 0, 0, 1)).toBeNull();
  });
});
