/**
 * Change 056 — Kontext-Leiste in SegmentList: Text-Markierung → 💬 Annotate
 * (neben dem Split-Symbol). Simuliert eine echte Browser-Selektion über den
 * Wort-Spans (data-word-index) + mouseup auf dem Split-Container.
 */
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { LocaleProvider } from "../useLocale";

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
}));

import { updateSegment } from "../api";

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

  it("Edit-Save zeigt den neuen Text SOFORT (optimistisches localTexts-Update)", async () => {
    const onEdited = vi.fn();
    const { container } = renderList(undefined, { onEdited });
    const row = container.querySelector("[role=button]") as HTMLElement;
    // Doppelklick → Edit-Mode öffnen
    fireEvent.doubleClick(row);
    const ta = container.querySelector("textarea") as HTMLTextAreaElement;
    expect(ta).toBeTruthy();
    // Text ändern + speichern (Ctrl+Enter)
    fireEvent.change(ta, { target: { value: "Hallo Welt 2" } });
    vi.mocked(updateSegment).mockResolvedValue({
      segments: [{ ...SEG, text: "Hallo Welt 2" }],
      text: "Hallo Welt 2",
    });
    fireEvent.keyDown(ta, { key: "Enter", ctrlKey: true });
    await vi.waitFor(() => {
      // Anzeige (Span) zeigt sofort den neuen Text — ohne auf die
      // API-Antwort zu warten (der alte Bug: alter Text bis Roundtrip).
      expect(screen.getByText("Hallo Welt 2")).toBeTruthy();
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

  it("aktive Text-Markierung startet KEIN Playback (Zeilen-Klick-Guard)", () => {
    const onSeekTo = vi.fn();
    const { container } = renderList(undefined, { onSeekTo });
    const splitContainer = container.querySelector("[data-split-container]") as HTMLElement;
    // Markierung über 2 Wörter simulieren (nicht kollabierte Selection)
    const spans = splitContainer.querySelectorAll("[data-word-index]");
    const range = document.createRange();
    range.setStart(spans[0].firstChild!, 0);
    range.setEnd(spans[1].firstChild!, 4);
    const sel = window.getSelection();
    sel?.removeAllRanges();
    sel?.addRange(range);
    // Zeilen-Klick (role=button) — der 280-ms-Timer feuert handleClick;
    // mit aktiver Selection muss das Playback ausbleiben.
    const row = container.querySelector("[role=button]") as HTMLElement;
    fireEvent.click(row);
    vi.waitFor(() => {
      expect(onSeekTo).not.toHaveBeenCalled();
    });
  });
});
