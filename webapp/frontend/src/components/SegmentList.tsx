import { useRef, useState, useEffect } from "react";
import type { Segment } from "../api";
import { updateSegment } from "../api";
import { fmtTimecode } from "../format";

interface Props {
  segments: Segment[];
  onSeekTo?: (seconds: number) => void;
  activeIdx: number;
  onActiveChange: (idx: number) => void;
  recordingId?: string;
  onEdited?: (segments: Segment[], text: string) => void;
  currentTime?: number;
}

export function SegmentList({ segments, onSeekTo, activeIdx, onActiveChange, recordingId, onEdited, currentTime }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rowRefs = useRef<(HTMLDivElement | null)[]>([]);
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const [editText, setEditText] = useState("");
  const [saving, setSaving] = useState(false);

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

  function handleClick(idx: number) {
    if (editingIdx !== null) return;  // don't seek while editing
    onActiveChange(idx);
    onSeekTo?.(segments[idx].start);
  }

  async function handleSave(idx: number) {
    if (saving || !recordingId || !onEdited) return;
    setSaving(true);
    try {
      const result = await updateSegment(recordingId, idx, editText);
      onEdited(result.segments, result.text);
      setEditingIdx(null);
    } catch {
      // keep edit open on error, user can retry
    } finally {
      setSaving(false);
    }
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
          onClick={() => handleClick(i)}
          onDoubleClick={() => {
            if (!recordingId) return;
            setEditingIdx(i);
            setEditText(seg.text);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") { handleClick(i); }
          }}
          className={`
            flex items-baseline gap-[10px] px-3 py-[6px]
            cursor-pointer transition-colors duration-[120ms]
            border-l-2 border-transparent
            text-[13.5px] leading-[1.5]
            hover:bg-[rgba(91,140,255,0.07)]
            ${i === activeIdx ? "seg-active" : ""}
            ${editingIdx === i ? "cursor-default" : ""}
          `}
        >
          <span className="text-[11px] font-semibold text-accent min-w-[42px] flex-shrink-0 opacity-85 tabular-nums">
            {fmtTimecode(seg.start)}
          </span>
          {seg.speaker && (
            <span className="text-[11px] font-bold text-[#25d366] min-w-[48px] flex-shrink-0 uppercase tracking-[.04em]">
              {seg.speaker.replace("SPEAKER_", "")}
            </span>
          )}
          {editingIdx === i ? (
            <textarea
              className="flex-1 min-w-0 bg-panel2 border border-border rounded-sm px-2 py-1 text-[13px] resize-y leading-[1.4]"
              value={editText}
              onChange={(e) => setEditText(e.target.value)}
              onKeyDown={async (e) => {
                if (e.key === "Escape") { setEditingIdx(null); return; }
                if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                  e.preventDefault();
                  await handleSave(i);
                }
              }}
              onBlur={() => handleSave(i)}
              autoFocus
            />
          ) : (
            <span className="text-txt flex-1 min-w-0">
              {seg.words && seg.words.length > 0 && currentTime != null && i === activeIdx
                ? (console.log("KARAOKE_WORDS", seg.words),
                  seg.words.map((w, wi) => {
                    const isActive = currentTime >= w.start && currentTime < w.end;
                    return (
                      <span
                        key={wi}
                        className={
                          isActive
                            ? "text-accent font-semibold underline decoration-accent/40 underline-offset-2"
                            : ""
                        }
                      >
                        {w.word}{wi < seg.words!.length - 1 ? " " : ""}
                      </span>
                    );
                  }))
                : console.log("KARAOKE_SKIP", {hasWords: !!seg.words, len: seg.words?.length, ct: currentTime, active: i === activeIdx, idx: i}),
                  seg.text}
            </span>
          )}
        </div>
      ))}
    </div>
  );
}
