/** Change 199: Overlay mit der Detailwellenform über der residenten Welle.
 *
 *  Nur im Timing-Modus UND pausiert sichtbar — beim Abspielen wird weder
 *  gezeichnet noch geladen. Beim Pausieren lädt die Ebene das sichtbare
 *  Fenster (± 50 % Überschuss) aus dem Detail-Sidecar per Range und rahmt
 *  den Wechsel grob → fein mit einer kurzen Rausch-Blende.
 *
 *  Fehlt das Sidecar (Altaufnahme, deren Nachlauf noch aussteht), bleibt die
 *  residente Welle stehen und der Aufrufer erfährt es über `onUnavailable` —
 *  ein stiller Fehlschlag wäre von „es gibt hier nichts zu sehen" nicht zu
 *  unterscheiden.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { fetchPeaksBinary } from "../api";
import { HI_BPS, detailByteRange, windowBinRange } from "../waveformTime";
import {
  columnRect,
  detailLayerVisible,
  enhanceRunning,
  grainAmount,
  grainValue,
  prefersReducedMotion,
  windowColumns,
} from "./detailWaveform";

type Props = {
  recordingId?: string | null;
  duration: number;
  win: { start: number; end: number };
  playing: boolean;
  timingZoom: boolean;
  width: number;
  height?: number;
  color?: string;
  onUnavailable?: () => void;
  onLoaded?: () => void;
};

export function DetailWaveformLayer({
  recordingId,
  duration,
  win,
  playing,
  timingZoom,
  width,
  height = 80,
  color = "#2ea043",
  onUnavailable,
  onLoaded,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const bytesRef = useRef<Uint8Array | null>(null);
  const firstBinRef = useRef(0);
  const blendStartRef = useRef<number | null>(null);
  const rafRef = useRef<number | null>(null);
  const [nonce, setNonce] = useState(0);
  const [haveData, setHaveData] = useState(false);

  const visible = detailLayerVisible(timingZoom, playing) && Boolean(recordingId);

  // Beim Wechsel der Aufnahme die gepufferten Daten verwerfen.
  useEffect(() => {
    bytesRef.current = null;
    firstBinRef.current = 0;
    blendStartRef.current = null;
    setHaveData(false);
  }, [recordingId]);

  // Laden — nur im sichtbaren Zustand, und nur wenn das Gepufferte das
  // Fenster nicht schon abdeckt.
  useEffect(() => {
    if (!visible || !recordingId || !(duration > 0)) return;
    const need = detailByteRange(win, duration);
    // Geprüft wird die NACKTE Sicht, nicht das gepufferte Fenster: ein Puffer,
    // der am Fenster klebt, wandert beim Scrollen mit und deckt nie etwas ab.
    const sicht = windowBinRange(win, duration);
    const have = bytesRef.current;
    if (
      have &&
      firstBinRef.current <= sicht.start &&
      firstBinRef.current + have.length - 1 >= sicht.end
    ) {
      return;
    }
    let cancelled = false;
    fetchPeaksBinary(recordingId, "hi", need)
      .then((b) => {
        if (cancelled) return;
        bytesRef.current = b;
        firstBinRef.current = need.start;
        blendStartRef.current = performance.now();
        setHaveData(true);
        setNonce((n) => n + 1);
        onLoaded?.();
      })
      .catch(() => {
        if (!cancelled) onUnavailable?.();
      });
    return () => {
      cancelled = true;
    };
  }, [visible, recordingId, duration, win.start, win.end, onUnavailable, onLoaded]);

  const draw = useCallback(() => {
    const cv = canvasRef.current;
    if (!cv) return;
    const ctx = cv.getContext("2d");
    if (!ctx) return;
    const w = cv.width;
    const h = cv.height;
    ctx.clearRect(0, 0, w, h);
    const bytes = bytesRef.current;
    if (!bytes || bytes.length === 0) return;

    const cols = windowColumns(bytes, firstBinRef.current, win, w, HI_BPS);
    const start = blendStartRef.current;
    const elapsed = start == null ? Number.POSITIVE_INFINITY : performance.now() - start;
    const reduced = prefersReducedMotion();
    const grain = grainAmount(elapsed, reduced);

    // Wellenform: ein Bin-Spaltenmaximum pro Pixel.
    ctx.fillStyle = color;
    for (let px = 0; px < w; px += 1) {
      const r = columnRect(cols[px], px, h);
      ctx.fillRect(r.x, r.y, r.w, r.h);
    }

    // Rauschphase: Pixelkörnung über der (noch groben) Form, die sich auflöst.
    if (grain > 0) {
      const seed = (start ?? 0) | 0;
      for (let px = 0; px < w; px += 1) {
        for (let d = 0; d < 3; d += 1) {
          const g = grainValue(seed, px * 7 + d);
          if (g > grain) continue;
          const yy = Math.floor(grainValue(seed + 3, px * 13 + d) * h);
          const xx = px + Math.round(grainValue(seed + 7, px * 17 + d)) - 1;
          ctx.fillStyle = `rgba(214,255,224,${(0.2 + 0.55 * grain).toFixed(3)})`;
          ctx.fillRect(xx, yy, 1, 1);
        }
      }
    }
  }, [win, color]);

  // Zeichnen + Blend-Schleife. Läuft nur, solange die Blende läuft.
  useEffect(() => {
    if (!visible) return;
    draw();
    const start = blendStartRef.current;
    if (start == null) return;
    if (!enhanceRunning(performance.now() - start, prefersReducedMotion())) return;
    const tick = () => {
      draw();
      const el = performance.now() - (blendStartRef.current ?? 0);
      if (enhanceRunning(el, prefersReducedMotion())) {
        rafRef.current = requestAnimationFrame(tick);
      } else {
        rafRef.current = null;
        draw();
      }
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    };
  }, [visible, draw, nonce, win.start, win.end, width, height]);

  if (!visible || !haveData) return null;

  return (
    <canvas
      ref={canvasRef}
      width={Math.max(1, Math.floor(width))}
      height={height}
      aria-hidden
      className="absolute left-0 top-0 pointer-events-none"
      style={{ width: "100%", height: `${height}px` }}
    />
  );
}
