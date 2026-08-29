/** Change 083: Waveform-Zeit-Berechnung (pure Helfer, ohne WaveSurfer-Import).

 *  Problem (User-Befund 22.08.): Der Initial-Zoom zeigte bei langen Audios
 *  nur einen Ausschnitt (minPxPerSec=1 → fit unmöglich) und der Klick-Seek
 *  ignorierte Zoom/Scroll → „Klick springt zu weit entfernte Stellen".
 */
export const MIN_PPS = 0.05; // px/s — erlaubt echten Fit auch für 2h-Audios

/** Change 137 (Timing-Tab): oberste Zoom-Grenze für die Wort-Detailansicht.
 *  Sehr kurze Wörter (< 100 ms) würden sonst auf absurde px/s explodieren
 *  (die Peaks-Auflösung rendert dann ohnehin gestreckte Balken). */
export const MAX_TIMING_PPS = 2000;

/** Change 137: kürzeste sinnvolle Wortdauer im Timing-Tab (Backend-Regel
 *  MIN_WORD_DURATION_S = 0.02 — identisch halten). */
export const MIN_WORD_DURATION_S = 0.02;

/** px/s für „ganze Aufnahme sichtbar" (fit), nie kleiner als MIN_PPS. */
export function fitPps(containerW: number, duration: number): number {
  return Math.max(MIN_PPS, containerW / Math.max(duration, 1));
}

/** Change 137 (Timing-Tab): px/s, damit die Wortdauer ~30 % der sichtbaren
 *  Zeitspanne belegt — geclampt auf [minPps, MAX_TIMING_PPS].
 *  visible_duration = Wortdauer / 0.30 → pps = Breite / visible_duration. */
export function timingPps(
  containerW: number,
  wordDuration: number,
  minPps: number = MIN_PPS,
  maxPps: number = MAX_TIMING_PPS,
): number {
  const dur = Math.max(wordDuration, 1e-3);
  const pps = (0.3 * Math.max(containerW, 1)) / dur;
  return Math.max(minPps, Math.min(maxPps, pps));
}

/** Change 137 (Timing-Tab): Wort-Timing auf erlaubte Grenzen clammen.
 *  Regeln (Design Change 137): start < end, Mindestdauer, Monotonie gegen
 *  die Nachbarn (minStart = Ende des Vorgängers, maxEnd = Start des
 *  Folgeworts) — Lücken erlaubt, Überlappungen nicht. Das Frontend clampt
 *  beim Drag; der Backend-PATCH lehnt Verstöße mit 400 ab. */
export function clampWordTiming(
  start: number,
  end: number,
  minStart: number | undefined,
  maxEnd: number | undefined,
  minDur: number = MIN_WORD_DURATION_S,
): { start: number; end: number } {
  const lo = minStart != null ? minStart : Number.NEGATIVE_INFINITY;
  const hi = maxEnd != null ? maxEnd : Number.POSITIVE_INFINITY;
  let s = Math.max(lo, Math.min(end - minDur, start));
  let e = Math.min(hi, Math.max(s + minDur, end));
  // minDur kann die Lücke sprengen (Nachbarn näher als 20 ms) → dann so
  // eng wie möglich an die Grenzen legen (Chronologie hat Vorrang).
  if (s + minDur > e) {
    s = Math.max(lo, e - minDur);
    e = Math.min(hi, s + minDur);
    if (s < lo) {
      s = lo;
      e = Math.min(hi, Math.max(s + 1e-3, e));
    }
  }
  return { start: s, end: e };
}

/** Klick-Position (px, relativ zum sichtbaren Container) → Zeit (s).
 *  Korrekt bei Fit-Ansicht UND bei gezoomter/gescrollter View:
 *  absolute px-Position in der Wellenform = scrollPx + clickPx. */
export function timeFromClick(
  clickPx: number,
  scrollPx: number,
  pps: number,
  duration: number,
): number {
  const t = (scrollPx + Math.max(0, clickPx)) / Math.max(pps, MIN_PPS);
  return Math.max(0, Math.min(duration, t));
}

/** Change 155 (Timing-Zoom): sichtbares Zeitfenster des Containers.
 *  Bei Fit (scrollPx=0, pps=fitPps) ist das Fenster = [0, duration]. */
export function visibleWindow(
  containerW: number,
  scrollPx: number,
  pps: number,
  duration: number,
): { start: number; end: number } {
  const p = Math.max(pps, MIN_PPS);
  const start = Math.max(0, scrollPx / p);
  const end = Math.min(duration, start + Math.max(containerW, 1) / p);
  return { start, end };
}

/** Change 155 (Timing-Zoom): Marker-Position relativ zum SICHTBAREN
 *  Fenster (vorher: relativ zur Gesamtdauer — im Zoom lag der Marker
 *  daneben). Liefert left/width in % des Containers. */
export function markerPct(
  win: { start: number; end: number },
  start: number,
  end: number,
): { left: number; width: number } {
  const span = Math.max(1e-6, win.end - win.start);
  return {
    left: ((start - win.start) / span) * 100,
    width: (Math.max(0, end - start) / span) * 100,
  };
}

/** Change 155 (Timing-Zoom): GANZE Markierung verschieben (Body-Drag) —
 *  start UND end wandern gemeinsam, Länge bleibt, geclampt auf die
 *  Nachbar-Grenzen (minStart/maxEnd) und die Mindestdauer. */
export function clampMoveWordTiming(
  start: number,
  end: number,
  dT: number,
  minStart: number | undefined,
  maxEnd: number | undefined,
  minDur: number = MIN_WORD_DURATION_S,
): { start: number; end: number } {
  const len = Math.max(minDur, end - start);
  const lo = minStart != null ? minStart : Number.NEGATIVE_INFINITY;
  const hi = maxEnd != null ? maxEnd : Number.POSITIVE_INFINITY;
  const s = Math.max(lo, Math.min(hi - len, start + dT));
  return { start: s, end: Math.min(hi, s + len) };
}
