import { useRef, useState, useEffect } from "react";
import type { Segment } from "../api";
import { updateSegment, renameSpeaker } from "../api";
import { fmtTimecode } from "../format";
import { activeWordIndex, confidenceClass, hasConfidence, shouldScrollIntoView } from "../karaoke";
import { useT } from "../useLocale";
import { useToast } from "./Toasts";

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
  const [renamingSpeaker, setRenamingSpeaker] = useState<string | null>(null);
  const [renameText, setRenameText] = useState("");
  const [renameSaving, setRenameSaving] = useState(false);
  const { t } = useT();
  const { toast } = useToast();

  // Auto-scroll the active segment into view — nur wenn es NICHT vollständig
  // sichtbar ist (top UND bottom im Container). scrollIntoView mit
  // block:"nearest" scrollt minimal und verträgt sich mit scroll-smooth;
  // die alte direkte scrollTop-Zuweisung scrollte unten abgeschnittene
  // Segmente nie nach (nur top wurde geprüft).
  useEffect(() => {
    const container = containerRef.current;
    const activeEl = rowRefs.current[activeIdx];
    if (!container || !activeEl || activeIdx < 0) return;

    const top = activeEl.offsetTop - container.offsetTop;
    const bottom = top + activeEl.offsetHeight;
    if (
      shouldScrollIntoView(container.scrollTop, container.clientHeight, top, bottom)
    ) {
      activeEl.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [activeIdx]);

  function handleClick(idx: number) {
    if (editingIdx !== null) return;  // don't seek while editing
    onActiveChange(idx);
    onSeekTo?.(segments[idx].start);
  }

  function handleWordClick(idx: number, seconds: number) {
    if (editingIdx !== null) return;
    onActiveChange(idx);
    onSeekTo?.(seconds);
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

  async function handleRenameSpeaker(speaker: string) {
    if (renameSaving || !recordingId || !onEdited) return;
    const newName = renameText.trim();
    if (!newName || newName === speaker) {
      setRenamingSpeaker(null);
      return;
    }
    setRenameSaving(true);
    try {
      const result = await renameSpeaker(recordingId, speaker, newName);
      onEdited(result.segments, result.text);
      setRenamingSpeaker(null);
      toast(t("rename_speaker_saved"), "ok");
    } catch (err) {
      // Input offen lassen, User kann es erneut versuchen; Fehler sichtbar
      toast(
        err instanceof Error ? err.message : t("rename_speaker_error"),
        "err",
      );
    } finally {
      setRenameSaving(false);
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
      {segments.map((seg, i) => {
        const speaker = seg.speaker;
        return (
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
          {speaker && (
            renamingSpeaker === speaker ? (
              <input
                className="text-[11px] font-bold text-[#25d366] min-w-[80px] max-w-[140px] flex-shrink-0 bg-panel2 border border-border rounded-sm px-1 py-0.5 uppercase tracking-[.04em]"
                value={renameText}
                placeholder={t("rename_speaker_placeholder")}
                onChange={(e) => setRenameText(e.target.value)}
                onClick={(e) => e.stopPropagation()}
                onDoubleClick={(e) => e.stopPropagation()}
                onKeyDown={async (e) => {
                  if (e.key === "Escape") { setRenamingSpeaker(null); return; }
                  if (e.key === "Enter") {
                    e.preventDefault();
                    e.stopPropagation();
                    await handleRenameSpeaker(speaker);
                  }
                }}
                onBlur={() => handleRenameSpeaker(speaker)}
                autoFocus
              />
            ) : (
              <span
                className="text-[11px] font-bold text-[#25d366] min-w-[48px] flex-shrink-0 uppercase tracking-[.04em] cursor-pointer hover:underline decoration-dotted underline-offset-2"
                title={t("rename_speaker_placeholder")}
                onDoubleClick={(e) => {
                  e.stopPropagation();  // nicht den Text-Edit der Zeile triggern
                  setRenamingSpeaker(speaker);
                  setRenameText(speaker.replace("SPEAKER_", ""));
                }}
              >
                {speaker.replace("SPEAKER_", "")}
              </span>
            )
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
              onBlur={() => {
                if (editText !== segments[i].text) handleSave(i);
              }}
              autoFocus
            />
          ) : (
            <span className="text-txt flex-1 min-w-0">
              {seg.words && seg.words.length > 0 && (hasConfidence(seg.words) || (currentTime != null && i === activeIdx))
                ? (() => {
                    const activeW = currentTime != null ? activeWordIndex(seg.words, currentTime) : -1;
                    return seg.words!.map((w, wi) => {
                      const isActive = wi === activeW;
                      return (
                        <span
                          key={wi}
                          role="button"
                          tabIndex={0}
                          onClick={(e) => {
                            e.stopPropagation();
                            handleWordClick(i, w.start);
                          }}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              handleWordClick(i, w.start);
                            }
                          }}
                          className={`cursor-pointer transition-colors duration-[100ms] ${
                            isActive
                              ? "text-accent font-semibold underline decoration-accent/40 underline-offset-2"
                              : `${confidenceClass(w.confidence)} hover:text-accent/70`
                          }`}
                        >
                          {w.word}{wi < seg.words!.length - 1 ? " " : ""}
                        </span>
                      );
                    });
                  })()
                : seg.text}
            </span>
          )}
        </div>
        );
      })}
    </div>
  );
}
