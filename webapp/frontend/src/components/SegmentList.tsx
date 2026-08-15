import { useRef, useState, useEffect } from "react";
import type { ReactNode } from "react";
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
  /** Review-Fix 2026-08-15 (Such-UI): Query für grüne Treffer-Hervorhebung
   *  (bewusst ANDERS als der gelbe Karaoke-Marker) + Sprung-Ziel. */
  searchQuery?: string;
  searchJump?: { idx: number; nonce: number } | null;
}

export function SegmentList({ segments, onSeekTo, activeIdx, onActiveChange, recordingId, onEdited, currentTime, searchQuery, searchJump }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rowRefs = useRef<(HTMLDivElement | null)[]>([]);
  const renameInputRef = useRef<HTMLInputElement>(null);
  const editAreaRef = useRef<HTMLTextAreaElement>(null);
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const [editText, setEditText] = useState("");
  const [saving, setSaving] = useState(false);
  const [renamingSpeaker, setRenamingSpeaker] = useState<string | null>(null);
  const [renameText, setRenameText] = useState("");
  const [renameSaving, setRenameSaving] = useState(false);
  const { t } = useT();
  const { toast } = useToast();

  // ── Such-Treffer (case-insensitive) ───────────────────────────────
  // Nur Plain-Text-Seiten: Wörter-Karaoke wird wortweise unten geprüft.
  const hasSearch = !!searchQuery && searchQuery.trim().length > 0;

  function highlightText(text: string, q: string): ReactNode {
    if (!q) return text;
    const parts: React.ReactNode[] = [];
    const re = new RegExp(`(${q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi");
    // split mit Capture-Gruppe: Treffer stehen auf ungeraden Indizes.
    // KEIN re.test im Loop (global flag → lastIndex-Mutation!).
    const spl = text.split(re);
    for (let i = 0; i < spl.length; i++) {
      const p = spl[i];
      if (!p) continue;
      if (i % 2 === 1) {
        parts.push(<mark key={i} className="search-hit">{p}</mark>);
      } else {
        parts.push(<span key={i}>{p}</span>);
      }
    }
    return parts;
  }

  // Wort-Trefferprüfung für die Karaoke-Wortspans.
  function wordIsHit(w: string): boolean {
    if (!hasSearch) return false;
    return w.toLowerCase().includes(searchQuery!.trim().toLowerCase());
  }

  // Auto-scroll zum Such-Treffer (Review-Fix): der Klick auf ein
  // Treffer-Segment in der Suchleiste springt hierher.
  useEffect(() => {
    if (!searchJump) return;
    const el = rowRefs.current[searchJump.idx];
    if (el) el.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [searchJump]);

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

  // Auto-focus ohne Anker-Scroll: Das native focus()-Scrollen des Browsers
  // springt in der Segmentliste (Container max-h + overflow) wie zu einem
  // Anchor zur Zeile — auch wenn der Klick die Zeile schon sichtbar gemacht
  // hat. focus({preventScroll:true}) verhindert den Sprung. (2026-08-14)
  useEffect(() => {
    if (renamingSpeaker) renameInputRef.current?.focus({ preventScroll: true });
  }, [renamingSpeaker]);
  useEffect(() => {
    if (editingIdx !== null) editAreaRef.current?.focus({ preventScroll: true });
  }, [editingIdx]);

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
            flex items-baseline gap-x-2 px-3 py-[6px]
            cursor-pointer transition-colors duration-[120ms]
            border-l-2 border-transparent
            text-[13.5px] leading-[1.5]
            hover:bg-[rgba(91,140,255,0.07)]
            ${i === activeIdx ? "seg-active" : ""}
            ${editingIdx === i ? "cursor-default" : ""}
          `}
        >
          <span className="text-[11px] font-semibold text-accent min-w-[38px] flex-shrink-0 opacity-85 tabular-nums">
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
                ref={renameInputRef}
              />
            ) : (
              <span className="flex items-center gap-0.5 flex-shrink-0">
                <span
                  className="text-[11px] font-bold text-[#25d366] w-max uppercase tracking-[.04em] cursor-pointer hover:underline decoration-dotted underline-offset-2"
                  title={t("rename_speaker_placeholder")}
                  onClick={(e) => {
                    // Ein-Klick auf den Speaker = Umbenennen-Modus (NICHT
                    // Zeilen-Seek). Der Zeilen-Klick (Audio abspielen) gehört
                    // zum Timecode/Text — der Speaker-Klick ist editierend.
                    e.stopPropagation();
                    setRenamingSpeaker(speaker);
                    setRenameText(speaker.replace("SPEAKER_", ""));
                  }}
                  onDoubleClick={(e) => e.stopPropagation()}
                >
                  {speaker.replace("SPEAKER_", "")}
                </span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setRenamingSpeaker(speaker);
                    setRenameText(speaker.replace("SPEAKER_", ""));
                  }}
                  className="text-[11px] leading-none text-muted2 hover:text-accent px-0.5 cursor-pointer"
                  title={t("rename_speaker_placeholder")}
                  aria-label={t("rename_speaker_placeholder")}
                >
                  ✎
                </button>
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
                // Review-Fix 2026-08-15: Klick nach außen beendet den
                // Edit-Mode IMMER. VORHER: nur bei Textänderung wurde
                // handleSave gerufen — bei unverändertem Text blieb
                // editingIdx gesetzt und der Mode war nicht mehr
                // beendbar (handleClick blockiert während des Editierens).
                if (editText !== segments[i].text) {
                  handleSave(i);
                } else {
                  setEditingIdx(null);
                }
              }}
              ref={editAreaRef}
            />
          ) : (
            <span className="text-txt flex-1 min-w-0">
              {seg.words && seg.words.length > 0 && (hasConfidence(seg.words) || (currentTime != null && i === activeIdx))
                ? (() => {
                    const activeW = currentTime != null ? activeWordIndex(seg.words, currentTime) : -1;
                    return seg.words!.map((w, wi) => {
                      const isActive = wi === activeW;
                      // Such-Treffer: grüner Marker (.search-hit) — bewusst
                      // getrennt vom gelben Karaoke-Marker (Abspielposition).
                      const isHit = wordIsHit(w.word);
                      const cls = isHit
                        ? "search-hit"
                        : isActive
                          ? "karaoke-active"
                          : `${confidenceClass(w.confidence)} hover:text-accent/70`;
                      return (
                        <>
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
                          className={`cursor-pointer transition-colors duration-[100ms] ${cls}`}
                        >
                          {/* Review-Fix 2026-08-15: Space GEHÖRT KEINEM
                              Wort-Span. Der Trenn-Space steht als separates
                              Text-Node zwischen den Wort-Spans → die Markierung
                              ist auf BEIDEN Seiten symmetrisch OHNE Space
                              (User-Vorgabe: konsistent beide Seiten, nicht
                              einseitig). Ein trailing space im Span würde am
                              Zeilenumbruch kollabieren (Markierung abgeschnitten),
                              ein leading space markierte einseitig mit. */}
                          {w.word}
                        </span>
                        {wi < seg.words!.length - 1 ? " " : ""}
                        </>
                      );
                    });
                  })()
                : hasSearch
                  ? highlightText(seg.text, searchQuery!.trim())
                  : seg.text}
            </span>
          )}
        </div>
        );
      })}
    </div>
  );
}
