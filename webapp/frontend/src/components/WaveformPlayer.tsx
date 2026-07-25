import { useEffect, useRef, useState, useCallback } from "react";
import WaveSurfer from "wavesurfer.js";
import RegionsPlugin from "wavesurfer.js/dist/plugins/regions.js";

interface Props {
  audioUrl: string;
  onRegionChange?: (start: number, end: number) => void;
  height?: number;
}

export function WaveformPlayer({ audioUrl, onRegionChange, height = 80 }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WaveSurfer | null>(null);
  const regionsRef = useRef<RegionsPlugin | null>(null);
  const [playing, setPlaying] = useState(false);
  const [ready, setReady] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);

  useEffect(() => {
    if (!containerRef.current) return;

    const regions = RegionsPlugin.create();
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
      minPxPerSec: 10,
      normalize: true,
      plugins: [regions],
    });

    ws.load(audioUrl);

    ws.on("ready", () => {
      setReady(true);
      setDuration(ws.getDuration());
      const dur = ws.getDuration();
      regions.addRegion({
        start: 0,
        end: dur,
        color: "rgba(91,140,255,0.08)",
        drag: true,
        resize: true,
      });
    });

    ws.on("timeupdate", (t) => setCurrentTime(t));
    ws.on("play", () => setPlaying(true));
    ws.on("pause", () => setPlaying(false));
    ws.on("finish", () => setPlaying(false));

    regions.on("region-updated", (r) => {
      onRegionChange?.(r.start, r.end);
    });

    wsRef.current = ws;
    regionsRef.current = regions;

    return () => { ws.destroy(); };
  }, [audioUrl]);

  const togglePlay = useCallback(() => wsRef.current?.playPause(), []);

  return (
    <div className="w-full">
      <div ref={containerRef} className="w-full" />
      {ready && (
        <div className="flex items-center gap-3 mt-2">
          <button
            onClick={togglePlay}
            className="btn-ghost-sm text-[13px] flex items-center gap-1"
            title={playing ? "Pause" : "Play"}
          >
            {playing ? "⏸" : "▶"}
          </button>
          <span className="text-[12px] text-muted2 tabular-nums">
            {fmtTime(currentTime)} / {fmtTime(duration)}
          </span>
        </div>
      )}
    </div>
  );
}

function fmtTime(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}
