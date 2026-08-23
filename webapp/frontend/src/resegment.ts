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

/**
 * Change 009 (Single Source of Truth): Anzeige-Segmente als reine Funktion
 * des Recording-Modells. Es gibt genau EINE Segment-Wahrheit (der
 * Server/Cache); die Anzeige kann nicht mehr davon abweichen.
 *
 * - segMaxDuration gesetzt → resegmentByDuration (Auto-Vorschau): zerlegt
 *   NUR Segmente ohne _manual-Flag; manuell angefasste (Grenz-Drag, +/−,
 *   Split — markieren ihre betroffenen Segmente) bleiben exakt erhalten.
 * - ohne Länge → segments direkt.
 */
export function deriveSegments(
  segments: readonly unknown[] | null | undefined,
  segMaxDuration: number | null,
): readonly unknown[] {
  if (!segments || segments.length === 0) return [];
  // Change 088-Hybrid: resegmentByDuration zerlegt NUR Segmente OHNE
  // _manual-Flag — manuell angefasste Grenzen (moveBoundary/insert/
  // delete/split setzen das Flag) bleiben exakt erhalten, unangefasste
  // Original-Chunks teilen sich nach der gewählten Länge. segments_manual
  // (Recording-Flag) ist dafür nicht mehr der Anzeige-Schalter: es zeigt
  // nur an, dass es manuelle OPs gibt — die Flags steuern die Aufteilung.
  if (segMaxDuration != null && segMaxDuration > 0) {
    return resegmentByDuration(segments, segMaxDuration);
  }
  return segments;
}

export function resegmentByDuration(
  segments: ResegmentInput,
  maxDurationS: number,
): ResegSegment[] {
  if (!segments || segments.length === 0 || !(maxDurationS > 0)) {
    return segments ? ([...segments] as ResegSegment[]) : [];
  }

  // Change 088: manuell angefasste Segmente (_manual: true) werden NICHT
  // aufgeteilt — sie wandern unverändert (Original-Referenz) in die
  // Ausgabe. Kurze unmarkierte Segmente bleiben als 1 Bucket mit
  // identischem Text erhalten; nur Riesen-Chunks (> Ziel) werden geteilt.
  const out: ResegSegment[] = [];
  let cur: _W[] = [];
  const flush = () => {
    if (cur.length === 0) return;
    const start = typeof cur[0].start === "number" ? cur[0].start : 0;
    const last = cur[cur.length - 1];
    const end = typeof last.end === "number" ? last.end : start;
    const speaker = cur[0]._speaker ?? "";
    const text = cur
      .map((x) => (typeof x.word === "string" ? x.word : String(x.word ?? "")))
      .join(" ")
      .trim();
    const seg: ResegSegment = {
      start,
      end,
      text,
      words: cur.map(({ _speaker: _sp, ...rest }) => rest as ResegWord),
    };
    if (speaker) seg.speaker = speaker;
    out.push(seg);
    cur = [];
  };

  for (const seg of segments) {
    const s = seg as { speaker?: unknown; words?: unknown; _manual?: unknown };
    if (s._manual === true) {
      flush(); // offenen Bucket vor dem manuellen Segment schließen
      out.push(seg as ResegSegment); // Original-Objekt, exakt erhalten
      continue;
    }
    const speaker = typeof s.speaker === "string" ? s.speaker : "";
    const segWords = Array.isArray(s.words) ? (s.words as _W[]) : [];
    if (segWords.length === 0) {
      // Keine Wort-Timestamps (kein Karaoke): Segment kann nicht geteilt
      // werden → Original unverändert übernehmen.
      flush();
      out.push(seg as ResegSegment);
      continue;
    }
    // Change 102: Bucket vor jedem neuen Segment schließen — die Bucket-
    // Logik darf NIE über Segmentgrenzen hinweg sammeln. Vorher wurden
    // kurze benachbarte unmarkierte Segmente zu EINEM verschmolzen
    // (14 Wörter/1 Segment statt 2), wodurch Anzeige ≠ DB-Zustand war und
    // Struktur-Ops (Split/Delete) + der Yjs-Autosave die Verschmelzung
    // zurückspeicherten (PUT mit leerem text → 400, Datenverlust-Risiko).
    flush();
    for (const w of segWords) {
      const item: _W = { ...w, _speaker: speaker };
      const ws = typeof w.start === "number" ? w.start : 0;
      const we = typeof w.end === "number" ? w.end : ws;
      if (cur.length > 0) {
        const firstS = typeof cur[0].start === "number" ? cur[0].start : 0;
        const curSpeaker = cur[0]._speaker ?? "";
        const overflow = we - firstS > maxDurationS;
        const speakerChange = (item._speaker ?? "") !== curSpeaker;
        if (overflow || speakerChange) {
          flush();
        }
      }
      cur.push(item);
    }
  }
  flush();
  return out;
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
    out[boundaryIdx] = { ...a, ...buildSeg(aNew), _manual: true };
    out[boundaryIdx + 1] = { ...b, ...buildSeg(bNew), _manual: true };
  } else {
    // Erste n Wörter von B → Ende von A
    const split = n;
    const aNew = [...aWords, ...bWords.slice(0, split)];
    const bNew = bWords.slice(split);
    out[boundaryIdx] = { ...a, ...buildSeg(aNew), _manual: true };
    out[boundaryIdx + 1] = { ...b, ...buildSeg(bNew), _manual: true };
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
  const next = { ...buildSeg([last]), _manual: true };
  if (a.speaker) next.speaker = a.speaker; // gleicher Sprecher wie voriges Segment
  segs[afterIdx] = { ...a, ...buildSeg(aNew), _manual: true };
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
    segs[0] = { ...b, ...buildSeg([...removedWords, ...bWords]), _manual: true };
  } else {
    const a = segs[idx - 1];
    const aWords = (a.words ?? []) as _W[];
    segs[idx - 1] = { ...a, ...buildSeg([...aWords, ...removedWords]), _manual: true };
  }
  return segs;
}

/* ============================================================
   SPLIT SEGMENT AT RANGE — Text-Markierung → eigenes Segment
   ============================================================
   Feature 2026-08-16 (Edit): Der User markiert einen Textbereich
   innerhalb EINES Segments → der markierte Teil wird ein eigenes
   Segment (mit neuem `speaker`), die Teile davor/danach behalten den
   ORIGINAL-Sprecher. Segment wird an der Stelle getrennt.

   Invariante (wie insertSegment/deleteSegment): Wort-Reihenfolge und
   Wort-Timestamps bleiben exakt erhalten — nur die Segment-Zuordnung
   ändert sich. Ohne Wort-Timestamps wird die Zeit proportional zur
   Zeichenposition interpoliert. Leere Teile (Selektion am Rand)
   entfallen. ============================================================ */

export function splitSegmentAtRange(
  segments: ResegmentInput,
  idx: number,
  charStart: number,
  charEnd: number,
  speaker: string,
): ResegSegment[] {
  const segs = [...(segments as ResegSegment[])];
  if (!segs.length || idx < 0 || idx >= segs.length) return segs;

  const seg = segs[idx];
  const text = typeof seg.text === "string" ? seg.text : "";
  if (!text) return segs;

  const cs = Math.max(0, Math.min(charStart, text.length));
  const ce = Math.max(0, Math.min(charEnd, text.length));
  if (cs >= ce) return segs; // kollabierte/leere Selektion

  const words = Array.isArray(seg.words) ? (seg.words as ResegWord[]) : [];
  const hasWords = words.length > 0;

  let part1: ResegWord[] = [];
  let part2: ResegWord[] = [];
  let part3: ResegWord[] = [];
  let midText: string;
  let midStart: number;
  let midEnd: number;

  if (hasWords) {
    // Wort-Char-Ranges rekonstruieren (Wort + Trenn-Space, wie im DOM
    // gerendert — der Space gehört KEINEM Wort-Span).
    let pos = 0;
    const ranges: Array<[number, number]> = words.map((w) => {
      const s = pos;
      pos += typeof w.word === "string" ? w.word.length : 0;
      const e = pos;
      pos += 1; // Trenn-Space
      return [s, e];
    });
    let w0 = -1;
    let w1 = -1;
    ranges.forEach(([s, e], wi) => {
      if (e > cs && s < ce) {
        if (w0 < 0) w0 = wi;
        w1 = wi;
      }
    });
    if (w0 < 0) return segs; // Selektion trifft kein Wort
    part1 = words.slice(0, w0);
    part2 = words.slice(w0, w1 + 1);
    part3 = words.slice(w1 + 1);
    midText = joinWords(part2);
    const first = part2[0];
    const last = part2[part2.length - 1];
    midStart = typeof first.start === "number" ? first.start : seg.start ?? 0;
    midEnd = typeof last.end === "number" ? last.end : seg.end ?? midStart;
  } else {
    // Keine Wort-Timestamps: proportional interpolieren.
    const st = typeof seg.start === "number" ? seg.start : 0;
    const en = typeof seg.end === "number" ? seg.end : st;
    const f0 = cs / text.length;
    const f1 = ce / text.length;
    midText = text.slice(cs, ce);
    midStart = st + (en - st) * f0;
    midEnd = st + (en - st) * f1;
  }

  const originalSpeaker = seg.speaker;
  const out: ResegSegment[] = [];

  if (hasWords ? part1.length > 0 : cs > 0) {
    const before: ResegSegment = { ...seg };
    if (part1.length > 0) {
      const first = part1[0];
      const last = part1[part1.length - 1];
      before.words = part1;
      before.text = joinWords(part1);
      before.start = typeof first.start === "number" ? first.start : seg.start;
      before.end = typeof last.end === "number" ? last.end : midStart;
    } else {
      before.words = undefined;
      before.text = text.slice(0, cs);
      before.end = midStart;
    }
    if (originalSpeaker !== undefined) before.speaker = originalSpeaker;
    before._manual = true;
    out.push(before);
  }

  const mid: ResegSegment = { ...seg };
  mid.words = part2.length > 0 ? part2 : undefined;
  mid.text = midText;
  mid.start = midStart;
  mid.end = midEnd;
  mid.speaker = speaker;
  mid._manual = true;
  out.push(mid);

  if (hasWords ? part3.length > 0 : ce < text.length) {
    const after: ResegSegment = { ...seg };
    if (part3.length > 0) {
      const first = part3[0];
      const last = part3[part3.length - 1];
      after.words = part3;
      after.text = joinWords(part3);
      after.start = typeof first.start === "number" ? first.start : midEnd;
      after.end = typeof last.end === "number" ? last.end : seg.end;
    } else {
      after.words = undefined;
      after.text = text.slice(ce);
      after.start = midEnd;
    }
    if (originalSpeaker !== undefined) after.speaker = originalSpeaker;
    after._manual = true;
    out.push(after);
  }

  segs.splice(idx, 1, ...out);
  return segs;
}

/** Wörter mit genau einem Space verbinden (wie der DOM-Render). */
function joinWords(words: ResegWord[]): string {
  return words
    .map((w) => (typeof w.word === "string" ? w.word : ""))
    .join(" ")
    .trim();
}

/* ============================================================
   Change 013: Wort-Range → Char-Range (Split-Anker)
   Gleiche Char-Range-Logik wie splitSegmentAtRange (Wort +
   Trenn-Space; der Space gehört KEINEM Wort-Span). Wird von der
   Touch-Markierung (SegmentList) verwendet, um aus einem
   Wort-Index-Range den Char-Range für den Split zu bauen.
   ============================================================ */
export function wordRangeToCharRange(
  words: readonly ResegWord[],
  lo: number,
  hi: number,
): { start: number; end: number } | null {
  if (!words || words.length === 0) return null;
  const lo2 = Math.min(lo, hi);
  const hi2 = Math.max(lo, hi);
  if (lo2 < 0 || hi2 >= words.length) return null;
  let pos = 0;
  const ranges: Array<[number, number]> = words.map((w) => {
    const s = pos;
    pos += typeof w.word === "string" ? w.word.length : 0;
    const e = pos;
    pos += 1; // Trenn-Space
    return [s, e];
  });
  return { start: ranges[lo2][0], end: ranges[hi2][1] };
}

/* ============================================================
   Wort-Invariante: flattenWords über alle Segmente
   ============================================================
   Req 10 (Spec transcription-view): jede GUI-Operation (Grenze ziehen,
   +/−, Split, Re-Segmentierung) muss die lückenlose Wortfolge
   (word|start|end) über alle Segmente erhalten — nur die Segment-
   Zuordnung ändert sich. flattenWords liefert die kanonische Folge,
   mit der Anzeige/Server-Zustand inhaltlich verglichen werden kann
   (statt Objekt-Referenzen). ====================================== */

export interface FlatWord {
  word?: string;
  start?: number;
  end?: number;
}

export function flattenWords(
  segments: readonly { words?: readonly FlatWord[] | undefined }[],
): FlatWord[] {
  return (segments ?? []).flatMap((s) => s.words ?? []);
}
