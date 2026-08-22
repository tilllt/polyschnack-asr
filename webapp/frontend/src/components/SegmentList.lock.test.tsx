/** Change 084: SegmentList-Sperre bei fremdem Edit-Lock. */
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../hooks/useYjsTranscription", () => ({
  useYjsTranscription: vi.fn(),
}));
vi.mock("../api", () => ({
  updateSegment: vi.fn(),
  renameSpeaker: vi.fn(),
}));
vi.mock("./Toasts", () => ({ useToast: () => ({ toast: vi.fn() }) }));

import { useYjsTranscription } from "../hooks/useYjsTranscription";
import { LocaleProvider } from "../useLocale";
import { SegmentList } from "./SegmentList";

const mkSeg = (start: number, end: number, words: string[]) => ({
  start,
  end,
  text: words.join(" "),
  words: words.map((w, i) => ({ word: w, start: start + i, end: start + i + 1 })),
});

function renderList(opts: {
  editLock?: { index: number; name: string } | null;
  onBoundaryDragEnd?: () => void;
}) {
  vi.mocked(useYjsTranscription).mockReturnValue({
    conn: null,
    activeEditors: opts.editLock ? [opts.editLock.name] : [],
    editLock: opts.editLock ?? null,
    hasCollab: false,
    setSegmentText: () => {},
    getSegmentTexts: () => [],
    save: () => {},
    saving: false,
    setEditingActive: () => {},
  } as never);
  return render(
    <LocaleProvider>
      <SegmentList
        segments={[mkSeg(0, 2, ["a0", "a1"]), mkSeg(2, 4, ["b0", "b1"])]}
        activeIdx={0}
        onActiveChange={() => {}}
        onSplitSegment={vi.fn()}
        recordingId="r1"
        onSeekTo={() => {}}
        onEdited={() => {}}
        onBoundaryDragEnd={opts.onBoundaryDragEnd}
        onSegmentDelete={vi.fn()}
      />
    </LocaleProvider>,
  );
}

describe("SegmentList — Kollaborations-Lock (Change 084)", () => {
  beforeEach(() => {
    HTMLElement.prototype.scrollTo = vi.fn();
    window.getSelection()?.removeAllRanges();
  });

  it("zeigt Lock-Symbol am fremd-editierten Segment mit Namen im Tooltip", () => {
    renderList({ editLock: { index: 0, name: "Anna" } });
    const lock = screen.getByTestId("edit-lock");
    expect(lock).toBeTruthy();
    expect(lock.getAttribute("title")).toContain("Anna");
    // Nur Segment 0 ist gesperrt — kein zweites Lock.
    expect(screen.getAllByTestId("edit-lock").length).toBe(1);
  });

  it("Doppelklick auf das fremd-editierten Segment öffnet keine Edit-Box", () => {
    const { container } = renderList({ editLock: { index: 0, name: "Anna" } });
    const text = container.querySelector('[data-split-container]');
    expect(text).toBeTruthy();
    fireEvent.doubleClick(text as HTMLElement);
    expect(container.querySelector("textarea")).toBeNull();
  });

  it("Grenz-Drag ist bei fremdem Edit-Lock blockiert (kein onBoundaryDragEnd)", () => {
    const onEnd = vi.fn();
    const { container } = renderList({ editLock: { index: 0, name: "Anna" }, onBoundaryDragEnd: onEnd });
    // Timecode-Handle der Grenze vor Segment 1 — bei aktivem Lock trägt
    // er cursor-not-allowed (sprachunabhängiger Selektor).
    const handle = container.querySelector(".cursor-not-allowed") as HTMLElement;
    expect(handle).toBeTruthy();
    fireEvent.pointerDown(handle, { button: 0, clientY: 10 });
    fireEvent.pointerUp(handle, { clientY: 10 });
    expect(onEnd).not.toHaveBeenCalled();
  });

  it("Delete-Button ist bei fremdem Edit-Lock deaktiviert", () => {
    const { container } = renderList({ editLock: { index: 0, name: "Anna" } });
    const del = [...container.querySelectorAll("button")].find(
      (b) => b.textContent?.trim() === "−",
    ) as HTMLButtonElement;
    expect(del).toBeTruthy();
    expect(del.disabled).toBe(true);
  });
});
