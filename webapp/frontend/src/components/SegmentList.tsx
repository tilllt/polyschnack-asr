import { useEffect, useRef, type RefObject } from "react";
import type { Segment } from "../api";
import { fmtTimecode } from "../format";

interface Props {
  segments: Segment[];
  audioRef: RefObject<HTMLAudioElement>;
  activeIdx: number;
  onActiveChange: (idx: number) => void;
}

export function SegmentList({ segments, audioRef, activeIdx, onActiveChange }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rowRefs = useRef<(HTMLDivElement | null)[]>([]);

  // Auto-scroll the active segment into view
  useEffect(() => {
    const container = containerRef.current;
    const activeEl = rowRefs.current[activeIdx];
    if (!container || !activeEl || activeIdx < 0) return;

    const top = activeEl.offsetTop - container.offsetTop;
    const visible =
      container.scrollTop <= top &&
      top < container.scrollTop + container.clientHeight;

    if (!visible) {
      container.scrollTop =
        top - container.clientHeight / 2 + activeEl.offsetHeight / 2;
    }
  }, [activeIdx]);

  function seekTo(idx: number) {
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = segments[idx].start;
    void audio.play().catch(() => undefined);
    onActiveChange(idx);
  }

  return (
    <div
      ref={containerRef}
      className="
        bg-seg-bg border border-border rounded-sm
        max-h-[260px] overflow-y-auto scroll-smooth
        scrollbar-thin py-1
      "
    >
      {segments.map((seg, i) => (
        <div
          key={i}
          ref={(el) => { rowRefs.current[i] = el; }}
          role="button"
          tabIndex={0}
          onClick={() => seekTo(i)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") seekTo(i);
          }}
          className={`
            flex items-baseline gap-[10px] px-3 py-[6px]
            cursor-pointer transition-colors duration-[120ms]
            border-l-2 border-transparent
            text-[13.5px] leading-[1.5]
            hover:bg-[rgba(91,140,255,0.07)]
            ${i === activeIdx ? "seg-active" : ""}
          `}
        >
          <span className="text-[11px] font-semibold text-accent min-w-[42px] flex-shrink-0 opacity-85 tabular-nums">
            {fmtTimecode(seg.start)}
          </span>
          <span className="text-txt flex-1 min-w-0">{seg.text}</span>
        </div>
      ))}
    </div>
  );
}
