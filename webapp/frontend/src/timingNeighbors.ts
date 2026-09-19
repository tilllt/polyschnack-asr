/**
 * Change 209 (User-Vorgabe 19.09.2026): Nachbar-Marker im Timing-Modus.
 *
 * Neben dem aktiven Wort (n) zeigen wir die Range-Marker von n-1 und n+1.
 * Zieht man eine Kante des aktiven Wortes über einen Nachbarn hinaus, wird
 * dessen berührte Kante mitgeschoben (schrumpfen) — die Reihenfolge im
 * Wort-Flow bleibt erhalten, es entsteht keine Überlappung. Jeder Nachbar
 * behält dabei die Mindestdauer (MIN_WORD_DURATION_S).
 *
 * Der Server macht dasselbe autoritativ (`shrink_neighbors=true` im PATCH);
 * hier steht die identische Rechnung für die LIVE-Anzeige während des Ziehens
 * und für die Anzeige direkt nach dem Speichern.
 */
import type { Segment } from "./api";
import { MIN_WORD_DURATION_S } from "./waveformTime";

export interface TimingNeighbor {
  segIdx: number;
  wordIdx: number;
  /** Worttext (Anzeige/Tooltip). */
  text: string;
  start: number;
  end: number;
}

/** Wort an einer Position — oder null, wenn es dort keins gibt. */
function wordAt(
  segments: Segment[] | null | undefined,
  segIdx: number,
  wordIdx: number,
): TimingNeighbor | null {
  const seg = segments?.[segIdx];
  const w = seg?.words?.[wordIdx];
  if (!w || typeof w.start !== "number" || typeof w.end !== "number") return null;
  return { segIdx, wordIdx, text: w.word ?? "", start: w.start, end: w.end };
}

/**
 * Die Nachbarwörter im WORT-FLOW — segmentübergreifend, wie die Monotonie
 * des Servers: n-1 ist das vorige Wort (am Segmentanfang das letzte Wort des
 * vorigen Segments), n+1 das nächste (am Segmentende das erste Wort des
 * nächsten Segments). Gibt es keinen Nachbarn, ist der Wert null.
 */
export function neighborWords(
  segments: Segment[] | null | undefined,
  segIdx: number,
  wordIdx: number,
): { prev: TimingNeighbor | null; next: TimingNeighbor | null } {
  const words = segments?.[segIdx]?.words ?? [];
  let prev: TimingNeighbor | null = null;
  let next: TimingNeighbor | null = null;
  if (wordIdx > 0) {
    prev = wordAt(segments, segIdx, wordIdx - 1);
  } else if (segIdx > 0) {
    const prevSeg = segments?.[segIdx - 1];
    const n = prevSeg?.words?.length ?? 0;
    if (n > 0) prev = wordAt(segments, segIdx - 1, n - 1);
  }
  if (wordIdx < words.length - 1) {
    next = wordAt(segments, segIdx, wordIdx + 1);
  } else if (segIdx >= 0 && segIdx < (segments?.length ?? 0) - 1) {
    const nextWords = segments?.[segIdx + 1]?.words ?? [];
    if (nextWords.length > 0) next = wordAt(segments, segIdx + 1, 0);
  }
  return { prev, next };
}

/**
 * Berührte Kanten der Nachbarn mitschrumpfen (Live-Vorschau).
 *
 * Nur die Kante, die das aktive Wort tatsächlich überfährt, wandert — der
 * Vorgänger endet dann am neuen Wortanfang, der Nachfolger beginnt am neuen
 * Wortende. Ein Nachbar, den man nicht berührt, bleibt unverändert (er wächst
 * auch nicht nach, wenn das aktive Wort kleiner wird).
 */
export function shrinkNeighborEdges(
  current: { start: number; end: number },
  prev: TimingNeighbor | null,
  next: TimingNeighbor | null,
  minDur: number = MIN_WORD_DURATION_S,
): { prev: TimingNeighbor | null; next: TimingNeighbor | null } {
  let newPrev = prev;
  let newNext = next;
  if (prev && current.start < prev.end - 1e-6) {
    // Mindestdauer des Vorgängers bleibt: er endet nie vor start + minDur.
    const floor = Math.min(prev.end, prev.start + minDur);
    newPrev = { ...prev, end: Math.max(floor, current.start) };
  }
  if (next && current.end > next.start + 1e-6) {
    const ceil = Math.max(next.start, next.end - minDur);
    newNext = { ...next, start: Math.min(ceil, current.end) };
  }
  return { prev: newPrev, next: newNext };
}
