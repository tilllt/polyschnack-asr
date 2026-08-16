import { Fragment, useRef, useState, useEffect, useMemo } from "react";
import type { ReactNode } from "react";
import type { Segment } from "../api";
import { updateSegment, renameSpeaker } from "../api";
import { fmtTimecode } from "../format";
import { activeWordIndex, confidenceClass, hasConfidence, nextWordTarget } from "../karaoke";
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
  /** Feature 2026-08-16 (Edit-Vollbild): true = Liste füllt die verfügbare
   *  Höhe des Parents statt der kompakten 260px-Begrenzung. */
  fillHeight?: boolean;
  /** Feature 2026-08-16 (Edit): Text-Markierung in einem Segment →
   *  eigenes Segment. Callback bekommt Segment-Index + Zeichen-Range +
   *  den gewählten Sprecher (Persistenz macht der Parent via PUT). */
  onSplitSegment?: (idx: number, charStart: number, charEnd: number, speaker: string) => void;
}

// Re-segmentierte Segmente (resegment.ts) sind strukturell identisch zu
// Segment[] — die Optionals sind nur für die Typ-Kompatibilität mit dem
// generischen Input nötig; zur Laufzeit sind start/end/text immer gesetzt.
export type DisplaySegment = Segment;

/** Wieviele Pixel Drag-Bewegung = 1 Wort (Grenz-Marker). */
const PX_PER_WORD = 16;

/**
 * Feature 2026-08-16 (Edit): Zeichen-Range einer DOM-Selection innerhalb
 * eines Text-Containers → [start, end) im Segment-Text. Zählt die Längen
 * aller Text-Nodes des Containers in DOM-Reihenfolge (die Wort-Spans +
 * Trenn-Spaces ergeben exakt seg.text). Null bei kollabierter Selection
 * oder wenn die Selection über den Container hinausragt.
 */
function selectionCharRange(container: HTMLElement, segText: string): { start: number; end: number } | null {
  const sel = window.getSelection();
  if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return null;
  const range = sel.getRangeAt(0);
  if (!container.contains(range.startContainer) || !container.contains(range.endContainer)) return null;
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
  const nodes: Text[] = [];
  let n: Node | null;
  while ((n = walker.nextNode())) nodes.push(n as Text);
  const posOf = (node: Node, offset: number): number => {
    let pos = 0;
    for (const tn of nodes) {
      if (tn === node) return pos + offset;
      pos += tn.data?.length ?? 0;
    }
    return pos;
  };
  const s = posOf(range.startContainer, range.startOffset);
  const e = posOf(range.endContainer, range.endOffset);
  const start = Math.min(s, e);
  const end = Math.max(s, e);
  if (end - start < 1 || start >= segText.length) return null;
  return { start, end: Math.min(end, segText.length) };
}

export function SegmentList({ segments, onSeekTo, onSeekPaused, activeIdx, onActiveChange, recordingId, onEdited, currentTime, searchQuery, searchJump, onBoundaryMoved, onBoundaryDragEnd, onSegmentInsert, onSegmentDelete, fillHeight, onSplitSegment }: Props) {
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
  // Feature 2026-08-16 (Edit): Text-Markierung → Split-Modal.
  const [splitCandidate, setSplitCandidate] = useState<{
    idx: number;
    charStart: number;
    charEnd: number;
    preview: string;
  } | null>(null);
  const [splitSpeaker, setSplitSpeaker] = useState("");
  const [splitSpeakerOpen, setSplitSpeakerOpen] = useState(false);
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
    // Nur den Transkriptions-Container scrollen (nicht scrollIntoView —
    // das zöge die SEITE mit; siehe Auto-Scroll-Kommentar 2026-08-16).
    const container = containerRef.current;
    const el = rowRefs.current[searchJump.idx];
    if (!container || !el) return;
    const tRect = el.getBoundingClientRect();
    const cRect = container.getBoundingClientRect();
    const relTop = tRect.top - cRect.top + container.scrollTop;
    const targetTop = relTop - (container.clientHeight - tRect.height) / 2;
    container.scrollTo({ top: targetTop, behavior: "smooth" });
  }, [searchJump]);

  // Auto-Scroll: das AKTIVE WORT ungefähr in die Mitte des Viewports der
  // Transkription zentrieren (User 2026-08-16: „Scroll soll immer so sein,
  // dass das aktive Wort ungefähr in der Mitte ist"). WICHTIG: NICHT
  // scrollIntoView — das scrollt ALLE scrollbaren Vorfahren (auch die
  // SEITE!) und ließ die Seite während des Playbacks nach unten rutschen
  // (User: „Wenn man Stop drückt, scrollt die Seite nach unten"). Statt-
  // dessen container.scrollTo: nur der Transkriptions-Container bewegt sich.
  // Fallback: aktive Zeile, falls das aktive Wort nicht markiert ist.
  const activeW = activeIdx >= 0 && currentTime != null
    ? activeWordIndex(segments[activeIdx]?.words ?? [], currentTime)
    : -1;
  useEffect(() => {
    const container = containerRef.current;
    if (!container || activeIdx < 0) return;
    const activeWord = container.querySelector<HTMLElement>("[data-active-word=\"true\"]");
    const target = activeWord ?? rowRefs.current[activeIdx];
    if (!target) return;
    const tRect = target.getBoundingClientRect();
    const cRect = container.getBoundingClientRect();
    const relTop = tRect.top - cRect.top + container.scrollTop;
    const targetTop = relTop - (container.clientHeight - tRect.height) / 2;
    container.scrollTo({ top: targetTop, behavior: "smooth" });
  }, [activeIdx, activeW]);

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
    // Auto-Grow: Die Textarea soll exakt so hoch sein wie der (umgebrochene)
    // Text — HTML-Default rows=2 würde den sichtbaren Bereich sonst auf zwei
    // Zeilen quetschen (User 2026-08-16).
    if (editingIdx !== null && editAreaRef.current) {
      const el = editAreaRef.current;
      el.style.height = "auto";
      el.style.height = el.scrollHeight + "px";
    }
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

  // ── Klick-vs-Doppelklick (2026-08-16): Einzelklick = Playback-Start,
  // Doppelklick = Edit-Modus. Der ERSTE Klick eines Doppelklicks darf kein
  // Playback starten — der Playback-Start wird deshalb 280 ms verzögert und
  // bei onDoubleClick gecancelt (Browser-Doppelklick-Fenster ~300–500 ms).
  const clickTimer = useRef<number | null>(null);
  function cancelClickTimer() {
    if (clickTimer.current !== null) {
      clearTimeout(clickTimer.current);
      clickTimer.current = null;
    }
  }
  function scheduleClick(fn: () => void) {
    cancelClickTimer();
    clickTimer.current = window.setTimeout(() => {
      clickTimer.current = null;
      fn();
    }, 280);
  }
  useEffect(() => cancelClickTimer, []);

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

  // Feature 2026-08-16 (Edit): Text-Markierung in einem Segment →
  // Split-Modal öffnen (Zeichen-Range aus der DOM-Selection).
  function handleTextMouseUp(i: number, el: HTMLElement) {
    if (editingIdx !== null) return;
    const text = segments[i]?.text ?? "";
    const r = selectionCharRange(el, text);
    if (!r) return;
    // Volle Segment-Selektion ist kein Split (nichts bliebe übrig)
    if (r.start === 0 && r.end >= text.length) return;
    setSplitCandidate({ idx: i, charStart: r.start, charEnd: r.end, preview: text.slice(r.start, r.end) });
    setSplitSpeaker("");
    // Selection entfernen → das native Auswahlmenü (Copy/Suche) schließt
    // sich damit auch auf Mobile, nur unser Split-Modal bleibt.
    window.getSelection()?.removeAllRanges();
  }

  // Feature 2026-08-16 (Edit): Split bestätigen → Callback an den Parent
  // (der persistiert). Default-Sprecher: der des Original-Segments.
  function confirmSplit() {
    if (!splitCandidate) return;
    const orig = segments[splitCandidate.idx]?.speaker;
    const spk = splitSpeaker || orig || "SPEAKER_00";
    onSplitSegment?.(splitCandidate.idx, splitCandidate.charStart, splitCandidate.charEnd, spk);
    setSplitCandidate(null);
    setSplitSpeaker("");
    setSplitSpeakerOpen(false);
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
    <>
    <div
      ref={containerRef}
      className={`
        bg-seg-bg border border-border rounded-sm
        overflow-y-auto scroll-smooth
        scrollbar-thin py-1
        ${fillHeight ? "h-full max-h-none flex-1" : "max-h-[260px]"}
      `}
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
          onClick={() => scheduleClick(() => handleClick(i))}
          onDoubleClick={() => {
            if (!recordingId) return;
            // Erster Klick des Doppelklicks: Playback-Timer verwerfen —
            // Doppelklick = Edit-Modus, KEIN Playback.
            cancelClickTimer();
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
              className="flex-1 min-w-0 bg-panel2 border border-border rounded-sm px-2 py-1 text-[13px] leading-[1.4] overflow-hidden"
              value={editText}
              onChange={(e) => {
                setEditText(e.target.value);
                // Auto-Grow: Höhe an den (umgebrochenen) Inhalt anpassen,
                // damit beim Tippen nichts abgeschnitten wird.
                const el = e.target;
                el.style.height = "auto";
                el.style.height = el.scrollHeight + "px";
              }}
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
            <span
              className="text-txt flex-1 min-w-0"
              onMouseUp={onSplitSegment ? (e) => handleTextMouseUp(i, e.currentTarget) : undefined}
              onTouchEnd={onSplitSegment ? (e) => {
                // Mobile: Touch-Textauswahl feuert kein (zuverlässiges) mouseup —
                // nach dem Loslassen die Selection prüfen. Verzögert, damit die
                // Auswahl final ist; removeAllRanges schließt das native Menü.
                const el = e.currentTarget;
                setTimeout(() => handleTextMouseUp(i, el), 10);
              } : undefined}
              data-split-container
            >
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
                          data-active-word={isActive ? "true" : undefined}
                          onClick={(e) => {
                            e.stopPropagation();
                            scheduleClick(() => handleWordClick(i, w.start));
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
    {/* Feature 2026-08-16 (Edit): Split-Modal nach Text-Markierung */}
    {splitCandidate && onSplitSegment && (
      <>
        <div
          className="fixed inset-0 z-30 bg-black/20"
          onClick={() => {
            setSplitCandidate(null);
            setSplitSpeakerOpen(false);
          }}
        />
        <div className="fixed z-40 left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[340px] max-w-[90vw] bg-panel2 border border-border rounded-md shadow-xl p-4">
          <div className="text-[13px] font-semibold mb-1">✂ {t("split_segment_title")}</div>
          <div className="text-[12px] text-muted2 mb-2 leading-[1.5] break-words bg-panel rounded-sm px-2 py-1.5 max-h-[90px] overflow-y-auto scrollbar-thin">
            „{splitCandidate.preview}“
          </div>
          <div className="mb-3">
            <div className="text-[11px] text-muted2 mb-1">{t("split_speaker_label")}</div>
            <div className="relative">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setSplitSpeakerOpen((o) => !o);
                }}
                className="w-full text-left px-2 py-1 text-[12px] bg-panel border border-border rounded-sm uppercase tracking-[.04em]"
              >
                {(splitSpeaker || segments[splitCandidate.idx]?.speaker || t("split_speaker_default")).replace("SPEAKER_", "")}
              </button>
              {splitSpeakerOpen && (
                <>
                  <div
                    className="fixed inset-0 z-10"
                    onClick={(e) => {
                      e.stopPropagation();
                      setSplitSpeakerOpen(false);
                    }}
                  />
                  <div className="absolute top-full left-0 right-0 z-20 mt-0.5 max-h-[160px] overflow-y-auto bg-panel2 border border-border rounded-md shadow-xl py-0.5">
                    {speakerOptions.map((opt) => (
                      <button
                        key={opt}
                        onClick={(e) => {
                          e.stopPropagation();
                          setSplitSpeaker(opt);
                          setSplitSpeakerOpen(false);
                        }}
                        className={`block w-full text-left px-2 py-1 text-[11px] uppercase tracking-[.04em] cursor-pointer hover:bg-accent/10 ${
                          opt === (splitSpeaker || segments[splitCandidate.idx]?.speaker)
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
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <button
              onClick={() => {
                setSplitCandidate(null);
                setSplitSpeakerOpen(false);
              }}
              className="text-[12px] text-muted2 hover:text-txt border border-border rounded-sm px-3 py-1 transition-colors"
            >
              {t("split_segment_cancel")}
            </button>
            <button
              onClick={confirmSplit}
              className="text-[12px] text-white bg-accent rounded-sm px-3 py-1 font-semibold hover:opacity-90 transition-opacity"
            >
              {t("split_segment_confirm")}
            </button>
          </div>
        </div>
      </>
    )}
    </>
  );
}
