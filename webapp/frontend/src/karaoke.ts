/* ============================================================
   KARAOKE — Wort-Hervorhebung beim Playback
   ============================================================ */

export interface KaraokeWord {
  word: string;
  start: number;
  end: number;
  /** Per-Token-Confidence 0.0-1.0 — optional, nur wenn das Backend sie
   *  liefert (CrispASR `probability`). Fehlt → keine Färbung. */
  confidence?: number;
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
 * `leadS` (Review-Fix 2026-08-15): Vorlauf in Sekunden, mit dem das Wort
 * aktiv wird, BEVOR `currentTime` den Wortstart erreicht. Der Aligner liefert
 * 80-ms-Bins, die real oft ~0.1–0.2 s NACH dem akustischen Sprechbeginn
 * liegen — ohne Vorlauf sprang das Highlight erst, wenn das Wort fast vorbei
 * war. Mit KARAOKE_LEAD_S erscheint die Markierung am ANFANG des Wortes.
 *
 * Beispiele:
 *   words = [{start:0,end:1},{start:1.2,end:2}]  (Lücke 1.0–1.2)
 *     t=0.9 → 0, t=1.1 → 0 (kein Glitch!), t=1.2 → 1
 *   words = [{start:0,end:1.5},{start:1.2,end:2}] (Überlappung)
 *     t=1.3 → 1 (das neuere Wort gewinnt, kein Doppel-Highlight)
 */
export const KARAOKE_LEAD_S = 0.15; // Vorlauf: Markierung am Wortanfang

export function activeWordIndex(
  words: KaraokeWord[] | undefined,
  currentTime: number,
  leadS: number = KARAOKE_LEAD_S,
): number {
  if (!words || words.length === 0) return -1;
  const t = currentTime + leadS;
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

/**
 * Ziel-Wort für die Tastatur-Navigation (Cursor ←/→, Feature 2026-08-16).
 *
 * Gibt `{ segIdx, wIdx }` des Wortes NACH (`dir=1`) bzw. VOR (`dir=-1`)
 * dem aktuell aktiven Wort zurück — segmentübergreifend. Basis ist das
 * aktive Segment + aktives Wort (aus currentTime). Gibt null zurück, wenn
 * es kein Ziel gibt (Anfang/Ende der Transkription erreicht).
 */
export function nextWordTarget(
  segments: KaraokeSegment[],
  activeIdx: number,
  currentTime: number,
  dir: 1 | -1,
): { segIdx: number; wIdx: number } | null {
  if (!segments || segments.length === 0 || activeIdx < 0) return null;
  const seg = segments[activeIdx];
  if (!seg) return null;
  const words = seg.words ?? [];
  if (words.length === 0) return null;
  const aw = currentTime >= 0 ? activeWordIndex(words, currentTime) : -1;

  if (dir === 1) {
    // erstes Wort im selben Segment, sonst erstes Wort des nächsten Segments
    if (aw + 1 < words.length) return { segIdx: activeIdx, wIdx: aw + 1 };
    for (let i = activeIdx + 1; i < segments.length; i++) {
      if ((segments[i].words ?? []).length > 0) return { segIdx: i, wIdx: 0 };
    }
    return null;
  }
  // dir === -1
  if (aw > 0) return { segIdx: activeIdx, wIdx: aw - 1 };
  for (let i = activeIdx - 1; i >= 0; i--) {
    const w = segments[i].words ?? [];
    if (w.length > 0) return { segIdx: i, wIdx: w.length - 1 };
  }
  return null;
}

/**
 * Soll der SegmentList-Container zum aktiven Segment scrollen?
 *
 * Ein Element gilt als sichtbar, wenn es VOLLSTÄNDIG im sichtbaren Bereich
 * liegt (top >= scrollTop UND bottom <= scrollTop + clientHeight). Reicht nur
 * der obere Rand ins Bild (bottom abgeschnitten), wird gescrollt — das
 * behebt den Bug, dass unten abgeschnittene Segmente nie nachrutschten.
 *
 * @param scrollTop    container.scrollTop
 * @param clientHeight container.clientHeight
 * @param elTop        Element-Offset relativ zum Container
 * @param elBottom     elTop + Element-Höhe
 */
export function shouldScrollIntoView(
  scrollTop: number,
  clientHeight: number,
  elTop: number,
  elBottom: number,
): boolean {
  if (!Number.isFinite(elTop) || !Number.isFinite(elBottom)) return false;
  if (clientHeight <= 0) return false;
  const viewBottom = scrollTop + clientHeight;
  return elTop < scrollTop || elBottom > viewBottom;
}

/* ============================================================
   CONFIDENCE-FÄRBUNG (Task 3) — Per-Token-Confidence
   ============================================================ */

/**
 * Ampel für die Confidence eines Wortes.
 *
 * - `>= 0.90` → "high"   (grün — sehr sicher)
 * - `>= 0.70` → "medium" (gelb/amber — mittel)
 * - sonst     → "low"    (rot — unsicher, prüfen)
 *
 * `undefined`/NaN → null (keine Färbung; Backend liefert keine Confidence).
 */
export type ConfidenceTier = "high" | "medium" | "low";

export function confidenceTier(c?: number): ConfidenceTier | null {
  if (typeof c !== "number" || Number.isNaN(c)) return null;
  if (c >= 0.9) return "high";
  if (c >= 0.7) return "medium";
  return "low";
}

/** CSS-Klasse pro Confidence-Tier (Wort-Span im SegmentList). */
export function confidenceClass(c?: number): string {
  const tier = confidenceTier(c);
  if (tier === "high") return "conf-high";
  if (tier === "medium") return "conf-medium";
  if (tier === "low") return "conf-low";
  return "";
}

/**
 * Hat das Segment überhaupt Confidence-Daten (mindestens ein Wort mit
 * Zahl >= 0)? Nur dann wird die Färbung aktiviert — sonst sieht der Text
 * unverändert aus (kein Fake-Wert, keine verblassten Standard-Wörter).
 */
export function hasConfidence(words: KaraokeWord[] | undefined): boolean {
  return !!words && words.some((w) => typeof w.confidence === "number" && !Number.isNaN(w.confidence));
}
