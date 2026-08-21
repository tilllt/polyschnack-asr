import { Fragment, useRef, useState, useEffect, useMemo, useLayoutEffect } from "react";
import type { ReactNode } from "react";
import type { Segment } from "../api";
import { updateSegment, renameSpeaker } from "../api";
import { useYjsTranscription } from "../hooks/useYjsTranscription";
import { abbreviateMid, fmtTimecode } from "../format";
import { activeWordIndex, confidenceClass, hasConfidence, nextWordTarget } from "../karaoke";
import { moveBoundary, wordRangeToCharRange, type ResegWord } from "../resegment";
import { computeSplitPopover } from "../splitPosition";
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
  /** Fix 2026-08-17: Play-Zustand — Karaoke-Vorlauf (KARAOKE_LEAD_S) gilt
   *  NUR während der Wiedergabe; pausiert/gestoppt rechnet exakt (Markierung
   *  bleibt an der Stopp-Position, kein Sprung auf das nächste Wort). */
  isPlaying?: boolean;
  /** Review-Fix 2026-08-15 (Such-UI): Query für grüne Treffer-Hervorhebung
   *  (bewusst ANDERS als der gelbe Karaoke-Marker) + Sprung-Ziel. */
  searchQuery?: string;
  searchJump?: { idx: number; nonce: number } | null;
  /** Feature 2026-08-15: draggable Timecode-Marker zwischen den Segmenten.
   *  Wird dieser Callback gesetzt, sind die Grenzen ziehbar: nach oben =
   *  Grenze in der Zeit zurück (Segment N verliert am Ende Wörter, N+1
   *  gewinnt vorne), nach unten = umgekehrt. Wort für Wort, nie geteilt.
   *  Erster (Start) und letzter (Ende) Marker sind bewusst NICHT ziehbar.
   *  Change 009: die Drag-Preview ist LOKAL (dragPreview-State) — der
   *  Callback wird nur beim Loslassen für den Commit gerufen. */
  onBoundaryDragEnd?: (segments: Segment[]) => void;
  /** Feature 2026-08-16 (Mockup): „−" im Kreis vor dem Timecode — löscht
   *  Segment `idx` (Text wandert ans vorige Segment). Bleibt (Change 055). */
  onSegmentDelete?: (idx: number) => void;
  /** Feature 2026-08-16 (Edit-Vollbild): true = Liste füllt die verfügbare
   *  Höhe des Parents statt der kompakten 260px-Begrenzung. */
  fillHeight?: boolean;
  /** Feature 2026-08-16 (Edit): Text-Markierung in einem Segment →
   *  eigenes Segment. Callback bekommt Segment-Index + Zeichen-Range +
   *  den gewählten Sprecher (Persistenz macht der Parent via PUT). */
  onSplitSegment?: (idx: number, charStart: number, charEnd: number, speaker: string) => void;
  /** Change 067-Fix: Kollaboration nur bei geteilten Aufnahmen
   *  (has_shares || is_anon_shared || shared_with_me) — sonst keine
   *  Yjs-Verbindung, keine unnötigen Checks. */
  collabEnabled?: boolean;
  /** Change 056: Text-Markierung → „Annotate" (Kommentar zur Passage).
   *  Klick auf den 💬-Button liefert Markierungs-Koordinaten inkl.
   *  Text-Vorschau; die Karte öffnet das Annotate-Popover. */
  onAnnotate?: (a: {
    idx: number;
    charStart: number;
    charEnd: number;
    preview: string;
  }) => void;
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

export function SegmentList({ segments: segmentsProp, onSeekTo, onSeekPaused, activeIdx, onActiveChange, recordingId, onEdited, currentTime, isPlaying, searchQuery, searchJump, onBoundaryDragEnd, onSegmentDelete, fillHeight, onSplitSegment, onAnnotate, collabEnabled = false }: Props) {
  // Change 053: Yjs-Kollaboration (Live-Sync, Awareness, Fallback Solo).
  // Change 067-Fix: Verbindung nur bei geteilten Aufnahmen (collabEnabled)
  // + Leiste nur sichtbar, wenn ANDERE gerade aktiv bearbeiten.
  // Change 068: Autosave statt Button — Debounce ohne Version, Version
  // erst beim Verlassen des Edit-Mode.
  const {
    conn: yjsConn,
    activeEditors,
    hasCollab,
    setSegmentText,
    saving: yjsSaving,
    setEditingActive,
  } = useYjsTranscription(recordingId, segmentsProp, (texts) => {
    if (!onEdited) return;
    onEdited(
      texts.map((text, i) => ({ ...(segmentsProp[i] ?? {}), text })),
      texts.join(" "),
    );
  }, collabEnabled);
  const containerRef = useRef<HTMLDivElement>(null);
  const rowRefs = useRef<(HTMLDivElement | null)[]>([]);
  const renameInputRef = useRef<HTMLInputElement>(null);
  const editAreaRef = useRef<HTMLTextAreaElement>(null);
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const [editText, setEditText] = useState("");

  // Change 067-Fix: eigenes editing-Flag in die Awareness melden —
  // Andere sehen „X bearbeitet gerade" nur, während wirklich ein
  // Textfeld aktiv ist (nicht beim bloßen Öffnen der Seite).
  useEffect(() => {
    setEditingActive(editingIdx !== null);
  }, [editingIdx, setEditingActive]);
  const [saving, setSaving] = useState(false);
  const [renamingSpeakerIdx, setRenamingSpeakerIdx] = useState<number | null>(null);
  // Change 009 (Single Source of Truth): Drag-Preview ist LOKAL — während
  // des Ziehens zeigt die Liste `dragPreview`, sonst die Prop (Modell).
  // Kein Parent-State, keine Referenz-/Inhalts-Vergleiche zur Sync.
  const [dragPreview, setDragPreview] = useState<Segment[] | null>(null);
  const shown = dragPreview ?? segmentsProp;
  const [renameText, setRenameText] = useState("");
  const [renameSaving, setRenameSaving] = useState(false);
  // Feature 2026-08-16: Dropdown „Sprecher wählen" (Klick auf den Namen) —
  // offen für Segment-Index i; null = zu.
  const [openSpeakerMenu, setOpenSpeakerMenu] = useState<number | null>(null);
  // Feature 2026-08-16 (Edit): Text-Markierung → Split-Symbol (Change 013).
  // KEIN Auto-Modal mehr: handleTextMouseUp (Desktop) bzw. die eigene
  // Touch-Markierung setzen einen ANKER mit Y-Position; das Symbol erscheint
  // links am Rand auf Markierungshöhe. Klick aufs Symbol → Popover (Sprecher).
  const [splitAnchor, setSplitAnchor] = useState<{
    idx: number;
    charStart: number;
    charEnd: number;
    preview: string;
    y: number; // Markierungsbeginn relativ zur Segment-Zeile (px)
  } | null>(null);
  // Change 013 (Tablet): EIGENE Touch-Markierung — ersetzt die native
  // Selektion, die auf Android das Google-Suchassistenten-Popup öffnet.
  // pointerdown/up bestimmen den Wort-Range über data-word-index.
  const [touchSel, setTouchSel] = useState<{
    idx: number;
    startWord: number;
    endWord: number;
  } | null>(null);
  // Fix 2026-08-17: Touch-Markierung — siehe touchAction auf Wort-Spans.
  // (State entfällt: touch-action steuert der Browser direkt am Span.)
  const [splitSpeaker, setSplitSpeaker] = useState("");
  // Feature 2026-08-18: „+ Neuer Sprecher" — manuell erweiterbare
  // Speaker-Liste. newSpeakerMode: "seg" (Segment-Dropdown) | "split"
  // (Split-Popover) | null; newSpeakerName = aktueller Input.
  const [newSpeakerMode, setNewSpeakerMode] = useState<"seg" | "split" | null>(null);
  const [newSpeakerName, setNewSpeakerName] = useState("");
  // Change 013: Popover (nach Symbol-Klick) und Sprecher-Dropdown getrennt
  // steuern — ein gemeinsamer State öffnete beide gleichzeitig und der
  // Dropdown-Catcher (fixed inset-0) blockierte das ganze Popover.
  const [splitPopoverOpen, setSplitPopoverOpen] = useState(false);
  const [splitSpeakerOpen, setSplitSpeakerOpen] = useState(false);
  // Change 058: Split-Popover-Position — NEBEN dem Split-Symbol (gemessen),
  // nie am Viewport-Rand. Der alte Fix `left: 8` poppte auf Desktop neben
  // dem Hauptcontainer links auf (User-Befund).
  const splitPosRef = useRef<HTMLDivElement>(null);
  const [splitPos, setSplitPos] = useState<{ left: number; top: number } | null>(null);
  useLayoutEffect(() => {
    if (!splitPopoverOpen || !splitAnchor) return;
    const row = rowRefs.current[splitAnchor.idx];
    const pop = splitPosRef.current;
    if (!row || !pop) return;
    const rowRect = row.getBoundingClientRect();
    // Spiegel der Button-Position (Kreis: left-[10px], top-Clamp wie im JSX)
    const btnTop = Math.min(
      Math.max(0, splitAnchor.y - 13),
      Math.max(0, (rowRect.height ?? 26) - 26),
    );
    setSplitPos(
      computeSplitPopover(
        { left: rowRect.left + 10, top: rowRect.top + btnTop, width: 26, height: 26 },
        pop.offsetWidth,
        pop.offsetHeight,
        window.innerWidth,
        window.innerHeight,
      ),
    );
  }, [splitPopoverOpen, splitAnchor]);
  // Change 058: Escape schließt das Split-Popover (wie Klick-außerhalb).
  useEffect(() => {
    if (!splitPopoverOpen) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setSplitAnchor(null);
        setSplitSpeakerOpen(false);
        setSplitPopoverOpen(false);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [splitPopoverOpen]);
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
  // User 2026-08-20: Im Edit-Modus (Textbox offen) sind ALLE Auto-Scrolls
  // ausgeschaltet — sonst scrollt die Wiedergabe/Suche die Textbox weg.
  useEffect(() => {
    if (!searchJump) return;
    if (editingIdx !== null) return;
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
  }, [searchJump, editingIdx]);

  // Auto-Scroll: das AKTIVE WORT ungefähr in die Mitte des Viewports der
  // Transkription zentrieren (User 2026-08-16: „Scroll soll immer so sein,
  // dass das aktive Wort ungefähr in der Mitte ist"). WICHTIG: NICHT
  // scrollIntoView — das scrollt ALLE scrollbaren Vorfahren (auch die
  // SEITE!) und ließ die Seite während des Playbacks nach unten rutschen
  // (User: „Wenn man Stop drückt, scrollt die Seite nach unten"). Statt-
  // dessen container.scrollTo: nur der Transkriptions-Container bewegt sich.
  // Fallback: aktive Zeile, falls das aktive Wort nicht markiert ist.
  const activeW = activeIdx >= 0 && currentTime != null
    ? activeWordIndex(shown[activeIdx]?.words ?? [], currentTime, isPlaying ? undefined : 0)
    : -1;
  useEffect(() => {
    // User 2026-08-20: Während der Edit-Modus offen ist (Textbox), kein
    // Auto-Scroll — die Wiedergabe darf die Textbox nicht wegbewegen.
    if (editingIdx !== null) return;
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
  }, [activeIdx, activeW, editingIdx]);

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
    onSeekTo?.(shown[idx].start);
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
    if (!onBoundaryDragEnd) return;
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
    // Change 009: Basis ist die ANGEZEIGTE Liste (`shown`), nicht die Prop —
    // bei lokaler Preview ist shown == segmentsProp (Preview ist null).
    dragRef.current = { idx, startY: e.clientY, lastWords: 0, baseSegments: shown, currentList: shown };
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
      // Change 009: Preview ist LOKAL (kein Parent-State mehr).
      setDragPreview(next);
    }
  }

  function onBoundaryPointerUp() {
    const d = dragRef.current;
    if (!d) return;
    dragRef.current = null;
    setDragIdx(null);
    // Change 009: Preview verwerfen; Commit über den Callback.
    setDragPreview(null);
    onBoundaryDragEnd?.(d.currentList);
  }

  async function handleSave(idx: number) {
    if (saving || !recordingId || !onEdited) return;
    if (hasCollab) {
      // Change 053 + 068: Kollaboration — Änderung geht live an alle
      // Clients (Yjs) und wird automatisch gespeichert: Autosave nach
      // Debounce (ohne Version), beim Verlassen des Edit-Mode genau eine
      // Version (create_version=true). Kein manueller Button mehr.
      setSegmentText(idx, editText);
      setEditingIdx(null);
      return;
    }
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

  // Feature 2026-08-16 (Edit): Text-Markierung → Split-Symbol (Change 013).
  // Statt Auto-Modal: Anker mit Y-Position des Markierungsbeginns setzen —
  // das Symbol erscheint links am Rand auf dieser Höhe. Desktop nutzt die
  // native Selektion; Touch hat die eigene Markierung (touchSel) → hier wird
  // nur der Anker gesetzt.
  function setAnchorFromRange(i: number, r: { start: number; end: number }, yOverride?: number) {
    const text = shown[i]?.text ?? "";
    // Y-Position der AUSWAHL-MITTE relativ zur Segment-Zeile (User-Vorgabe
    // 2026-08-18: das Symbol erscheint links mittig zur Markierung, nicht
    // am Auswahl-Start).
    let y = yOverride ?? 0;
    if (yOverride === undefined) {
      const sel = window.getSelection();
      const rowEl = rowRefs.current[i];
      if (sel && sel.rangeCount > 0 && rowEl) {
        try {
          const rowRect = rowEl.getBoundingClientRect();
          const rangeRect = sel.getRangeAt(0).getBoundingClientRect();
          y = Math.max(0, rangeRect.top - rowRect.top + rangeRect.height / 2);
        } catch {
          y = 0;
        }
      }
    }
    setSplitAnchor({ idx: i, charStart: r.start, charEnd: r.end, preview: text.slice(r.start, r.end), y });
    setSplitSpeaker("");
    // Fix 2026-08-18 (Desktop/Firefox): NICHT mehr window.getSelection()
    // löschen — die native Textmarkierung bleibt sichtbar, bis der User
    // das Split-Symbol klickt (Regression gemeldet: Markierung verschwand
    // sofort beim Loslassen). Das native Auswahlmenü stört auf Desktop
    // nicht (kein Overlay wie Android); der Symbol-Klick und confirmSplit
    // räumen die Selection explizit weg. Ein selectionchange-Guard löscht
    // den Anker, wenn die Auswahl woanders hingeht (kein Geister-Icon).
  }

  // Fix 2026-08-17 (Touch): die eigene Markierung hat KEINE native Selection,
  // also die Y-Position über die Wort-Spans bestimmen (Startwort → Zeilenmitte).
  // Liefert px relativ zur Segment-Zeile, oder 0 wenn nicht ermittelbar.
  function touchAnchorY(i: number, startWord: number, endWord: number): number | undefined {
    const rowEl = rowRefs.current[i];
    if (!rowEl) return undefined;
    try {
      const rowRect = rowEl.getBoundingClientRect();
      const segEl = rowEl.querySelector("[data-split-container]");
      if (!segEl) return undefined;
      const spans = segEl.querySelectorAll("[data-word-index]");
      const lo = Math.min(startWord, endWord);
      const hi = Math.max(startWord, endWord);
      const first = spans[lo];
      const last = spans[hi];
      if (!first) return undefined;
      const a = (first as HTMLElement).getBoundingClientRect();
      const b = (last as HTMLElement).getBoundingClientRect();
      // Mitte des markierten Bereichs (Anfangswort bis Endwort)
      const midY = (Math.min(a.top, b.top) + Math.max(a.bottom, b.bottom)) / 2;
      return Math.max(0, midY - rowRect.top);
    } catch {
      return undefined;
    }
  }

  function handleTextMouseUp(i: number, el: HTMLElement) {
    if (editingIdx !== null) return;
    const text = shown[i]?.text ?? "";
    const r = selectionCharRange(el, text);
    if (!r) return;
    // Volle Segment-Selektion ist kein Split (nichts bliebe übrig)
    if (r.start === 0 && r.end >= text.length) return;
    setAnchorFromRange(i, r);
  }

  // ── Change 013 (Tablet): eigene Touch-Markierung ──────────────────────
  // Android öffnet bei nativer Textauswahl den Google-Suchassistenten;
  // user-select:none (pointer-coarse) verhindert die native Selektion.
  // Stattdessen: Wort-Range über Pointer-Events + data-word-index.
  function wordIndexFromEvent(e: React.PointerEvent): number | null {
    const t = e.target as HTMLElement;
    const w = t.closest?.("[data-word-index]");
    if (!w) return null;
    const idx = Number((w as HTMLElement).dataset.wordIndex);
    return Number.isFinite(idx) ? idx : null;
  }

  function handleTextPointerDown(i: number, e: React.PointerEvent) {
    if (editingIdx !== null) return;
    if (e.pointerType !== "touch") return; // Desktop: native Selektion
    e.preventDefault(); // native Touch-Selektion (Google-Popup) verhindern
    const w = wordIndexFromEvent(e);
    if (w === null) return;
    setTouchSel({ idx: i, startWord: w, endWord: w });
  }

  function handleTextPointerMove(i: number, e: React.PointerEvent) {
    const ts = touchSel;
    if (!ts || ts.idx !== i || e.pointerType !== "touch") return;
    // Fix 2026-08-17 (Touch-Drag): Bei Touch setzt der Browser implizit
    // Pointer Capture auf das Start-Element (gotpointercapture) → e.target
    // bleibt bei jedem move der Wort-Span 0. Deshalb die Position über
    // elementFromPoint auflösen, nicht über e.target.
    const el = document.elementFromPoint(e.clientX, e.clientY);
    const w = el ? (el.closest?.("[data-word-index]") as HTMLElement | null) : null;
    if (!w) return;
    const wi = Number((w as HTMLElement).dataset.wordIndex);
    if (!Number.isFinite(wi)) return;
    if (wi !== ts.endWord) setTouchSel({ ...ts, endWord: wi });
  }

  function handleTextPointerUp(i: number) {
    const ts = touchSel;
    if (!ts || ts.idx !== i) return;
    // Fix 2026-08-18 (User-Vorgabe): Ein TAP auf ein Wort ist ein Klick
    // (= Play ab dem Wort) und KEINE Markierung — kein Split-Anker. Erst
    // ein Drag über 2+ Wörter markiert und zeigt das Split-Symbol.
    if (ts.startWord === ts.endWord) return;
    // Fix 2026-08-17: Markierung NACH dem Loslassen sichtbar lassen —
    // sie verschwindet erst beim Klick aufs Split-Symbol (dort
    // setTouchSel(null) + Popover). Kein setTouchSel(null) hier!
    const words = (shown[i]?.words ?? []) as ResegWord[];
    if (words.length === 0) return;
    const r = wordRangeToCharRange(words, ts.startWord, ts.endWord);
    if (!r) return;
    // Fix 2026-08-17: Touch-Markierung hat keine native Selection →
    // Y-Position über die Wort-Spans (Mitte des markierten Bereichs).
    setAnchorFromRange(ts.idx, r, touchAnchorY(ts.idx, ts.startWord, ts.endWord));
  }

  // Feature 2026-08-16 (Edit): Split bestätigen → Callback an den Parent
  // (der persistiert). Default-Sprecher: der des Original-Segments.
  function confirmSplit() {
    if (!splitAnchor) return;
    const orig = shown[splitAnchor.idx]?.speaker;
    const spk = splitSpeaker || orig || "SPEAKER_00";
    onSplitSegment?.(splitAnchor.idx, splitAnchor.charStart, splitAnchor.charEnd, spk);
    // Native Textmarkierung wegräumen (Desktop: bleibt bis zum Klick sichtbar)
    window.getSelection()?.removeAllRanges();
    setSplitAnchor(null);
    setSplitSpeaker("");
    setSplitSpeakerOpen(false);
    setSplitPopoverOpen(false);
  }

  // Fix 2026-08-18 (Desktop/Firefox): Die native Textmarkierung bleibt nach
  // dem Loslassen sichtbar (kein removeAllRanges im Mouse-Pfad mehr). Geht
  // die Auswahl später woanders hin oder kollabiert sie (Klick in den Text),
  // verschwindet der Split-Anker mit — kein Geister-Icon ohne Markierung.
  // splitPopoverOpenRef: SYNCHRON im Icon-Klick gesetzt, BEVOR
  // removeAllRanges() das selectionchange-Event auslöst — sonst würde der
  // Guard den Anker löschen, während der Dialog sich öffnen will.
  const splitPopoverOpenRef = useRef(false);
  useEffect(() => {
    splitPopoverOpenRef.current = splitPopoverOpen;
  }, [splitPopoverOpen]);
  useEffect(() => {
    if (!splitAnchor || splitPopoverOpenRef.current) return;
    const onChange = () => {
      const sel = window.getSelection();
      if (!sel || sel.isCollapsed || sel.rangeCount === 0) setSplitAnchor(null);
    };
    document.addEventListener("selectionchange", onChange);
    return () => document.removeEventListener("selectionchange", onChange);
  }, [splitAnchor, splitPopoverOpen]);

  // Erkannte Sprecher dieser Aufnahme = unique speaker-Werte aller Segmente.
  const speakerOptions = useMemo(() => {
    const set = new Set<string>();
    for (const s of shown) if (s.speaker) set.add(s.speaker);
    return [...set];
  }, [shown]);

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

  // Feature 2026-08-18: „+ Neuer Sprecher" bestätigen — setzt den
  // eingegebenen Namen als Speaker für das Split-Segment (Mode "split")
  // oder als neuen Speaker für DIESES Segment (Mode "seg", PATCH).
  async function handleAddNewSpeaker(mode: "seg" | "split") {
    const name = newSpeakerName.trim();
    if (!name) return;
    const speakerName = name.toUpperCase().startsWith("SPEAKER_")
      ? name.toUpperCase()
      : `SPEAKER_${name.replace(/\s+/g, "_").toUpperCase()}`;
    if (mode === "split") {
      setSplitSpeaker(speakerName);
      setSplitSpeakerOpen(false);
      setNewSpeakerMode(null);
      setNewSpeakerName("");
      return;
    }
    // seg: auf das Segment anwenden, dessen Menü offen ist
    const idx = openSpeakerMenu;
    if (idx === null) return;
    setNewSpeakerMode(null);
    setNewSpeakerName("");
    void handleSetSpeaker(idx, speakerName);
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
    {hasCollab && onEdited && activeEditors.length > 0 && (
      <div className="flex items-center gap-2 px-3 py-1 text-[12px] text-fg-muted border-b border-border">
        <span title={yjsConn === "connected" ? "Live-Sync aktiv — Änderungen werden automatisch gespeichert (Autosave)" : "Verbindung zum Sync-Server wird aufgebaut"}>
          {yjsConn === "connected" ? "●" : "◌"} Kollaboration aktiv
        </span>
        <span title={activeEditors.join(", ")}>· {activeEditors.join(", ")} bearbeitet gerade</span>
        {yjsSaving && <span className="ml-auto">Speichert…</span>}
      </div>
    )}
    <div
      ref={containerRef}
      className={`
        bg-seg-bg border border-border rounded-sm
        overflow-y-auto scroll-smooth
        scrollbar-thin py-1
        ${fillHeight ? "h-full max-h-none flex-1" : "max-h-[260px]"}
      `}
    >
      {shown.map((seg, i) => {
        const speaker = seg.speaker;
        return (
        <Fragment key={i}>
        {i > 0 && (
          /* ── Hairline als Segment-Trennung (Change 055): der „+"-Insert-
             Button ist entfernt (Insert-Segment-Modus übernimmt); die
             Zeilen rücken enger zusammen, die Trennung bleibt. ── */
          <div
            className="flex items-center px-3"
            onClick={(e) => e.stopPropagation()}
            onDoubleClick={(e) => e.stopPropagation()}
          >
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
            // Change 013: Doppelklick darf kein Split-Symbol hinterlassen —
            // die Browser-Wort-Selektion des Doppelklicks setzt sonst über
            // handleTextMouseUp einen Anker, der im Edit stört.
            setSplitAnchor(null);
            setSplitSpeakerOpen(false);
            setSplitPopoverOpen(false);
            setTouchSel(null);
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
              const target = nextWordTarget(shown, activeIdx, currentTime ?? 0, e.key === "ArrowRight" ? 1 : -1);
              if (!target) return;
              const w = shown[target.segIdx]?.words?.[target.wIdx];
              if (!w) return;
              onActiveChange?.(target.segIdx);
              // Cursor-Navigation: nur springen, NICHT abspielen
              (onSeekPaused ?? onSeekTo)?.(typeof w.start === "number" ? w.start : 0);
            }
          }}
          className={`
            relative flex items-baseline gap-x-2 px-3 py-[6px]
            cursor-pointer transition-colors duration-[120ms]
            border-l-2 border-transparent
            text-[13.5px] leading-[1.5]
            hover:bg-[rgba(91,140,255,0.07)]
            ${i === activeIdx ? "seg-active" : ""}
            ${editingIdx === i ? "cursor-default" : ""}
          `}
        >
          {/* Change 013/056: Kontext-Leiste links am Rand auf Markierungshöhe —
              Split-Symbol (Insert Segment) + 💬 Annotate. Erscheint nur, wenn
              in DIESER Zeile eine Markierung aktiv ist. */}
          {splitAnchor && splitAnchor.idx === i && (onSplitSegment || onAnnotate) && (
            <>
            {onSplitSegment && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                // Fix 2026-08-17: Markierung bleibt nach dem Loslassen
                // sichtbar — erst der Symbol-Klick räumt sie und öffnet
                // den Dialog.
                // Fix 2026-08-18 (Desktop): native Selection ebenfalls
                // wegräumen (bleibt seit dem Mouse-Fix sichtbar). Die Ref
                // wird SYNCHRON vor removeAllRanges gesetzt, damit der
                // selectionchange-Guard den Anker nicht löscht.
                splitPopoverOpenRef.current = true;
                setTouchSel(null);
                window.getSelection()?.removeAllRanges();
                setSplitPopoverOpen(true);
                setSplitSpeakerOpen(false);
              }}
              className="absolute left-[10px] z-20 w-[26px] h-[26px] rounded-full flex items-center justify-center flex-shrink-0
                text-accent bg-white/70
                hover:bg-accent/15 hover:scale-110 active:scale-95
                shadow-sm transition-all"
              style={{
                // Fix 2026-08-18: Icon innerhalb der Zeile halten — ohne
                // Clamp ragte es bei Markierungen in der letzten Textzeile
                // über die Zeilen-Unterkante (bzw. den max-h-Container)
                // hinaus und wurde unten abgeschnitten.
                top: Math.min(
                  Math.max(0, splitAnchor.y - 13),
                  Math.max(0, (rowRefs.current[i]?.offsetHeight ?? 26) - 26),
                ),
              }}
              title={t("split_segment_title")}
              aria-label={t("split_segment_title")}
              data-testid="split-anchor-btn"
            >
              {/* Split-Symbol 2026-08-18 (User-Design, drop.n0ne.de/u/V1T5ih.svg):
                  Kreis + zwei auseinandergezogene Haelfte mit Balken und
                  Pfeil nach aussen. Schwarz → currentColor (accent #5b8cff),
                  passt damit automatisch zum Theme. viewBox 1000er, gerendert
                  24px im 26px-Kreis. */}
              <svg width="24" height="24" viewBox="0 0 1000 1000" aria-hidden
                style={{ width: 24, height: 24, flexShrink: 0 }}
                fillRule="evenodd" clipRule="evenodd" strokeLinecap="round" strokeLinejoin="round" strokeMiterlimit={1.5}>
                <g transform="matrix(1,0,0,0.985989,-151.73878,-162.200475)">
                  <circle cx="651.739" cy="671.611" r="457.508" fill="none" stroke="currentColor" strokeWidth={67.14} />
                </g>
                <path d="M823.718,565.929L823.718,640.288L176.282,640.288L176.282,565.929L823.718,565.929ZM500,640.288L501.282,818.494M500,818.494L438.462,735.16L561.538,735.16L500,818.494Z" fill="currentColor" stroke="currentColor" strokeWidth={35.42} />
                <g transform="matrix(-1,-0,0,-1,1000,1008.782035)">
                  <path d="M823.718,565.929L823.718,640.288L176.282,640.288L176.282,565.929L823.718,565.929ZM500,640.288L501.282,818.494M500,818.494L438.462,735.16L561.538,735.16L500,818.494Z" fill="currentColor" stroke="currentColor" strokeWidth={35.42} />
                </g>
              </svg>
            </button>
            )}
            {onAnnotate && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                splitPopoverOpenRef.current = true;
                setTouchSel(null);
                window.getSelection()?.removeAllRanges();
                const sel = {
                  idx: splitAnchor.idx,
                  charStart: splitAnchor.charStart,
                  charEnd: splitAnchor.charEnd,
                  preview: splitAnchor.preview,
                };
                setSplitAnchor(null);
                onAnnotate(sel);
              }}
              className="absolute left-[42px] z-20 w-[26px] h-[26px] rounded-full flex items-center justify-center flex-shrink-0
                text-[14px] leading-none bg-white/70
                hover:bg-accent/15 hover:scale-110 active:scale-95
                shadow-sm transition-all"
              style={{
                top: Math.min(
                  Math.max(0, splitAnchor.y - 13),
                  Math.max(0, (rowRefs.current[i]?.offsetHeight ?? 26) - 26),
                ),
              }}
              title={t("annotate")}
              aria-label={t("annotate")}
              data-testid="annotate-btn"
            >
              💬
            </button>
            )}
            </>
          )}
          {onSegmentDelete && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onSegmentDelete(i);
              }}
              disabled={shown.length <= 1}
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
              ${i > 0 && onBoundaryDragEnd
                ? `cursor-ns-resize touch-none select-none rounded-sm px-0.5 -mx-0.5 ${dragIdx === i - 1 ? "bg-[rgba(91,140,255,0.16)] text-accent" : "hover:bg-[rgba(91,140,255,0.08)]"}`
                : ""}
            `}
            onClick={(e) => {
              // Timecode = Drag-Handle der Grenze davor — kein Seek/Edit
              if (i > 0 && onBoundaryDragEnd) e.stopPropagation();
            }}
            onDoubleClick={(e) => {
              if (i > 0 && onBoundaryDragEnd) e.stopPropagation();
            }}
            onPointerDown={i > 0 && onBoundaryDragEnd ? (e) => onBoundaryPointerDown(e, i - 1) : undefined}
            onPointerMove={i > 0 && onBoundaryDragEnd ? onBoundaryPointerMove : undefined}
            onPointerUp={i > 0 && onBoundaryDragEnd ? onBoundaryPointerUp : undefined}
            onPointerCancel={i > 0 && onBoundaryDragEnd ? onBoundaryPointerUp : undefined}
            title={i > 0 && onBoundaryDragEnd ? t("boundary_drag_hint") : undefined}
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
                  className="text-[11px] font-bold text-[#25d366] max-w-[120px] overflow-hidden text-ellipsis whitespace-nowrap uppercase tracking-[.04em] cursor-pointer hover:underline decoration-dotted underline-offset-2"
                  title={`${speaker.replace("SPEAKER_", "")} — ${t("speaker_dropdown_hint")}`}
                  onClick={(e) => {
                    // Feature 2026-08-16: Klick auf den Namen öffnet das
                    // Dropdown mit den erkannten Sprechern (Segment-weises
                    // Setzen). Rename nur übers Stift-Icon daneben.
                    e.stopPropagation();
                    setOpenSpeakerMenu(openSpeakerMenu === i ? null : i);
                  }}
                  onDoubleClick={(e) => e.stopPropagation()}
                >
                  {/* Fix 2026-08-18: Mid-Ellipsis — sehr lange Namen
                      (z. B. "TILL...METZ") zerhauten das Layout, weil die
                      Spalte per w-max mit dem Inhalt wuchs. */}
                  {abbreviateMid(speaker.replace("SPEAKER_", ""), 14)}
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
                          className={`block w-full max-w-[240px] text-left px-2 py-1 text-[11px] uppercase tracking-[.04em] cursor-pointer hover:bg-accent/10 break-words ${
                            opt === speaker
                              ? "text-[#25d366] font-bold"
                              : "text-muted1"
                          }`}
                        >
                          {opt.replace("SPEAKER_", "")}
                        </button>
                      ))}
                      {/* Feature 2026-08-18: manuell erweiterbare Speaker-Liste */}
                      <div className="border-t border-border/60 my-0.5" />
                      {newSpeakerMode === "seg" ? (
                        <div className="px-2 py-1 flex items-center gap-1">
                          <input
                            autoFocus
                            value={newSpeakerName}
                            onChange={(e) => setNewSpeakerName(e.target.value)}
                            onKeyDown={(e) => {
                              e.stopPropagation();
                              if (e.key === "Enter") void handleAddNewSpeaker("seg");
                              if (e.key === "Escape") {
                                setNewSpeakerMode(null);
                                setNewSpeakerName("");
                              }
                            }}
                            placeholder={t("new_speaker_placeholder")}
                            className="w-full min-w-[110px] text-[11px] bg-panel border border-border rounded-sm px-1.5 py-0.5 text-txt outline-none focus:border-accent"
                          />
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              void handleAddNewSpeaker("seg");
                            }}
                            className="flex-shrink-0 text-[11px] text-accent font-semibold px-1 hover:opacity-80"
                          >
                            {t("new_speaker_save")}
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setNewSpeakerMode("seg");
                            setNewSpeakerName("");
                          }}
                          className="block w-full text-left px-2 py-1 text-[11px] italic text-accent cursor-pointer hover:bg-accent/10"
                        >
                          {t("new_speaker_add")}
                        </button>
                      )}
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
                if (editText !== shown[i].text) {
                  handleSave(i);
                } else {
                  setEditingIdx(null);
                }
              }}
              ref={editAreaRef}
            />
          ) : (
            <span
              className="text-txt flex-1 min-w-0 pointer-coarse:select-none"
              style={
                {
                  WebkitTouchCallout: "none",
                  // Fix 2026-08-17 (Touch-Markierung): Der Browser klassifiziert
                  // die Geste beim touchstart anhand des touch-action des
                  // Start-Elements. Die Wort-Spans haben touch-action:none
                  // (Markierung in alle Richtungen, kein pointercancel beim
                  // Ziehen über Zeilen); der Container behält pan-y, damit
                  // Scrollen über Zwischenräume/außerhalb weiter geht.
                  touchAction: "pan-y",
                } as React.CSSProperties
              }
              onMouseUp={onSplitSegment || onAnnotate ? (e) => handleTextMouseUp(i, e.currentTarget) : undefined}
              onPointerDown={onSplitSegment || onAnnotate ? (e) => handleTextPointerDown(i, e) : undefined}
              onPointerMove={onSplitSegment || onAnnotate ? (e) => handleTextPointerMove(i, e) : undefined}
              onPointerUp={onSplitSegment || onAnnotate ? () => handleTextPointerUp(i) : undefined}
              onPointerCancel={onSplitSegment || onAnnotate ? () => setTouchSel(null) : undefined}
              data-split-container
            >
              {/* Fix 2026-08-18: Wort-Spans IMMER rendern, wenn Split möglich
                  (onSplitSegment) — vorher nur bei hasConfidence ODER aktivem
                  Segment (currentTime != null). Beim ersten Laden war
                  currentTime null → nur Fließtext → keine data-word-index
                  Spans → Markieren/Split ging erst nach einem Playback-Zyklus.
                  Ohne Confidence/Playback bleibt die Optik identisch
                  (confidenceClass liefert ""). */}
              {seg.words && seg.words.length > 0 && (onSplitSegment || hasConfidence(seg.words) || (currentTime != null && i === activeIdx))
                ? (() => {
                    const activeW = i === activeIdx && currentTime != null ? activeWordIndex(seg.words, currentTime, isPlaying ? undefined : 0) : -1;
                    // Change 013 (Tablet): eigene Touch-Markierung hervorheben.
                    const ts = touchSel && touchSel.idx === i ? touchSel : null;
                    return seg.words!.map((w, wi) => {
                      const isActive = wi === activeW;
                      // Such-Treffer: grüner Marker (.search-hit) — bewusst
                      // getrennt vom gelben Karaoke-Marker (Abspielposition).
                      const isHit = wordIsHit(w.word);
                      const inTouchSel = ts
                        ? wi >= Math.min(ts.startWord, ts.endWord) && wi <= Math.max(ts.startWord, ts.endWord)
                        : false;
                      // Fix 2026-08-17: Space nach Wort wi mit markieren, wenn
                      // Wort wi UND wi+1 im Bereich liegen (lückenlose Markierung
                      // inkl. Leerzeichen).
                      const spaceInSel = ts
                        ? wi >= Math.min(ts.startWord, ts.endWord) &&
                          wi + 1 <= Math.max(ts.startWord, ts.endWord)
                        : false;
                      const cls = isHit
                        ? "search-hit"
                        : inTouchSel
                          ? "touch-sel"
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
                          data-word-index={wi}
                          // Fix 2026-08-17 (Touch): touch-action gilt laut Spec
                          // NICHT für non-replaced inline-Elemente → Wort-Span
                          // inline-block + touch-action:none. Der Browser
                          // klassifiziert die Geste beim touchstart am
                          // Start-Element: Start auf Wort = nie Scroll (kein
                          // pointercancel, auch vertikal über Zeilen);
                          // Start auf Zwischenraum = Scrollen normal.
                          style={{ display: "inline-block", touchAction: "none" } as React.CSSProperties}
                          onClick={(e) => {
                            e.stopPropagation();
                            // Fix 2026-08-18 (User-Vorgabe): Markieren darf
                            // KEIN Play auslösen — nach einer Textauswahl
                            // feuert der Browser zusätzlich ein click auf dem
                            // Start-Wort. Nur ein einfacher Klick (Selection
                            // kollabiert, kein Touch-Drag) spielt ab dem Wort.
                            const sel = window.getSelection();
                            if (sel && !sel.isCollapsed && sel.rangeCount > 0) return;
                            const ts = touchSel;
                            if (ts && ts.idx === i && ts.startWord !== ts.endWord) return;
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
                          {/* Fix 2026-08-17: Space ist ein EIGENER Span mit
                              white-space:pre (kollabiert nicht am Umbruch).
                              So lassen sich Leerzeichen MIT markieren — vorher
                              waren sie Text-Nodes ohne Klasse und die Markierung
                              sprang Wort für Wort. Konsistent: Space zwischen
                              zwei markierten Wörtern wird mit markiert. */}
                          {w.word}
                        </span>
                        {wi < seg.words!.length - 1 ? (
                          <span
                            key={`sp-${wi}`}
                            className={spaceInSel ? "touch-sel" : undefined}
                            style={{ whiteSpace: "pre" }}
                          >
                            {" "}
                          </span>
                        ) : null}
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
    {/* Feature 2026-08-16 (Edit): Split-Popover nach Klick auf das
        Split-Symbol (Change 013 — KEIN Auto-Modal mehr). Positioniert
        neben dem Symbol (links), nicht zentriert. */}
    {splitAnchor && splitPopoverOpen && onSplitSegment && (
      <>
        <div
          className="fixed inset-0 z-30"
          onClick={() => {
            setSplitAnchor(null);
            setSplitSpeakerOpen(false);
            setSplitPopoverOpen(false);
          }}
        />
        <div
          ref={splitPosRef}
          className="fixed z-40 w-[260px] max-w-[70vw] bg-panel2 border border-border rounded-md shadow-xl p-3"
          style={
            splitPos
              ? { left: splitPos.left, top: splitPos.top }
              : {
                  left: 8,
                  top: Math.min(
                    (rowRefs.current[splitAnchor.idx]?.getBoundingClientRect().top ?? 0) + splitAnchor.y,
                    window.innerHeight - 220,
                  ),
                }
          }
        >
          <div className="text-[13px] font-semibold mb-1">✂ {t("split_segment_title")}</div>
          <div className="text-[12px] text-muted2 mb-2 leading-[1.5] break-words bg-panel rounded-sm px-2 py-1.5 max-h-[70px] overflow-y-auto scrollbar-thin">
            „{splitAnchor.preview}“
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
                {abbreviateMid(
                  (splitSpeaker || shown[splitAnchor.idx]?.speaker || t("split_speaker_default")).replace("SPEAKER_", ""),
                  20,
                )}
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
                        className={`block w-full max-w-[240px] text-left px-2 py-1 text-[11px] uppercase tracking-[.04em] cursor-pointer hover:bg-accent/10 break-words ${
                          opt === (splitSpeaker || shown[splitAnchor.idx]?.speaker)
                            ? "text-[#25d366] font-bold"
                            : "text-muted1"
                        }`}
                      >
                        {opt.replace("SPEAKER_", "")}
                      </button>
                    ))}
                    {/* Feature 2026-08-18: manuell erweiterbare Speaker-Liste */}
                    <div className="border-t border-border/60 my-0.5" />
                    {newSpeakerMode === "split" ? (
                      <div className="px-2 py-1 flex items-center gap-1">
                        <input
                          autoFocus
                          value={newSpeakerName}
                          onChange={(e) => setNewSpeakerName(e.target.value)}
                          onKeyDown={(e) => {
                            e.stopPropagation();
                            if (e.key === "Enter") void handleAddNewSpeaker("split");
                            if (e.key === "Escape") {
                              setNewSpeakerMode(null);
                              setNewSpeakerName("");
                            }
                          }}
                          placeholder={t("new_speaker_placeholder")}
                          className="w-full min-w-[110px] text-[11px] bg-panel border border-border rounded-sm px-1.5 py-0.5 text-txt outline-none focus:border-accent"
                        />
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            void handleAddNewSpeaker("split");
                          }}
                          className="flex-shrink-0 text-[11px] text-accent font-semibold px-1 hover:opacity-80"
                        >
                          {t("new_speaker_save")}
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setNewSpeakerMode("split");
                          setNewSpeakerName("");
                        }}
                        className="block w-full text-left px-2 py-1 text-[11px] italic text-accent cursor-pointer hover:bg-accent/10"
                      >
                        {t("new_speaker_add")}
                      </button>
                    )}
                  </div>
                </>
              )}
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <button
              onClick={() => {
                setSplitAnchor(null);
                setSplitSpeakerOpen(false);
                setSplitPopoverOpen(false);
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
