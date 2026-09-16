/** Change 083: Waveform-Zeit-Berechnung (pure Helfer, ohne WaveSurfer-Import).

 *  Problem (User-Befund 22.08.): Der Initial-Zoom zeigte bei langen Audios
 *  nur einen Ausschnitt (minPxPerSec=1 → fit unmöglich) und der Klick-Seek
 *  ignorierte Zoom/Scroll → „Klick springt zu weit entfernte Stellen".
 */
export const MIN_PPS = 0.05; // px/s — erlaubt echten Fit auch für 2h-Audios

/** Change 137 (Timing-Tab): oberste Zoom-Grenze für die Wort-Detailansicht.
 *  Sehr kurze Wörter (< 100 ms) würden sonst auf absurde px/s explodieren
 *  (die Peaks-Auflösung rendert dann ohnehin gestreckte Balken).
 *  Change 196-Folge: 2000 war zu niedrig — ein 20-ms-Wort (MIN_WORD_DURATION_S)
 *  erreichte nur 4 % der Containerbreite statt der angepeilten 30 % und war
 *  damit im Timing-Tab praktisch nicht markierbar. 48000 lässt die
 *  Mindest-Wortdauer ihr Zielfenster treffen (1000 px: 15000 px/s). */
export const MAX_TIMING_PPS = 48000;

/** Change 137: kürzeste sinnvolle Wortdauer im Timing-Tab (Backend-Regel
 *  MIN_WORD_DURATION_S = 0.02 — identisch halten). */
export const MIN_WORD_DURATION_S = 0.02;

/** Change 199: Speicherbudget des residenten Envelopes, in Bytes (= Bins,
 *  uint8). Muss zum Backend passen (`peaks.RESIDENT_BIN_BUDGET`). */
export const RESIDENT_BIN_BUDGET = 2_097_152;

/** Change 199: Auflösung des Detail-Envelopes in Bins/s (Backend `HI_BPS`). */
export const HI_BPS = 1000;

/** Change 199: gemessene Browser-Breitengrenze für Elementbreiten (2^25 px).
 *  WaveSurfer setzt die Gesamtbreite auf `Dauer × px/s`; darüber kappt der
 *  Browser stillschweigend. Der erreichbare Zoom ist damit `2^25 / Dauer`. */
export const MAX_ELEMENT_PX = 33_554_428;

/** Change 199: Auflösung des residenten Envelopes (Bins/s).
 *  `min(HI_BPS, BUDGET / Dauer)` — bei langen Aufnahmen sinkt die Auflösung,
 *  die geladene Datenmenge bleibt aber konstant bei ≤ BUDGET Bytes. */
export function residentBinsPerSecond(duration: number): number {
  if (!(duration > 0)) return HI_BPS;
  return Math.min(HI_BPS, RESIDENT_BIN_BUDGET / duration);
}

/** Change 199: Bin-Anzahl des residenten Envelopes (Backend-Formel). */
export function residentBinCount(duration: number): number {
  return Math.max(1, Math.round(residentBinsPerSecond(duration) * duration));
}

/** Change 199: Bin-Anzahl des Detail-Envelopes (1000 Bins/s). */
export function hiBinCount(duration: number): number {
  return Math.max(1, Math.round(Math.max(duration, 0) * HI_BPS));
}

/** Change 199: effektiv erreichbarer Maximalzoom in px/s.
 *
 *  `MAX_TIMING_PPS` (48000) gilt nur bis `2^25 / Dauer` — ab ~11,7 min
 *  deckelt die Browser-Breitengrenze, bei 262 min sind es noch 2135 px/s.
 *  Die Grenze gehört zur Zoom-Mechanik, nicht zur Datenquelle: die
 *  Detailwellenform liefert die Auflösung, nur die Breite fehlt.
 */
export function effectiveMaxPps(duration: number): number {
  if (!(duration > 0)) return MAX_TIMING_PPS;
  return Math.min(MAX_TIMING_PPS, MAX_ELEMENT_PX / duration);
}

/** Change 199: lässt die Breitengrenze das 30-%-Zielfenster eines Wortes von
 *  *wordDuration* Sekunden noch zu?
 *
 *  Ersetzt die Zusicherung aus Change 197 („ein Wort erreicht immer sein
 *  30-%-Fenster"), die auf langen Dateien nicht haltbar ist: ein 0,1-s-Wort
 *  sind bei 2135 px/s nur 213 px statt 300. Statt einer Zusicherung, die der
 *  Browser nicht einhalten kann, wird die Grenze hier abfragbar. */
export function timingTargetReachable(
  containerW: number,
  duration: number,
  wordDuration: number = MIN_WORD_DURATION_S,
): boolean {
  const needed = (0.3 * Math.max(containerW, 1)) / Math.max(wordDuration, 1e-3);
  return needed <= effectiveMaxPps(duration);
}

/** Change 199: Bin-Bereich eines Zeitfensters im Detail-Sidecar.
 *
 *  Grundlage für die Frage „deckt das Geladene das Sichtbare noch ab?".
 *  Wichtig: hier gehört KEIN Puffer hinein. Ein Puffer klebt am Fenster und
 *  wandert beim Scrollen mit — geprüft wird die nackte Sicht, gepuffert wird
 *  nur die Anfrage (`detailByteRange`). */
export function windowBinRange(
  win: { start: number; end: number },
  duration: number,
): { start: number; end: number } {
  const last = hiBinCount(duration) - 1;
  const start = Math.max(
    0,
    Math.min(last, Math.floor(Math.max(0, win.start) * HI_BPS)),
  );
  const end = Math.max(
    start,
    Math.min(last, Math.ceil(Math.max(0, win.end) * HI_BPS) - 1),
  );
  return { start, end };
}

/** Change 199: Bin-Bereich, der für ein sichtbares Zeitfenster angefordert
 *  wird — mit *pad* Überschuss auf beiden Seiten.
 *
 *  Der Überschuss bestimmt, wie weit gescrollt werden kann, ohne dass eine
 *  neue Anfrage fällig wird: bei `pad = 0.5` und einem 1-s-Fenster sind das
 *  0,5 s in jede Richtung. Bei 1000 Bins/s ist die Zahl der übertragenen
 *  Bytes genau `end - start + 1` — ein 1-s-Fenster ≈ 2 KB statt der 6 MB des
 *  JSON-Wegs. */
export function detailByteRange(
  win: { start: number; end: number },
  duration: number,
  pad = 0.5,
): { start: number; end: number } {
  const span = Math.max(1e-6, win.end - win.start);
  const from = Math.max(0, win.start - span * pad);
  const to = Math.min(Math.max(duration, 0), win.end + span * pad);
  return windowBinRange({ start: from, end: to }, duration);
}

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
