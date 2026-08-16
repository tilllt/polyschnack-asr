import { useEffect, useRef, useState, useCallback, useImperativeHandle, forwardRef } from "react";
import WaveSurfer from "wavesurfer.js";
import RegionsPlugin from "wavesurfer.js/dist/plugins/regions.js";
import TimelinePlugin from "wavesurfer.js/dist/plugins/timeline.js";
import HoverPlugin from "wavesurfer.js/dist/plugins/hover.js";

export interface WaveSurferHandle {
  seekTo: (seconds: number) => void;
  playPause: () => void;
  getCurrentTime: () => number;
  isPlaying: () => boolean;
}

interface Props {
  audioUrl: string;
  /** Server-berechnete Peak-Envelope (2000 Werte) — WaveSurfer rendert damit
   * SOFORT, ohne die Audiodatei zu dekodieren (Mini-Preview). Ohne Peaks
   * muss WaveSurfer die ganze Datei laden → bei langen Aufnahmen langsam
   * oder Timeout („Waveform data corrupted"). */
  peaks?: number[] | null;
  /** Exakte Dauer in Sekunden — nötig, damit WaveSurfer mit Peaks die
   * Timeline korrekt skaliert, ohne die Datei erst zu dekodieren. */
  durationHint?: number | null;
  onRegionChange?: (start: number, end: number) => void;
  onTimeUpdate?: (time: number) => void;
  onPlayStateChange?: (playing: boolean) => void;
  onLoadError?: () => void;
  height?: number;
}

const ZOOM_STEPS = [1, 2, 4, 6, 10, 20, 50];

/* ============================================================
   AUDIO-EXKLUSIVITÄT — immer nur EIN Player spielt app-weit.
   Modul-Singleton: der zuletzt gestartete Player pausiert den
   vorherigen (auch über mehrere RecordingCards/Benchmark-Samples
   hinweg). User-Anforderung 2026-08-15: „Wenn ein neues angeklickt
   wird, hört eins, das schon spielt, auf."
   ============================================================ */
type Playable = { pause: () => void; play: () => void; playPause: () => void; isPlaying: () => boolean };
export type { Playable };
let activePlayer: Playable | null = null;

/** Registriert `me` als aktiven Player und pausiert den vorherigen. */
export function claimExclusivePlayback(me: Playable): void {
  if (activePlayer && activePlayer !== me && activePlayer.isPlaying()) {
    activePlayer.pause();
  }
  // Immer merken (auch wenn nicht spielend): Space/Play-Shortcuts zielen
  // auf den zuletzt beanspruchten Player (Feature 2026-08-16).
  activePlayer = me;
}

/** Gibt die Exklusivität frei, wenn `me` noch der aktive Player ist. */
export function releaseExclusivePlayback(me: Playable): void {
  if (activePlayer === me) activePlayer = null;
}

/**
 * Globaler Play/Stop (Feature 2026-08-16, Space-Taste): togglet den
 * zuletzt beanspruchten Player — spielt er, wird pausiert; steht er,
 * wird gestartet. Kein aktiver Player → no-op.
 */
export function toggleActivePlayback(): void {
  const p = activePlayer;
  if (!p) return;
  if (p.isPlaying()) p.pause();
  else p.play();
}

export const WaveformPlayer = forwardRef<WaveSurferHandle, Props>(
  function WaveformPlayer({ audioUrl, peaks, durationHint, onRegionChange, onTimeUpdate, onPlayStateChange, onLoadError, height = 80 }, ref) {
    const containerRef = useRef<HTMLDivElement>(null);
    const timelineRef = useRef<HTMLDivElement>(null);
    const wsRef = useRef<WaveSurfer | null>(null);
    const regionsRef = useRef<RegionsPlugin | null>(null);
    const onTimeUpdateRef = useRef(onTimeUpdate);
    const onPlayStateRef = useRef(onPlayStateChange);
    const onRegionRef = useRef(onRegionChange);
    const onLoadErrorRef = useRef(onLoadError);
    const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    // Keep refs in sync with latest props
    onTimeUpdateRef.current = onTimeUpdate;
    onPlayStateRef.current = onPlayStateChange;
    onRegionRef.current = onRegionChange;
    onLoadErrorRef.current = onLoadError;
    const [ready, setReady] = useState(false);
    const [error, setError] = useState(false);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(0);
    const [zoomIdx, setZoomIdx] = useState(0);
    const [playing, setPlaying] = useState(false);

    const doZoom = useCallback((ws: WaveSurfer, idx: number) => {
      const pps = ZOOM_STEPS[idx];
      ws.zoom(pps);
      setZoomIdx(idx);
    }, []);

    useEffect(() => {
      if (!containerRef.current) return;

      let cancelled = false;

      const regions = RegionsPlugin.create();
      const timeline = TimelinePlugin.create({ container: timelineRef.current! });
      const hover = HoverPlugin.create();
      let ws: WaveSurfer;

      try {
        ws = WaveSurfer.create({
          container: containerRef.current,
          backend: "WebAudio",
          waveColor: "rgba(91,140,255,0.3)",
          progressColor: "rgba(91,140,255,0.8)",
          cursorColor: "#3b82f6",
          cursorWidth: 1,
          barWidth: 2,
          barGap: 1,
          barRadius: 2,
          height,
          normalize: true,
          minPxPerSec: 1,
          plugins: [regions, timeline, hover],
        });
      } catch (e) {
        setError(true);
        setReady(true);
        onLoadErrorRef.current?.();
        return;
      }

      // Peaks + Dauer vom Server → Waveform rendert sofort (Mini-Preview),
      // ohne die komplette Audiodatei im Browser zu dekodieren. WaveSurfer
      // erwartet peaks als Array-of-Channels: [peaks] = Mono. Nur wenn BEIDE
      // da sind (ohne durationHint kann WaveSurfer die Timeline nicht
      // skalieren — dann lieber selbst dekodieren).
      const hasPeaks = !!(peaks && peaks.length > 0 && durationHint && durationHint > 0);
      try {
        ws.load(
          audioUrl,
          hasPeaks ? [peaks as number[]] : undefined,
          hasPeaks ? (durationHint as number) : undefined,
        );
      } catch (e) {
        setError(true);
        setReady(true);
        onLoadErrorRef.current?.();
        return;
      }

      // Timeout safety net — mit Server-Peaks rendert WaveSurfer sofort (10s);
      // OHNE Peaks muss der Browser die ganze Datei dekodieren (WebAudio) —
      // bei langen Aufnahmen dauert das deutlich länger, der alte 10s-Timeout
      // warf dann faelschlich "Waveform data corrupted". 60s fuer den
      // Browser-Decode-Pfad.
      timerRef.current = setTimeout(() => {
        if (!cancelled) {
          setError(true);
          setReady(true);
          onLoadErrorRef.current?.();
        }
      }, hasPeaks ? 10000 : 60000);

      // WaveSurfer fires "error" when audio fails to load/decode
      ws.on("error", () => {
        if (cancelled) return;
        if (timerRef.current) clearTimeout(timerRef.current);
        setError(true);
        setReady(true);
        onLoadErrorRef.current?.();
      });

      ws.on("ready", () => {
        if (cancelled) return;
        if (timerRef.current) clearTimeout(timerRef.current);
        setReady(true);
        const dur = ws.getDuration();
        setDuration(dur);
        // Initial zoom = fit container width
        const containerW = containerRef.current?.clientWidth ?? 800;
        const fitPps = Math.max(1, Math.round(containerW / dur));
        let zi = 0;
        for (let i = 0; i < ZOOM_STEPS.length; i++) {
          if (ZOOM_STEPS[i] <= fitPps) zi = i;
        }
        doZoom(ws, zi);

        regions.addRegion({
          start: 0,
          end: dur,
          color: "rgba(91,140,255,0.08)",
          drag: true,
          resize: true,
        });
      });

      ws.on("timeupdate", (t) => { setCurrentTime(t); onTimeUpdateRef.current?.(t); });
      // Audio-Exklusivität: Start dieses Players pausiert jeden anderen.
      const me: Playable = {
        pause: () => ws.pause(),
        play: () => ws.play(),
        playPause: () => ws.playPause(),
        isPlaying: () => ws.isPlaying(),
      };
      // Beim Mount als aktiven Player merken (zuletzt geöffnete Card) —
      // damit der globale Play/Stop-Shortcut (Space) ein Ziel hat, auch
      // bevor je ein Play lief. Cleanup gibt die Exklusivität frei.
      claimExclusivePlayback(me);
      ws.on("play", () => {
        claimExclusivePlayback(me);
        setPlaying(true);
        onPlayStateRef.current?.(true);
        startSync();
      });
      ws.on("pause", () => {
        releaseExclusivePlayback(me);
        setPlaying(false);
        onPlayStateRef.current?.(false);
      });
      ws.on("finish", () => {
        releaseExclusivePlayback(me);
        setPlaying(false);
        onPlayStateRef.current?.(false);
      });

      regions.on("region-updated", (r) => onRegionRef.current?.(r.start, r.end));

      // ── Karaoke-Timing: rAF-Sync-Loop (2026-08-14) ──
      // `timeupdate` feuert nur ~4x/Sekunde (Browser-HTMLMediaElement) — das
      // Wort-Highlight hinkte dadurch bis 250ms hinterher („beginnt genau,
      // wird dann schnell ungenau"). Der rAF-Loop liest die exakte Zeit
      // direkt von der Quelle (getCurrentTime, ~40fps, 25ms-Schwelle) —
      // frame-genau und driftfrei, weil nie ein Timer akkumuliert.
      let rafId: number | null = null;
      let lastT = -1;
      const syncLoop = () => {
        const t = ws.getCurrentTime();
        if (Math.abs(t - lastT) >= 0.025) {
          lastT = t;
          setCurrentTime(t);
          onTimeUpdateRef.current?.(t);
        }
        rafId = ws.isPlaying() ? requestAnimationFrame(syncLoop) : null;
      };
      const startSync = () => {
        if (rafId == null) rafId = requestAnimationFrame(syncLoop);
      };

      wsRef.current = ws;
      regionsRef.current = regions;
      return () => {
        cancelled = true;
        if (rafId != null) cancelAnimationFrame(rafId);
        releaseExclusivePlayback(me);
        ws.destroy();
      };
    }, [audioUrl]);

    useImperativeHandle(ref, () => ({
      seekTo: (s: number) => { wsRef.current?.setTime(s); wsRef.current?.play(); },
      playPause: () => wsRef.current?.playPause(),
      getCurrentTime: () => wsRef.current?.getCurrentTime() ?? 0,
      isPlaying: () => wsRef.current?.isPlaying() ?? false,
    }), []);

    return (
      <div className="w-full">
        {!ready && (
          <div className="flex items-center justify-center h-[80px] text-muted2 text-[13px] gap-2">
            <span className="animate-spin inline-block w-4 h-4 border-2 border-current border-t-transparent rounded-full" />
            Loading waveform…
          </div>
        )}
        {error && (
          <div className="flex items-center justify-center h-[80px] text-[13px] gap-2 bg-[rgba(248,81,73,.08)] border border-err/20 rounded-sm">
            <span>⚠️</span>
            <span className="text-err">Waveform data corrupted</span>
          </div>
        )}
        <div ref={containerRef} className={`w-full ${ready && !error ? "" : "hidden"}`} />
        {/* Timeline ruler */}
        <div ref={timelineRef} className={`w-full ${ready && !error ? "mt-0" : "hidden"}`} />
        {ready && !error && (
          <div className="flex items-center gap-3 mt-2">
            <button
              onClick={() => wsRef.current?.playPause()}
              className="btn-ghost-sm text-[13px] flex items-center gap-1"
              title={playing ? "Pause" : "Play"}
            >
              {playing ? "⏸" : "▶"}
            </button>
            <span className="text-[12px] text-muted2 tabular-nums">
              {fmtTime(currentTime)} / {fmtTime(duration)}
            </span>
            <span className="flex-1" />
            <button
              onClick={() => { const w = wsRef.current; if (w) doZoom(w, Math.max(0, zoomIdx - 1)); }}
              disabled={zoomIdx <= 0}
              className="btn-ghost-sm text-[13px] px-1 disabled:opacity-30"
              title="Zoom out"
            >−</button>
            <span className="text-[11px] text-muted2 tabular-nums min-w-[36px] text-center">
              {ZOOM_STEPS[zoomIdx]}×
            </span>
            <button
              onClick={() => { const w = wsRef.current; if (w) doZoom(w, Math.min(ZOOM_STEPS.length - 1, zoomIdx + 1)); }}
              disabled={zoomIdx >= ZOOM_STEPS.length - 1}
              className="btn-ghost-sm text-[13px] px-1 disabled:opacity-30"
              title="Zoom in"
            >+</button>
          </div>
        )}
      </div>
    );
  }
);

function fmtTime(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}
