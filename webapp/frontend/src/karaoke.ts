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
 */
export function isWordActive(w: KaraokeWord, currentTime: number): boolean {
  return currentTime >= w.start && currentTime < w.end;
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
