import { useEffect, useRef, useState, useCallback, useImperativeHandle, forwardRef } from "react";
import WaveSurfer from "wavesurfer.js";
import RegionsPlugin from "wavesurfer.js/dist/plugins/regions.js";
import TimelinePlugin from "wavesurfer.js/dist/plugins/timeline.js";
import MinimapPlugin from "wavesurfer.js/dist/plugins/minimap.js";
import HoverPlugin from "wavesurfer.js/dist/plugins/hover.js";

export interface WaveSurferHandle {
  seekTo: (seconds: number) => void;
  playPause: () => void;
  getCurrentTime: () => number;
  isPlaying: () => boolean;
}

interface Props {
  audioUrl: string;
  audioPreviewUrl?: string | null;
  peaks?: number[] | null;
  duration?: number | null;
  onRegionChange?: (start: number, end: number) => void;
  onTimeUpdate?: (time: number) => void;
  onPlayStateChange?: (playing: boolean) => void;
  height?: number;
}

const ZOOM_STEPS = [1, 2, 4, 6, 10, 20, 50];

export const WaveformPlayer = forwardRef<WaveSurferHandle, Props>(
  function WaveformPlayer({ audioUrl, audioPreviewUrl, peaks, duration: propDuration, onRegionChange, onTimeUpdate, onPlayStateChange, height = 80 }, ref) {
    const containerRef = useRef<HTMLDivElement>(null);
    const timelineRef = useRef<HTMLDivElement>(null);
    const minimapRef = useRef<HTMLDivElement>(null);
    const wsRef = useRef<WaveSurfer | null>(null);
    const regionsRef = useRef<RegionsPlugin | null>(null);
    const onTimeUpdateRef = useRef(onTimeUpdate);
    const onPlayStateRef = useRef(onPlayStateChange);
    const onRegionRef = useRef(onRegionChange);
    // Keep refs in sync with latest props
    onTimeUpdateRef.current = onTimeUpdate;
    onPlayStateRef.current = onPlayStateChange;
    onRegionRef.current = onRegionChange;
    const [ready, setReady] = useState(false);
    const [audioReady, setAudioReady] = useState(false);
    const [error, setError] = useState<string | null>(null);
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

      const regions = RegionsPlugin.create();
      const timeline = TimelinePlugin.create({ container: timelineRef.current! });
      const minimap = MinimapPlugin.create({
        container: minimapRef.current!,
        height: 30,
        waveColor: "rgba(91,140,255,0.15)",
        progressColor: "rgba(91,140,255,0.3)",
      });
      const hover = HoverPlugin.create();
      const hasPeaks = peaks && peaks.length > 0;
      const ws = WaveSurfer.create({
        container: containerRef.current,
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
        peaks: hasPeaks ? [peaks as number[]] : undefined,
        duration: hasPeaks && propDuration ? propDuration : undefined,
        plugins: [regions, timeline, minimap, hover],
      });

      ws.load(audioPreviewUrl || audioUrl);

      // Track when actual audio is decoded (separate from peak-based "ready")
      let audioDecoded = false;
      ws.on("decode", () => {
        audioDecoded = true;
        setAudioReady(true);
        setError(null);
      });

      // Timeout: if audio doesn't become playable within 30s, fall back to original WAV
      const audioTimeout = setTimeout(() => {
        if (!audioDecoded) {
          console.warn("WaveformPlayer: audio decode timeout, falling back to original WAV");
          // Re-load with original URL
          const url = audioPreviewUrl ? audioUrl : null; // only retry if we were using preview
          if (url) {
            ws.load(url);
          } else {
            setError("Audio konnte nicht geladen werden");
            setAudioReady(true); // unblock interaction anyway
          }
        }
      }, 30000);

      ws.on("loading", (pct: number) => {
        if (pct >= 100 && !audioDecoded) {
          // Fetch completed but decode still pending – WS7 handles this internally
        }
      });

      ws.on("ready", () => {
        setReady(true);
        setError(null);
        const dur = ws.getDuration();

        // If we can already get currentTime > 0, audio is decoded
        try { ws.getCurrentTime(); setAudioReady(true); } catch (_) {}

        // Initial zoom = fit container width
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
      ws.on("play", () => { setPlaying(true); onPlayStateRef.current?.(true); });
      ws.on("pause", () => { setPlaying(false); onPlayStateRef.current?.(false); });
      ws.on("finish", () => { setPlaying(false); onPlayStateRef.current?.(false); });

      regions.on("region-updated", (r) => onRegionRef.current?.(r.start, r.end));

      // Error handling: retry with original URL if preview fails
      ws.on("error", (err: string) => {
        console.warn("WaveformPlayer error:", err);
        if (audioPreviewUrl && audioUrl) {
          setError("Preview fehlgeschlagen, lade Original…");
          setTimeout(() => ws.load(audioUrl), 500);
        } else {
          setError(`Fehler: ${err}`);
          setAudioReady(true);
        }
      });

      wsRef.current = ws;
      regionsRef.current = regions;
      return () => { clearTimeout(audioTimeout); ws.destroy(); };
    }, [audioUrl, audioPreviewUrl, peaks, propDuration]);

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
        {error && ready && (
          <div className="flex items-center justify-center h-[40px] text-[13px] text-amber-400 gap-2">
            <span>⚠️</span> {error}
          </div>
        )}
        {ready && !audioReady && !error && (
          <div className="flex items-center justify-center h-[30px] text-muted2 text-[12px] gap-2">
            <span className="animate-spin inline-block w-3 h-3 border-2 border-current border-t-transparent rounded-full" />
            Loading audio…
          </div>
        )}
        <div ref={containerRef} className={`w-full ${ready ? "" : "hidden"}`} />
        {/* Timeline ruler */}
        <div ref={timelineRef} className={`w-full ${ready ? "mt-0" : "hidden"}`} />
        {/* Minimap overview */}
        <div ref={minimapRef} className={`w-full mt-2 ${ready ? "" : "hidden"}`} />
        {ready && (
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
