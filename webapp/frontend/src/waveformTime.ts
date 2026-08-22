/** Change 083: Waveform-Zeit-Berechnung (pure Helfer, ohne WaveSurfer-Import).

 *  Problem (User-Befund 22.08.): Der Initial-Zoom zeigte bei langen Audios
 *  nur einen Ausschnitt (minPxPerSec=1 → fit unmöglich) und der Klick-Seek
 *  ignorierte Zoom/Scroll → „Klick springt zu weit entfernte Stellen".
 */
export const MIN_PPS = 0.05; // px/s — erlaubt echten Fit auch für 2h-Audios

/** px/s für „ganze Aufnahme sichtbar" (fit), nie kleiner als MIN_PPS. */
export function fitPps(containerW: number, duration: number): number {
  return Math.max(MIN_PPS, containerW / Math.max(duration, 1));
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
