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
    activeUsers: [],
    hasCollab: false,
    setSegmentText: () => {},
    getSegmentTexts: () => [],
    finalize: () => {},
    saving: false,
  }),
}));

vi.mock("../api", () => ({
  updateSegment: vi.fn(),
  renameSpeaker: vi.fn(),
}));

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

function renderList(onAnnotate?: (a: { idx: number; charStart: number; charEnd: number; preview: string }) => void) {
  return render(
    <LocaleProvider>
      <SegmentList
        segments={[SEG]}
        activeIdx={0}
        onActiveChange={() => {}}
        onSplitSegment={vi.fn()}
        onAnnotate={onAnnotate}
        recordingId="r1"
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
