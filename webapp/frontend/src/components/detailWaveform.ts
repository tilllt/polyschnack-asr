/** Change 199: Detailwellenform über der residenten Welle (pure Logik).
 *
 *  Im Timing-Modus und PAUSIERT zeichnet eine Overlay-Ebene das sichtbare
 *  Fenster aus dem Detail-Sidecar (1000 Bins/s, per Range geladen). Beim
 *  Abspielen ist die Ebene aus — es wird dann nichts nachgeladen, und die
 *  residente Welle (die im Speicher liegt) bleibt sichtbar.
 *
 *  Der Wechsel grob → fein wird mit einer kurzen Blende gerahmt: erst
 *  Pixelrauschen, das sich auflöst. Reine Canvas-Körnung, keine CSS-Filter.
 */

/** Dauer der Rauschphase in ms. */
export const ENHANCE_NOISE_MS = 120;
/** Gesamtdauer der Blende in ms (Rauschen + Auflösen). */
export const ENHANCE_TOTAL_MS = 320;

export type EnhancePhase = "idle" | "noise" | "resolve" | "sharp";

/** Phase der Blende zu einem Zeitpunkt nach dem Pausieren.
 *
 *  `reducedMotion` (prefers-reduced-motion) überspringt die Animation
 *  vollständig: sofort scharf, keine Körnung — die Information ist in beiden
 *  Fällen dieselbe, nur die Einblendung entfällt. */
export function enhancePhase(elapsedMs: number, reducedMotion = false): EnhancePhase {
  if (reducedMotion) return elapsedMs < 0 ? "idle" : "sharp";
  if (elapsedMs < 0) return "idle";
  if (elapsedMs < ENHANCE_NOISE_MS) return "noise";
  if (elapsedMs < ENHANCE_TOTAL_MS) return "resolve";
  return "sharp";
}

/** Stärke der Körnung 0..1 — in der Rauschphase voll, danach linear aus. */
export function grainAmount(elapsedMs: number, reducedMotion = false): number {
  if (reducedMotion) return 0;
  if (elapsedMs <= 0) return 0;
  if (elapsedMs < ENHANCE_NOISE_MS) return 1;
  if (elapsedMs >= ENHANCE_TOTAL_MS) return 0;
  return (
    1 - (elapsedMs - ENHANCE_NOISE_MS) / (ENHANCE_TOTAL_MS - ENHANCE_NOISE_MS)
  );
}

/** Läuft die Blende noch? (steuert requestAnimationFrame) */
export function enhanceRunning(elapsedMs: number, reducedMotion = false): boolean {
  return !reducedMotion && elapsedMs >= 0 && elapsedMs < ENHANCE_TOTAL_MS;
}

/** Ist die Detail-Ebene sichtbar?
 *
 *  Nur im Timing-Modus UND pausiert. Während des Abspielens wird bewusst
 *  nichts angezeigt und nichts angefordert: die Naht zwischen grob und fein
 *  wäre beim Scrollen sichtbar, und die residente Auflösung genügt zum
 *  Zusehen. */
export function detailLayerVisible(timingZoom: boolean, playing: boolean): boolean {
  return Boolean(timingZoom) && !playing;
}

/** Ein Bin pro Pixel, Maximum je Gruppe — für ein Zeitfenster.
 *
 *  *bytes* sind die geladenen Bins ab *firstBin* (gepolstertes Fenster),
 *  *win* ist der sichtbare Zeitausschnitt. Der Ausschnitt wird auf die Breite
 *  abgebildet (nicht das ganze geladene Fenster — das ist bewusst größer).
 *
 *  Sind mehr Bins als Pixel vorhanden (der Normalfall im Wort-Zoom), wird je
 *  Pixel das Maximum genommen. Sind weniger Bins als Pixel da, wird jeder Bin
 *  über mehrere Pixel gestreckt.
 */
export function windowColumns(
  bytes: Uint8Array,
  firstBin: number,
  win: { start: number; end: number },
  width: number,
  bps = 1000,
): Uint8Array {
  const w = Math.max(1, Math.floor(width));
  const out = new Uint8Array(w);
  const n = bytes.length;
  if (n === 0) return out;
  const span = Math.max(1e-6, win.end - win.start);
  for (let px = 0; px < w; px += 1) {
    const t0 = win.start + (px / w) * span;
    const t1 = win.start + ((px + 1) / w) * span;
    let a = Math.floor(t0 * bps) - firstBin;
    let b = Math.ceil(t1 * bps) - 1 - firstBin;
    if (a < 0) a = 0;
    if (a > n - 1) a = n - 1;
    if (b < a) b = a;
    if (b > n - 1) b = n - 1;
    let m = 0;
    for (let i = a; i <= b; i += 1) {
      if (bytes[i] > m) m = bytes[i];
    }
    out[px] = m;
  }
  return out;
}

/** Deterministischer Zufall für die Körnung (kein Math.random im Render —
 *  sonst flackert die Ebene bei jedem Frame unterschiedlich und ein Test
 *  könnte nichts festnageln). */
export function grainValue(seed: number, index: number): number {
  let x = (seed * 1103515245 + (index + 1) * 12345) & 0x7fffffff;
  x = (x ^ (x >>> 13)) * 1274126177 & 0x7fffffff;
  return ((x >>> 8) & 0xffff) / 0xffff;
}

/** Zeichenparameter eines Balkens (1 Bin-Spalte pro Pixel).
 *  `center` ist die Nulllinie, `amp` die halbe Höhe bei Vollausschlag. */
export function columnRect(
  value: number,
  px: number,
  height: number,
): { x: number; w: number; y: number; h: number } {
  const mid = height / 2;
  const amp = Math.max(0, Math.min(1, value / 255)) * (mid - 1);
  const h = Math.max(1, amp * 2);
  return { x: px, w: 1, y: mid - h / 2, h };
}

/** Schätzt, ob `prefers-reduced-motion: reduce` gesetzt ist.
 *  In Nicht-Browser-Umgebungen (Tests, SSR) sicher `false`. */
export function prefersReducedMotion(): boolean {
  try {
    return (
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    );
  } catch {
    return false;
  }
}
