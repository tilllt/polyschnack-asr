/* ============================================================
   KARAOKE — Wort-Hervorhebung beim Playback
   ============================================================ */

export interface KaraokeWord {
  word: string;
  start: number;
  end: number;
}

export interface KaraokeSegment {
  start: number;
  end: number;
  text: string;
  speaker?: string;
  words?: KaraokeWord[];
}

/**
 * Ist das Wort zum Zeitpunkt `currentTime` aktiv (wird gerade gesprochen)?
 *
 * Regel (identisch mit der alten Inline-Logik in SegmentList):
 *   currentTime >= w.start && currentTime < w.end
 *
 * Hinweis: Für die *Anzeige* nutze `activeWordIndex` — die liefert auch bei
 * Timestamp-Lücken/Überlappungen immer genau ein aktives Wort (kein Glitch).
 */
export function isWordActive(w: KaraokeWord, currentTime: number): boolean {
  return currentTime >= w.start && currentTime < w.end;
}

/**
 * Lückenloser aktiver Wort-Index für die Karaoke-Anzeige.
 *
 * Das aktive Wort ist das letzte, dessen `start <= currentTime` — d.h. die
 * Markierung wandert nahtlos von Wort zu Wort, auch wenn die ASR-Timestamps
 * Lücken (w[i].end < w[i+1].start) oder Überlappungen (w[i+1].start < w[i].end)
 * enthalten. Vor dem ersten Wort → -1 (nichts aktiv).
 *
 * Beispiele:
 *   words = [{start:0,end:1},{start:1.2,end:2}]  (Lücke 1.0–1.2)
 *     t=0.9 → 0, t=1.1 → 0 (kein Glitch!), t=1.2 → 1
 *   words = [{start:0,end:1.5},{start:1.2,end:2}] (Überlappung)
 *     t=1.3 → 1 (das neuere Wort gewinnt, kein Doppel-Highlight)
 */
export function activeWordIndex(
  words: KaraokeWord[] | undefined,
  currentTime: number,
): number {
  if (!words || words.length === 0) return -1;
  const t = currentTime;
  if (t < words[0].start) return -1;
  let idx = 0;
  for (let i = 0; i < words.length; i++) {
    if (t >= words[i].start) idx = i;
    else break;
  }
  return idx;
}

/**
 * Liefert den Index des aktiven Segments zum Zeitpunkt `currentTime`
 * (-1 wenn keins). Basis für Auto-Scroll + Karaoke.
 */
export function activeSegmentIndex(
  segments: KaraokeSegment[],
  currentTime: number,
): number {
  if (!segments || segments.length === 0) return -1;
  for (let i = 0; i < segments.length; i++) {
    const s = segments[i];
    if (currentTime >= s.start && currentTime < s.end) return i;
  }
  // Nach dem letzten Segment-Ende → letztes Segment
  const last = segments[segments.length - 1];
  if (currentTime >= (last?.end ?? 0)) return segments.length - 1;
  return -1;
}

/**
 * Karaoke-fähig? Ein Segment ist karaoke-fähig, wenn es Wörter MIT
 * gültigen Timestamps hat (start/end als Zahlen, end > start).
 * Nach Diarization-Merge und Edit müssen die Wörter diese Form behalten.
 */
export function isKaraokeReady(seg: KaraokeSegment): boolean {
  const words = seg.words;
  if (!words || words.length === 0) return false;
  return words.every(
    (w) =>
      typeof w.start === "number" &&
      typeof w.end === "number" &&
      w.end > w.start,
  );
}
