/**
 * Change 056 — Kontext-Leiste in SegmentList: Text-Markierung → 💬 Annotate
 * (neben dem Split-Symbol). Simuliert eine echte Browser-Selektion über den
 * Wort-Spans (data-word-index) + mouseup auf dem Split-Container.
 */
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, beforeAll } from "vitest";
import { LocaleProvider } from "../useLocale";

// jsdom 25 hat kein window.PointerEvent — fireEvent.pointerDown erzeugt
// dann ein generisches Event OHNE pointerType, und die Touch-Handler
// (handleTextPointerDown: `e.pointerType !== "touch" → return`) feuern
// nie. Echte Browser haben PointerEvent immer; hier minimal polyfillen,
// damit die Touch-Pointer-Tests die Realität abbilden.
beforeAll(() => {
  if (typeof window.PointerEvent === "undefined") {
    class PointerEventPolyfill extends MouseEvent {
      pointerType: string;
      isPrimary: boolean;
      constructor(type: string, params: PointerEventInit = {}) {
        super(type, params);
        this.pointerType = params.pointerType ?? "mouse";
        this.isPrimary = params.isPrimary ?? true;
      }
    }
    (window as unknown as { PointerEvent: typeof PointerEvent }).PointerEvent =
      PointerEventPolyfill as unknown as typeof PointerEvent;
  }
});

vi.mock("../hooks/useYjsTranscription", () => ({
  useYjsTranscription: () => ({
    conn: null,
    activeEditors: [],
    hasCollab: false,
    setSegmentText: () => {},
    getSegmentTexts: () => [],
    save: () => {},
    saving: false,
    setEditingActive: () => {},
  }),
}));

vi.mock("../api", () => ({
  updateSegment: vi.fn(),
  renameSpeaker: vi.fn(),
  // Change 139: Text-Edit persistiert jetzt die volle Anzeige-Liste (PUT).
  replaceSegments: vi.fn(async (_rid: string, segs: never[]) => ({
    segments: segs,
    text: (segs as unknown as { text?: string }[]).map((s) => s.text ?? "").join(" "),
    segments_manual: true,
  })),
}));

import { updateSegment, replaceSegments } from "../api";

vi.mock("./Toasts", () => ({ useToast: () => ({ toast: vi.fn() }) }));

// Karaoke-Abhängigkeiten sind pure Funktionen — bleiben real.

import { SegmentList } from "./SegmentList";

const SEG = {
  start: 0,
  end: 2,
  text: "Hallo Welt",
  words: [
    { word: "Hallo", start: 0, end: 1 },
    { word: "Welt", start: 1, end: 2 },
  ],
};

function renderList(onAnnotate?: (a: { idx: number; charStart: number; charEnd: number; preview: string }) => void, opts: { onSeekTo?: (s: number) => void; onEdited?: (segments: unknown[], text: string) => void } = {}) {
  return render(
    <LocaleProvider>
      <SegmentList
        segments={[SEG]}
        activeIdx={0}
        onActiveChange={() => {}}
        onSplitSegment={vi.fn()}
        onAnnotate={onAnnotate}
        recordingId="r1"
        onSeekTo={opts.onSeekTo}
        onEdited={opts.onEdited}
      />
    </LocaleProvider>,
  );
}

function selectWord(container: HTMLElement, wi: number) {
  const spans = container.querySelectorAll(`[data-word-index="${wi}"]`);
  expect(spans.length).toBeGreaterThan(0);
  const span = spans[0];
  const text = span.textContent ?? "";
  const range = document.createRange();
  range.setStart(span.firstChild!, 0);
  range.setEnd(span.firstChild!, text.length);
  const sel = window.getSelection();
  sel?.removeAllRanges();
  sel?.addRange(range);
  fireEvent.mouseUp(container);
}

describe("SegmentList — Kontext-Leiste (Change 056)", () => {
  beforeEach(() => {
    window.getSelection()?.removeAllRanges();
    // jsdom: HTMLDivElement hat kein scrollTo (Auto-Scroll-Effekt Z. 249)
    HTMLElement.prototype.scrollTo = vi.fn();
  });

  it("zeigt 💬 Annotate neben dem Split-Symbol nach einer Markierung", () => {
    const { container } = renderList(vi.fn());
    const splitContainer = container.querySelector("[data-split-container]") as HTMLElement;
    expect(splitContainer).toBeTruthy();
    selectWord(splitContainer, 0);
    expect(screen.getByTestId("annotate-btn")).toBeTruthy();
    expect(screen.getByTestId("split-anchor-btn")).toBeTruthy();
  });

  it("liefert Markierungs-Koordinaten + Vorschau an onAnnotate", () => {
    const onAnnotate = vi.fn();
    const { container } = renderList(onAnnotate);
    const splitContainer = container.querySelector("[data-split-container]") as HTMLElement;
    selectWord(splitContainer, 0);
    fireEvent.click(screen.getByTestId("annotate-btn"));
    expect(onAnnotate).toHaveBeenCalledWith({
      idx: 0,
      charStart: 0,
      charEnd: 5,
      preview: "Hallo",
    });
  });

  it("rückt den Anker nach Klick (Symbol verschwindet)", () => {
    const { container } = renderList(vi.fn());
    const splitContainer = container.querySelector("[data-split-container]") as HTMLElement;
    selectWord(splitContainer, 0);
    expect(screen.getByTestId("annotate-btn")).toBeTruthy();
    fireEvent.click(screen.getByTestId("annotate-btn"));
    expect(screen.queryByTestId("annotate-btn")).toBeNull();
  });
});

describe("SegmentList — Change 077 Fixes", () => {
  beforeEach(() => {
    window.getSelection()?.removeAllRanges();
    HTMLElement.prototype.scrollTo = vi.fn();
  });

  it("Edit-Save zeigt den neuen Text SOFORT (Anzeige == Edit-Inhalt, Change 139)", async () => {
    const onEdited = vi.fn();
    const { container } = renderList(undefined, { onEdited });
    const row = container.querySelector("[role=button]") as HTMLElement;
    // Doppelklick → Edit-Mode öffnen
    fireEvent.doubleClick(row);
    const ta = container.querySelector("textarea") as HTMLTextAreaElement;
    expect(ta).toBeTruthy();
    // Text ändern + speichern (Ctrl+Enter)
    fireEvent.change(ta, { target: { value: "Hallo Welt 2" } });
    expect(ta.value).toBe("Hallo Welt 2"); // Debug: change wirkt?
    vi.mocked(updateSegment).mockResolvedValue({
      segments: [{ ...SEG, text: "Hallo Welt 2" }],
      text: "Hallo Welt 2",
    });
    fireEvent.keyDown(ta, { key: "Enter", ctrlKey: true });
    await vi.waitFor(() => expect(vi.mocked(replaceSegments)).toHaveBeenCalled());
    // Debug: Was geschah? (onEdited-Aufrufe, Fehlerpfad)
    expect(onEdited).toHaveBeenCalled();
    const first = onEdited.mock.calls[0]?.[0] as { text: string }[] | undefined;
    expect(first?.[0]?.text).toBe("Hallo Welt 2");
    await vi.waitFor(() => {
      // Change 139: Edit wird SOFORT geschlossen, die ANZEIGE (Segment-Text
      // als Wort-Spans) zeigt den neuen Text — ohne auf die API-Antwort zu
      // warten (der alte Bug: Edit-Ende → alte Version sichtbar).
      const sc = container.querySelector("[data-split-container]");
      const shown = sc?.textContent?.replace(/\s+/g, " ").trim() ?? "";
      expect(shown).toContain("Hallo Welt 2");
    });
  });

  it("Doppelklick setzt den Cursor an die Wort-Position (setSelectionRange)", () => {
    const { container } = renderList(undefined, { onEdited: vi.fn() });
    const splitContainer = container.querySelector("[data-split-container]") as HTMLElement;
    // Wort 1 („Welt") selektieren wie der Browser beim Doppelklick
    const spans = splitContainer.querySelectorAll("[data-word-index]");
    const span = spans[1] as HTMLElement;
    const range = document.createRange();
    range.setStart(span.firstChild!, 0);
    range.setEnd(span.firstChild!, span.textContent!.length);
    const sel = window.getSelection();
    sel?.removeAllRanges();
    sel?.addRange(range);
    const row = container.querySelector("[role=button]") as HTMLElement;
    fireEvent.doubleClick(row);
    const ta = container.querySelector("textarea") as HTMLTextAreaElement;
    expect(ta.selectionStart).toBe(6); // „Hallo " = 6 Zeichen
    expect(ta.selectionEnd).toBe(10);  // „Welt" = 4 Zeichen
  });

  it("einfacher Klick räumt Markierung auf und startet Playback (Change 091)", async () => {
    const onSeekTo = vi.fn();
    const { container } = renderList(undefined, { onSeekTo });
    const splitContainer = container.querySelector("[data-split-container]") as HTMLElement;
    // „Alte“ Markierung: native Selection über beide Wörter (kein Drag davor)
    const spans = splitContainer.querySelectorAll("[data-word-index]");
    const range = document.createRange();
    range.setStart(spans[0].firstChild!, 0);
    range.setEnd(spans[1].firstChild!, 4);
    const sel = window.getSelection();
    sel?.removeAllRanges();
    sel?.addRange(range);
    // Einfacher Klick auf die Zeile → Markierung weg + Playback startet
    const row = container.querySelector("[role=button]") as HTMLElement;
    fireEvent.click(row);
    // await (Fix 2026-08-29): ohne await läuft das Promise nach Testende
    // weiter und timeoutet als unhandled error im nachfolgenden Test.
    await vi.waitFor(() => {
      expect(onSeekTo).toHaveBeenCalled();
      expect(sel?.isCollapsed).toBe(true);
    });
  });

  it("Klick direkt nach einem Text-Drag behält die Markierung, kein Playback (Change 091)", () => {
    const onSeekTo = vi.fn();
    const { container } = renderList(undefined, { onSeekTo });
    const splitContainer = container.querySelector("[data-split-container]") as HTMLElement;
    // Teil-Selektion (nur „Welt“) — kein voller Segment-Umfang
    const span = splitContainer.querySelectorAll("[data-word-index]")[1] as HTMLElement;
    const range = document.createRange();
    range.setStart(span.firstChild!, 0);
    range.setEnd(span.firstChild!, 4);
    const sel = window.getSelection();
    sel?.removeAllRanges();
    sel?.addRange(range);
    // MouseUp = Drag-Ende → Anker + dragMadeRef (500 ms)
    fireEvent.mouseUp(splitContainer);
    // Der auf den Drag folgende Klick (Browser feuert ihn nach dem Loslassen)
    const row = container.querySelector("[role=button]") as HTMLElement;
    fireEvent.click(row);
    vi.waitFor(() => {
      expect(onSeekTo).not.toHaveBeenCalled();
    });
    // Markierung bleibt sichtbar (nicht kollabiert) — Split/Annotate möglich
    expect(sel?.isCollapsed).toBe(false);
  });

  // Change 077-Fix (Mobile 2026-08-21): iOS/Android feuern bei Touch kein
  // onDoubleClick, und die native Wort-Selektion gibt es dort nicht
  // (user-select:none). Der Edit-Einstieg läuft deshalb über den
  // Doppeltap-Detektor (2 Taps auf dasselbe Wort ≤ 350 ms) — dieser Test
  // simuliert den Touch-Pfad über Pointer-Events mit pointerType touch.
  it("Touch: Doppeltap auf ein Wort öffnet den Edit-Modus mit Cursor am Wort", () => {
    const { container } = renderList(undefined, { onEdited: vi.fn() });
    const spans = container.querySelectorAll("[data-word-index]");
    const w1 = spans[1] as HTMLElement; // „Welt" (Char 6–10)
    // Zwei Taps auf dasselbe Wort (Pointer-Events wie ein echter Touch)
    fireEvent.pointerDown(w1, { pointerType: "touch" });
    fireEvent.pointerUp(w1, { pointerType: "touch" });
    fireEvent.pointerDown(w1, { pointerType: "touch" });
    fireEvent.pointerUp(w1, { pointerType: "touch" });
    const ta = container.querySelector("textarea") as HTMLTextAreaElement;
    expect(ta).toBeTruthy();
    // Cursor an der Doppeltap-Stelle („Hallo " = 6, „Welt" = 4)
    expect(ta.selectionStart).toBe(6);
    expect(ta.selectionEnd).toBe(10);
  });

  it("Touch: einfacher Tap startet KEINEN Edit-Modus", () => {
    const { container } = renderList(undefined, { onEdited: vi.fn() });
    const spans = container.querySelectorAll("[data-word-index]");
    const w1 = spans[1] as HTMLElement;
    fireEvent.pointerDown(w1, { pointerType: "touch" });
    fireEvent.pointerUp(w1, { pointerType: "touch" });
    expect(container.querySelector("textarea")).toBeNull();
  });

  it("Touch: Doppeltap auf VERSCHIEDENE Wörter startet KEINEN Edit-Modus", () => {
    const { container } = renderList(undefined, { onEdited: vi.fn() });
    const spans = container.querySelectorAll("[data-word-index]");
    const w0 = spans[0] as HTMLElement; // „Hallo"
    const w1 = spans[1] as HTMLElement; // „Welt"
    fireEvent.pointerDown(w0, { pointerType: "touch" });
    fireEvent.pointerUp(w0, { pointerType: "touch" });
    fireEvent.pointerDown(w1, { pointerType: "touch" });
    fireEvent.pointerUp(w1, { pointerType: "touch" });
    expect(container.querySelector("textarea")).toBeNull();
  });

  // ── Change 153: Timing-Tab (readOnly) — native Textmarkierung hat Vorrang ──
  // TimingEditor rendert SegmentList OHNE Split/Annotate-Handler (nur
  // readOnly + onWordClick). Dort darf die Klick-Logik eine frische
  // System-Markierung nicht wegwischen und kein Wort/Seek auslösen.
  function renderTimingList(opts: {
    onSeekTo?: (s: number) => void;
    onWordClick?: (s: number, w: number) => void;
    onActiveChange?: (i: number) => void;
  } = {}) {
    return render(
      <LocaleProvider>
        <SegmentList
          segments={[SEG]}
          activeIdx={0}
          onActiveChange={opts.onActiveChange ?? (() => {})}
          recordingId="r1"
          onSeekTo={opts.onSeekTo}
          readOnly
          onWordClick={opts.onWordClick}
        />
      </LocaleProvider>,
    );
  }

  it("Timing: Markierung + Zeilen-Klick → Markierung bleibt, kein Seek, kein Zeilenwechsel (Change 153)", async () => {
    const onSeekTo = vi.fn();
    const onActiveChange = vi.fn();
    const { container } = renderTimingList({ onSeekTo, onActiveChange });
    const splitContainer = container.querySelector("[data-split-container]") as HTMLElement;
    // Native Markierung über beide Wörter (wie ein System-Drag)
    const spans = splitContainer.querySelectorAll("[data-word-index]");
    const range = document.createRange();
    range.setStart(spans[0].firstChild!, 0);
    range.setEnd(spans[1].firstChild!, 4);
    const sel = window.getSelection();
    sel?.removeAllRanges();
    sel?.addRange(range);
    // Klick auf die Zeile — der 280-ms-Timer (scheduleClick) darf NICHTS tun
    const row = container.querySelector("[role=button]") as HTMLElement;
    fireEvent.click(row);
    await new Promise((r) => setTimeout(r, 450));
    expect(onSeekTo).not.toHaveBeenCalled();
    expect(onActiveChange).not.toHaveBeenCalled();
    // Markierung bleibt für System-Kopieren (Ctrl+C) erhalten
    expect(sel?.isCollapsed).toBe(false);
    expect(sel?.rangeCount).toBeGreaterThan(0);
  });

  it("Timing: Markierung + Wort-Klick → kein Waveform-Load (Change 153)", async () => {
    const onWordClick = vi.fn();
    const { container } = renderTimingList({ onWordClick });
    const splitContainer = container.querySelector("[data-split-container]") as HTMLElement;
    // Teil-Markierung (nur „Welt")
    const span = splitContainer.querySelectorAll("[data-word-index]")[1] as HTMLElement;
    const range = document.createRange();
    range.setStart(span.firstChild!, 0);
    range.setEnd(span.firstChild!, 4);
    const sel = window.getSelection();
    sel?.removeAllRanges();
    sel?.addRange(range);
    // Der Klick, der beim Loslassen der Markier-Geste entsteht
    fireEvent.click(span);
    await new Promise((r) => setTimeout(r, 450));
    expect(onWordClick).not.toHaveBeenCalled();
    expect(sel?.isCollapsed).toBe(false);
  });

  it("Timing: Klick OHNE Markierung → Seek weiterhin (Regression Change 153)", async () => {
    const onSeekTo = vi.fn();
    const { container } = renderTimingList({ onSeekTo });
    const row = container.querySelector("[role=button]") as HTMLElement;
    fireEvent.click(row);
    await vi.waitFor(() => expect(onSeekTo).toHaveBeenCalled());
  });

  it("Timing: Wort-Klick OHNE Markierung → lädt das Wort in die Waveform (Regression Change 153)", async () => {
    const onWordClick = vi.fn();
    const { container } = renderTimingList({ onWordClick });
    const span = container.querySelectorAll("[data-word-index]")[0] as HTMLElement;
    fireEvent.click(span);
    await vi.waitFor(() => expect(onWordClick).toHaveBeenCalledWith(0, 0));
  });
});
