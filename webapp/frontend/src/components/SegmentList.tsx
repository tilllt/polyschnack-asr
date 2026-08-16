import { Fragment, useRef, useState, useEffect, useMemo } from "react";
import type { ReactNode } from "react";
import type { Segment } from "../api";
import { updateSegment, renameSpeaker } from "../api";
import { fmtTimecode } from "../format";
import { activeWordIndex, confidenceClass, hasConfidence, shouldScrollIntoView, nextWordTarget } from "../karaoke";
import { moveBoundary } from "../resegment";
import { useT } from "../useLocale";
import { useToast } from "./Toasts";

interface Props {
  segments: Segment[];
  onSeekTo?: (seconds: number) => void;
  /** Seek OHNE Autoplay (2026-08-16: Cursor-Wort-Navigation). */
  onSeekPaused?: (seconds: number) => void;
  activeIdx: number;
  onActiveChange: (idx: number) => void;
  recordingId?: string;
  onEdited?: (segments: Segment[], text: string) => void;
  currentTime?: number;
  /** Review-Fix 2026-08-15 (Such-UI): Query für grüne Treffer-Hervorhebung
   *  (bewusst ANDERS als der gelbe Karaoke-Marker) + Sprung-Ziel. */
  searchQuery?: string;
  searchJump?: { idx: number; nonce: number } | null;
  /** Feature 2026-08-15: draggable Timecode-Marker zwischen den Segmenten.
   *  Wird dieser Callback gesetzt, sind die Grenzen ziehbar: nach oben =
   *  Grenze in der Zeit zurück (Segment N verliert am Ende Wörter, N+1
   *  gewinnt vorne), nach unten = umgekehrt. Wort für Wort, nie geteilt.
   *  Erster (Start) und letzter (Ende) Marker sind bewusst NICHT ziehbar. */
  onBoundaryMoved?: (segments: Segment[]) => void;
  /** Feature 2026-08-15: Drag begonnen/beendet (für Speichern + UI-Feedback). */
  onBoundaryDragEnd?: (segments: Segment[]) => void;
  /** Feature 2026-08-16 (Mockup): "+" im Kreis zwischen den Segmenten —
   *  fügt nach Segment `afterIdx` ein neues Segment ein (gleicher Sprecher,
   *  letztes Wort wandert). Callback bekommt den neuen Segment-Index. */
  onSegmentInsert?: (afterIdx: number) => void;
  /** Feature 2026-08-16 (Mockup): "−" im Kreis vor dem Timecode — löscht
   *  Segment `idx` (Text wandert ans vorige Segment). */
  onSegmentDelete?: (idx: number) => void;
}

// Re-segmentierte Segmente (resegment.ts) sind strukturell identisch zu
// Segment[] — die Optionals sind nur für die Typ-Kompatibilität mit dem
// generischen Input nötig; zur Laufzeit sind start/end/text immer gesetzt.
export type DisplaySegment = Segment;

/** Wieviele Pixel Drag-Bewegung = 1 Wort (Grenz-Marker). */
const PX_PER_WORD = 16;

export function SegmentList({ segments, onSeekTo, onSeekPaused, activeIdx, onActiveChange, recordingId, onEdited, currentTime, searchQuery, searchJump, onBoundaryMoved, onBoundaryDragEnd, onSegmentInsert, onSegmentDelete }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rowRefs = useRef<(HTMLDivElement | null)[]>([]);
  const renameInputRef = useRef<HTMLInputElement>(null);
  const editAreaRef = useRef<HTMLTextAreaElement>(null);
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const [editText, setEditText] = useState("");
  const [saving, setSaving] = useState(false);
  const [renamingSpeakerIdx, setRenamingSpeakerIdx] = useState<number | null>(null);
  const [renameText, setRenameText] = useState("");
  const [renameSaving, setRenameSaving] = useState(false);
  // Feature 2026-08-16: Dropdown „Sprecher wählen" (Klick auf den Namen) —
  // offen für Segment-Index i; null = zu.
  const [openSpeakerMenu, setOpenSpeakerMenu] = useState<number | null>(null);
  // Feature 2026-08-15: aktive Drag-Grenze (für visuelles Feedback)
  const [dragIdx, setDragIdx] = useState<number | null>(null);
  const dragRef = useRef<{
    idx: number;
    startY: number;
    lastWords: number;
    baseSegments: Segment[]; // eingefrorene Liste beim Drag-Start (Duplikat-Fix 2026-08-16)
    currentList: Segment[]; // zuletzt an onBoundaryMoved gesendete Liste
  } | null>(null);
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
  // Fix 2026-08-16: renamingSpeakerIdx (SEGMENT-Index) statt Speaker-Name —
  // der String-Zustand zeigte das Rename-Input in JEDEM Segment mit demselben
  // Sprecher und fokussierte das LETZTE (Sprung ans Listenende).
  useEffect(() => {
    if (renamingSpeakerIdx !== null) renameInputRef.current?.focus({ preventScroll: true });
  }, [renamingSpeakerIdx]);
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

  // ── Feature 2026-08-15: draggable Grenz-Marker ─────────────────────
  // Ziehen nach OBEN (dy < 0) = Grenze in der Zeit zurück → Segment N
  // verliert am Ende Wörter, Segment N+1 gewinnt vorne (moveBoundary
  // mit delta < 0). Nach unten = umgekehrt. Alle 16 px = 1 Wort.
  // Der Grenz-Streifen liegt ZWISCHEN den Segment-Zeilen — der Klick
  // auf die Zeile selbst (Seek) bleibt unberührt (stopPropagation).
  function onBoundaryPointerDown(e: React.PointerEvent, idx: number) {
    if (!onBoundaryMoved) return;
    if (e.button !== 0 && e.pointerType === "mouse") return;
    e.preventDefault();
    e.stopPropagation();
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    // Basis-Liste einfrieren + kumulativen Wort-Offset speichern. moveBoundary
    // wird bei JEDEM Pointer-Move mit dem kumulativen words-Wert auf DIESER
    // Basis-Liste aufgerufen (nicht Schritt-für-Schritt auf dem Prop): die
    // Prop-Liste kann zwischen zwei Pointer-Moves noch die alte sein (React
    // rendert asynchron) — Schritt-Deltas auf der alten Liste duplizieren
    // Wörter (Bug 2026-08-16: "Anton? Anton?", "Montag. Montag.").
    dragRef.current = { idx, startY: e.clientY, lastWords: 0, baseSegments: segments, currentList: segments };
    setDragIdx(idx);
  }

  function onBoundaryPointerMove(e: React.PointerEvent) {
    const d = dragRef.current;
    if (!d) return;
    const dy = e.clientY - d.startY;
    const words = Math.round(dy / PX_PER_WORD);
    if (words !== d.lastWords) {
      d.lastWords = words;
      const next = moveBoundary(d.baseSegments, d.idx, words) as Segment[];
      d.currentList = next; // für onBoundaryDragEnd: explizit die AKTUELLE
      // Liste übergeben (kein Closure-State — der kann beim Loslassen noch
      // den vorletzten Render-Stand enthalten, Bug 2026-08-16: „nicht
      // gespeichert / springt zurück").
      onBoundaryMoved?.(next);
    }
  }

  function onBoundaryPointerUp() {
    const d = dragRef.current;
    if (!d) return;
    dragRef.current = null;
    setDragIdx(null);
    onBoundaryDragEnd?.(d.currentList);
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

  // Erkannte Sprecher dieser Aufnahme = unique speaker-Werte aller Segmente.
  const speakerOptions = useMemo(() => {
    const set = new Set<string>();
    for (const s of segments) if (s.speaker) set.add(s.speaker);
    return [...set];
  }, [segments]);

  // Feature 2026-08-16: Sprecher per Dropdown auf DIESES Segment setzen
  // (PATCH /segments/{idx} mit speaker — Wörter/Timestamps bleiben).
  async function handleSetSpeaker(idx: number, speaker: string) {
    setOpenSpeakerMenu(null);
    if (!recordingId || !onEdited) return;
    try {
      const result = await updateSegment(recordingId, idx, undefined, speaker);
      onEdited(result.segments, result.text);
      toast(t("speaker_set_saved"), "ok");
    } catch (err) {
      toast(
        err instanceof Error ? err.message : t("speaker_set_error"),
        "err",
      );
    }
  }

  async function handleRenameSpeaker(speaker: string) {
    if (renameSaving || !recordingId || !onEdited) return;
    const newName = renameText.trim();
    if (!newName || newName === speaker) {
      setRenamingSpeakerIdx(null);
      return;
    }
    setRenameSaving(true);
    try {
      const result = await renameSpeaker(recordingId, speaker, newName);
      onEdited(result.segments, result.text);
      setRenamingSpeakerIdx(null);
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
        const prevHasWords = i > 0 && (segments[i - 1].words?.length ?? 0) > 0;
        return (
        <Fragment key={i}>
        {i > 0 && onSegmentInsert && (
          /* ── Grenz-Leiste (Feature 2026-08-16, Mockup): "+" im Kreis,
             40 % Transparenz, daneben die Hairline als Segment-Trennung ── */
          <div
            className="flex items-center gap-1.5 px-3 py-[1px]"
            onClick={(e) => e.stopPropagation()}
            onDoubleClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={(e) => {
                e.stopPropagation();
                onSegmentInsert(i - 1);
              }}
              disabled={!prevHasWords}
              className="w-[18px] h-[18px] rounded-full flex items-center justify-center flex-shrink-0
                text-[12px] leading-none text-accent/60 bg-accent/10 border border-accent/25
                opacity-40 hover:opacity-100 hover:bg-accent/25 hover:text-accent
                transition-opacity disabled:opacity-15 disabled:hover:opacity-15 disabled:cursor-not-allowed"
              title={t("segment_insert_hint")}
              aria-label={t("segment_insert_hint")}
            >
              +
            </button>
            <div className="h-px flex-1 bg-border/60" aria-hidden />
          </div>
        )}
        <div
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
            // Guard: Tasten in Edit-Feldern (Text-Edit, Sprecher-Rename)
            // dürfen die Zeilen-Navigation NICHT auslösen (bubbeln sonst
            // hierher: Enter im Textarea = Zeilen-Seek!).
            const t = e.target as HTMLElement;
            if (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable) return;
            if (e.key === "Enter") { handleClick(i); return; }
            // Cursor ←/→: Wort-für-Wort-Navigation (Feature 2026-08-16).
            // Space übernimmt der globale Play/Stop-Handler (capture).
            if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
              e.preventDefault();
              e.stopPropagation();
              const target = nextWordTarget(segments, activeIdx, currentTime ?? 0, e.key === "ArrowRight" ? 1 : -1);
              if (!target) return;
              const w = segments[target.segIdx]?.words?.[target.wIdx];
              if (!w) return;
              onActiveChange?.(target.segIdx);
              // Cursor-Navigation: nur springen, NICHT abspielen
              (onSeekPaused ?? onSeekTo)?.(typeof w.start === "number" ? w.start : 0);
            }
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
          {onSegmentDelete && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onSegmentDelete(i);
              }}
              disabled={segments.length <= 1}
              className="w-[18px] h-[18px] rounded-full flex items-center justify-center flex-shrink-0
                text-[12px] leading-none text-muted2 border border-border/70
                opacity-40 hover:opacity-100 hover:text-err hover:bg-err/10 hover:border-err/40
                transition-opacity disabled:opacity-15 disabled:hover:opacity-15 disabled:cursor-not-allowed"
              title={t("segment_delete_hint")}
              aria-label={t("segment_delete_hint")}
            >
              −
            </button>
          )}
          <span
            className={`
              text-[11px] font-semibold text-accent min-w-[38px] flex-shrink-0
              opacity-85 tabular-nums
              ${i > 0 && onBoundaryMoved
                ? `cursor-ns-resize touch-none select-none rounded-sm px-0.5 -mx-0.5 ${dragIdx === i - 1 ? "bg-[rgba(91,140,255,0.16)] text-accent" : "hover:bg-[rgba(91,140,255,0.08)]"}`
                : ""}
            `}
            onClick={(e) => {
              // Timecode = Drag-Handle der Grenze davor — kein Seek/Edit
              if (i > 0 && onBoundaryMoved) e.stopPropagation();
            }}
            onDoubleClick={(e) => {
              if (i > 0 && onBoundaryMoved) e.stopPropagation();
            }}
            onPointerDown={i > 0 && onBoundaryMoved ? (e) => onBoundaryPointerDown(e, i - 1) : undefined}
            onPointerMove={i > 0 && onBoundaryMoved ? onBoundaryPointerMove : undefined}
            onPointerUp={i > 0 && onBoundaryMoved ? onBoundaryPointerUp : undefined}
            onPointerCancel={i > 0 && onBoundaryMoved ? onBoundaryPointerUp : undefined}
            title={i > 0 && onBoundaryMoved ? t("boundary_drag_hint") : undefined}
          >
            {fmtTimecode(seg.start)}
          </span>
          {speaker && (
            renamingSpeakerIdx === i ? (
              <input
                className="text-[11px] font-bold text-[#25d366] min-w-[80px] max-w-[140px] flex-shrink-0 bg-panel2 border border-border rounded-sm px-1 py-0.5 uppercase tracking-[.04em]"
                value={renameText}
                placeholder={t("rename_speaker_placeholder")}
                onChange={(e) => setRenameText(e.target.value)}
                onClick={(e) => e.stopPropagation()}
                onDoubleClick={(e) => e.stopPropagation()}
                onKeyDown={async (e) => {
                  if (e.key === "Escape") { setRenamingSpeakerIdx(null); return; }
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
              <span className="relative flex items-center gap-0.5 flex-shrink-0">
                <span
                  className="text-[11px] font-bold text-[#25d366] w-max uppercase tracking-[.04em] cursor-pointer hover:underline decoration-dotted underline-offset-2"
                  title={t("speaker_dropdown_hint")}
                  onClick={(e) => {
                    // Feature 2026-08-16: Klick auf den Namen öffnet das
                    // Dropdown mit den erkannten Sprechern (Segment-weises
                    // Setzen). Rename nur übers Stift-Icon daneben.
                    e.stopPropagation();
                    setOpenSpeakerMenu(openSpeakerMenu === i ? null : i);
                  }}
                  onDoubleClick={(e) => e.stopPropagation()}
                >
                  {speaker.replace("SPEAKER_", "")}
                </span>
                <button
                  onClick={(e) => {
                    // Fix 2026-08-16: Stift bearbeitet DIESES Segment (Index
                    // i) — vorher zeigte der String-Zustand das Input in allen
                    // Segmenten mit demselben Sprecher und der Fokus sprang ans
                    // Ende der Liste.
                    e.stopPropagation();
                    setRenamingSpeakerIdx(i);
                    setRenameText(speaker.replace("SPEAKER_", ""));
                  }}
                  className="text-[11px] leading-none text-muted2 hover:text-accent px-0.5 cursor-pointer"
                  title={t("rename_speaker_placeholder")}
                  aria-label={t("rename_speaker_placeholder")}
                >
                  ✎
                </button>
                {openSpeakerMenu === i && (
                  <>
                    {/* Klick-Catcher: schließt das Menü bei Klick außerhalb */}
                    <div
                      className="fixed inset-0 z-10"
                      onClick={(e) => {
                        e.stopPropagation();
                        setOpenSpeakerMenu(null);
                      }}
                    />
                    <div
                      className="absolute top-full left-0 z-20 mt-0.5 min-w-[110px] max-h-[160px] overflow-y-auto bg-panel2 border border-border rounded-md shadow-xl py-0.5"
                      onDoubleClick={(e) => e.stopPropagation()}
                    >
                      {speakerOptions.map((opt) => (
                        <button
                          key={opt}
                          onClick={(e) => {
                            e.stopPropagation();
                            if (opt === speaker) {
                              setOpenSpeakerMenu(null);
                              return;
                            }
                            void handleSetSpeaker(i, opt);
                          }}
                          className={`block w-full text-left px-2 py-1 text-[11px] uppercase tracking-[.04em] cursor-pointer hover:bg-accent/10 ${
                            opt === speaker
                              ? "text-[#25d366] font-bold"
                              : "text-muted1"
                          }`}
                        >
                          {opt.replace("SPEAKER_", "")}
                        </button>
                      ))}
                    </div>
                  </>
                )}
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
        {/* Feature 2026-08-15/16: draggable Grenze. Seit 2026-08-16 sind die
            Start-Timecodes der Zeilen selbst die Drag-Handles (Grenze VOR
            Segment i = Timecode von Segment i, i > 0) — die separaten
            22-px-Streifen entfallen (User: „extra handles nerven"). Erste
            Grenze (vor Segment 0) und letzte (nach dem letzten) existieren
            nicht — die äußeren Marker sind fix. */}
        </Fragment>
        );
      })}
    </div>
  );
}
