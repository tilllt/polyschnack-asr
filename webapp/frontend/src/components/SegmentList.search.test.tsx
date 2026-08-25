/** Change 124: SegmentList meldet die Anzeige-Segmente (onDisplayChange)
 *  und führt Ersetzen über den kollaborationsfähigen Schreibpfad aus
 *  (setSegmentText im Yjs-Modus statt REST an der Anzeige vorbei). */
import { render, waitFor } from "@testing-library/react";
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

function mockYjs(overrides: Record<string, unknown> = {}) {
  vi.mocked(useYjsTranscription).mockReturnValue({
    conn: "connected",
    activeEditors: [],
    editLock: null,
    hasCollab: true,
    setSegmentText: vi.fn(),
    getSegmentTexts: () => [],
    save: () => {},
    saving: false,
    setEditingActive: () => {},
    ...overrides,
  } as never);
}

function renderList(props: Record<string, unknown> = {}) {
  return render(
    <LocaleProvider>
      <SegmentList
        segments={[mkSeg(0, 2, ["a0", "a1"]), mkSeg(2, 4, ["b0", "b1"])]}
        activeIdx={0}
        onActiveChange={() => {}}
        onSplitSegment={vi.fn()}
        recordingId="r1"
        onSeekTo={() => {}}
        onEdited={vi.fn()}
        onBoundaryDragEnd={vi.fn()}
        onSegmentDelete={vi.fn()}
        {...props}
      />
    </LocaleProvider>,
  );
}

describe("SegmentList — Suche/Ersetzen (Change 124)", () => {
  beforeEach(() => {
    HTMLElement.prototype.scrollTo = vi.fn();
    mockYjs();
  });

  it("meldet die Anzeige-Segmente an onDisplayChange", () => {
    const onDisplay = vi.fn();
    renderList({ onDisplayChange: onDisplay });
    expect(onDisplay).toHaveBeenCalled();
    const shown = onDisplay.mock.calls[0][0] as { text: string }[];
    expect(shown.map((s) => s.text)).toEqual(["a0 a1", "b0 b1"]);
  });

  it("replaceRequest ersetzt im Yjs-Modus via setSegmentText (nicht REST)", async () => {
    const setSegmentText = vi.fn();
    mockYjs({ setSegmentText });
    const { rerender } = renderList();
    rerender(
      <LocaleProvider>
        <SegmentList
          segments={[mkSeg(0, 2, ["a0", "a1"]), mkSeg(2, 4, ["b0", "b1"])]}
          activeIdx={0}
          onActiveChange={() => {}}
          onSplitSegment={vi.fn()}
          recordingId="r1"
          onSeekTo={() => {}}
          onEdited={vi.fn()}
          onBoundaryDragEnd={vi.fn()}
          onSegmentDelete={vi.fn()}
          replaceRequest={{ query: "a1", replace: "Z", one: true, nonce: 1 }}
        />
      </LocaleProvider>,
    );
    await waitFor(() => {
      expect(setSegmentText).toHaveBeenCalledWith(0, "a0 Z");
    });
  });

  it("replaceRequest ersetzt im Solo-Modus via updateSegment", async () => {
    const { updateSegment } = await import("../api");
    vi.mocked(updateSegment).mockResolvedValue({ segments: [], text: "" } as never);
    mockYjs({ hasCollab: false });
    const { rerender } = renderList();
    rerender(
      <LocaleProvider>
        <SegmentList
          segments={[mkSeg(0, 2, ["a0", "a1"]), mkSeg(2, 4, ["b0", "b1"])]}
          activeIdx={0}
          onActiveChange={() => {}}
          onSplitSegment={vi.fn()}
          recordingId="r1"
          onSeekTo={() => {}}
          onEdited={vi.fn()}
          onBoundaryDragEnd={vi.fn()}
          onSegmentDelete={vi.fn()}
          replaceRequest={{ query: "a1", replace: "Z", one: true, nonce: 1 }}
        />
      </LocaleProvider>,
    );
    await waitFor(() => {
      expect(updateSegment).toHaveBeenCalledWith("r1", 0, "a0 Z");
    });
  });
});
