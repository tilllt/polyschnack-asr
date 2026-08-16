/* ============================================================
   RESEGMENT — Segmentlänge in der Transkriptionsansicht wählen
   ============================================================
   Feature 2026-08-15 (User): ASR-Segmente sind chunk-bedingt oft ~105 s
   lang — für Untertitel unbrauchbar. In der Ansicht wählbar: die Wörter
   werden in Blöcke ≤ max_duration_s aufgeteilt; der Export (SRT/VTT)
   nutzt dieselbe Aufteilung (Backend: resegment_by_duration in
   service.py — identische Bucket-Logik, gleiche Ausgabe).

   Regeln (1:1 zum Backend):
   - Nur Wörter mit Timestamps werden aufgeteilt; fehlen sie, bleibt das
     Original-Segment unverändert.
   - Bucket endet, sobald (a) Ziel-Dauer überschritten würde ODER
     (b) Sprecher wechselt.
   - Mindestens 1 Wort pro Bucket.
   - Text = Wörter verbunden; start/end aus erstem/letztem Wort.
   ============================================================ */

export interface ResegWord {
  word: string;
  start?: number;
  end?: number;
  confidence?: number;
  [k: string]: unknown;
}

export interface ResegSegment {
  start?: number;
  end?: number;
  text?: string;
  speaker?: string;
  words?: ResegWord[];
  [k: string]: unknown;
}

// Pragmatischer Input-Typ: resegmentByDuration akzeptiert Segment[] UND
// die generischen Resegment-Strukturen — die Felder werden intern gelesen
// (readonly, optional). Kein API-Vertrag, nur ein UI-Helper.
export type ResegmentInput = readonly unknown[];

interface _W {
  word?: unknown;
  start?: unknown;
  end?: unknown;
  _speaker?: string;
}

export function resegmentByDuration(
  segments: ResegmentInput,
  maxDurationS: number,
): ResegSegment[] {
  if (!segments || segments.length === 0 || !(maxDurationS > 0)) {
    return segments ? ([...segments] as ResegSegment[]) : [];
  }

  const words: _W[] = [];
  for (const seg of segments) {
    const s = seg as { speaker?: unknown; words?: unknown };
    const speaker = typeof s.speaker === "string" ? s.speaker : "";
    const segWords = Array.isArray(s.words) ? (s.words as _W[]) : [];
    for (const w of segWords) {
      words.push({ ...w, _speaker: speaker });
    }
  }
  if (words.length === 0) return [...segments] as ResegSegment[];

  const buckets: _W[][] = [];
  let cur: _W[] = [];
  for (const w of words) {
    const ws = typeof w.start === "number" ? w.start : 0;
    const we = typeof w.end === "number" ? w.end : ws;
    if (cur.length > 0) {
      const firstS = typeof cur[0].start === "number" ? cur[0].start : 0;
      const curSpeaker = cur[0]._speaker ?? "";
      const overflow = we - firstS > maxDurationS;
      const speakerChange = (w._speaker ?? "") !== curSpeaker;
      if (overflow || speakerChange) {
        buckets.push(cur);
        cur = [];
      }
    }
    cur.push(w);
  }
  if (cur.length > 0) buckets.push(cur);

  return buckets.map((b) => {
    const start = typeof b[0].start === "number" ? b[0].start : 0;
    const last = b[b.length - 1];
    const end = typeof last.end === "number" ? last.end : start;
    const speaker = b[0]._speaker ?? "";
    const text = b
      .map((x) => (typeof x.word === "string" ? x.word : String(x.word ?? "")))
      .join(" ")
      .trim();
    const seg: ResegSegment = {
      start,
      end,
      text,
      words: b.map(({ _speaker: _sp, ...rest }) => rest as ResegWord),
    };
    if (speaker) seg.speaker = speaker;
    return seg;
  });
}

/** Ein Segment aus einer Wort-Liste bauen (start/end/text/words). */
function buildSeg(words: _W[]): ResegSegment {
  const start = typeof words[0].start === "number" ? words[0].start : 0;
  const last = words[words.length - 1];
  const end = typeof last.end === "number" ? last.end : start;
  const speaker = words[0]._speaker ?? "";
  const text = words
    .map((x) => (typeof x.word === "string" ? x.word : String(x.word ?? "")))
    .join(" ")
    .trim();
  const seg: ResegSegment = {
    start,
    end,
    text,
    words: words.map(({ _speaker: _sp, ...rest }) => rest as ResegWord),
  };
  if (speaker) seg.speaker = speaker;
  return seg;
}

/**
 * Verschiebt die Grenze zwischen Segment `boundaryIdx` und `boundaryIdx+1`
 * WORT FÜR WORT (Feature 2026-08-15, draggable Timecode-Marker).
 *
 * Semantik (Konsument = Drag-UI):
 * - `delta < 0` (Marker nach OBEN ziehen = Grenze in der Zeit zurück):
 *   die letzten `-delta` Wörter von Segment `boundaryIdx` wandern zum
 *   Anfang von Segment `boundaryIdx+1` → Segment N verkleinert sich am
 *   Ende, Segment N+1 verlängert sich am Anfang.
 * - `delta > 0` (nach unten): die ersten `delta` Wörter von Segment
 *   N+1 wandern an das Ende von Segment N.
 * - Jeder Schritt = eine Wortgrenze. Einzelne Wörter werden nie geteilt.
 * - Ist die Grenze an der äußersten Kante (Segment hätte 0 Wörter),
 *   wird nichts weiter verschoben (stoppt am ersten/letzten Wort).
 * - Fehlen Wort-Timestamps (kein Karaoke), passiert nichts.
 *
 * Returns: neue Segmentliste (die betroffenen zwei Segmente neu gebaut,
 * alle anderen unverändert referenziert).
 */
export function moveBoundary(
  segments: ResegmentInput,
  boundaryIdx: number,
  delta: number,
): ResegSegment[] {
  if (!segments || segments.length < 2) {
    return segments ? ([...segments] as ResegSegment[]) : [];
  }
  if (!Number.isFinite(delta) || delta === 0) return [...segments] as ResegSegment[];
  if (boundaryIdx < 0 || boundaryIdx >= segments.length - 1) {
    return [...segments] as ResegSegment[];
  }

  const segs = segments as ResegSegment[];
  const a = segs[boundaryIdx];
  const b = segs[boundaryIdx + 1];
  const aWords = (a.words ?? []) as _W[];
  const bWords = (b.words ?? []) as _W[];
  if (aWords.length === 0 || bWords.length === 0) {
    return [...segments] as ResegSegment[];
  }

  let n: number;
  if (delta < 0) {
    n = Math.max(-aWords.length + 1, delta); // Segment A darf nicht leer werden
  } else {
    n = Math.min(bWords.length - 1, delta); // Segment B darf nicht leer werden
  }
  if (n === 0) return [...segments] as ResegSegment[];

  const out = [...segs];
  if (n < 0) {
    // Letzte |n| Wörter von A → Anfang von B
    const split = aWords.length + n;
    const aNew = aWords.slice(0, split);
    const bNew = [...aWords.slice(split), ...bWords];
    out[boundaryIdx] = { ...a, ...buildSeg(aNew) };
    out[boundaryIdx + 1] = { ...b, ...buildSeg(bNew) };
  } else {
    // Erste n Wörter von B → Ende von A
    const split = n;
    const aNew = [...aWords, ...bWords.slice(0, split)];
    const bNew = bWords.slice(split);
    out[boundaryIdx] = { ...a, ...buildSeg(aNew) };
    out[boundaryIdx + 1] = { ...b, ...buildSeg(bNew) };
  }
  return out;
}

/**
 * Fügt an der Grenze nach Segment `afterIdx` ein NEUES Segment ein
 * (Feature 2026-08-16, Mockup: "+" im Kreis zwischen den Segmenten).
 *
 * Regeln (User):
 * - Das neue Segment übernimmt den Sprecher des VORIGEN Segments.
 * - Das LETZTE WORT des vorigen Segments wandert in das neue Segment
 *   (start/end des neuen Segments = Wort-Timestamps).
 * - Der Gesamttext ändert sich NICHT — nur die Segment-Aufteilung.
 * - Ohne Wort-Timestamps (kein Karaoke) kann nicht eingefügt werden →
 *   Liste unverändert (Button wird in der UI dann deaktiviert).
 */
export function insertSegment(
  segments: ResegmentInput,
  afterIdx: number,
): ResegSegment[] {
  if (!segments || segments.length === 0) return segments ? ([...segments] as ResegSegment[]) : [];
  if (afterIdx < 0 || afterIdx >= segments.length) return [...segments] as ResegSegment[];
  const segs = [...segments] as ResegSegment[];
  const a = segs[afterIdx];
  const aWords = (a.words ?? []) as _W[];
  if (aWords.length === 0) return segs; // ohne Wörter nichts zu verschieben

  const last = aWords[aWords.length - 1];
  const aNew = aWords.slice(0, -1);
  const next = buildSeg([last]);
  if (a.speaker) next.speaker = a.speaker; // gleicher Sprecher wie voriges Segment
  segs[afterIdx] = { ...a, ...buildSeg(aNew) };
  segs.splice(afterIdx + 1, 0, next);
  return segs;
}

/**
 * Löscht Segment `idx` (Feature 2026-08-16, Mockup: "−" im Kreis vor dem
 * Timecode). Der Text (die Wörter) bleibt erhalten und wird dem VORIGEN
 * Segment zugeordnet; beim ersten Segment dem NACHFOLGENDEN. Mindestens
 * ein Segment bleibt immer übrig. Ohne Wörter wird der Text-String einfach
 * angehängt (start/end des Nachbarsegments bleiben).
 */
export function deleteSegment(
  segments: ResegmentInput,
  idx: number,
): ResegSegment[] {
  if (!segments || segments.length <= 1) return segments ? ([...segments] as ResegSegment[]) : [];
  if (idx < 0 || idx >= segments.length) return [...segments] as ResegSegment[];
  const segs = [...segments] as ResegSegment[];
  const removed = segs.splice(idx, 1)[0];
  const removedWords = ((removed.words ?? []) as _W[]).slice();

  if (removedWords.length === 0) {
    // Nur Text übertragen (keine Wort-Timestamps verfügbar)
    const t = String(removed.text ?? "").trim();
    if (!t) return segs;
    if (idx === 0) {
      const b = segs[0];
      segs[0] = { ...b, text: `${t} ${String(b.text ?? "")}`.trim() };
    } else {
      const a = segs[idx - 1];
      segs[idx - 1] = { ...a, text: `${String(a.text ?? "")} ${t}`.trim() };
    }
    return segs;
  }

  if (idx === 0) {
    // Erstes Segment: Wörter an den Anfang des neuen ersten Segments
    const b = segs[0];
    const bWords = (b.words ?? []) as _W[];
    segs[0] = { ...b, ...buildSeg([...removedWords, ...bWords]) };
  } else {
    const a = segs[idx - 1];
    const aWords = (a.words ?? []) as _W[];
    segs[idx - 1] = { ...a, ...buildSeg([...aWords, ...removedWords]) };
  }
  return segs;
}
