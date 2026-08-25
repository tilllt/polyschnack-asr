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
  replaceSegments: vi.fn(),
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
    vi.clearAllMocks(); // Call-Zähler pro Test frisch (Vitest kumuliert sonst)
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

  it("replaceRequest ersetzt im Solo-Modus via replaceSegments (PUT, volle Liste)", async () => {
    const { replaceSegments, updateSegment } = await import("../api");
    vi.mocked(replaceSegments).mockResolvedValue({ segments: [], text: "" } as never);
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
      // Change 125: KEIN PATCH mit Anzeige-Index gegen das Original-Array
      // (404 bei Re-Segmentierung) — ein PUT mit der kompletten Liste.
      expect(replaceSegments).toHaveBeenCalledWith(
        "r1",
        expect.arrayContaining([expect.objectContaining({ text: "a0 Z" })]),
        false,
      );
      expect(updateSegment).not.toHaveBeenCalled();
    });
  });

  it("ersetzt bei re-segmentierter Anzeige (Treffer-Index > Original-Länge) mit genau einem PUT", async () => {
    const { replaceSegments, updateSegment } = await import("../api");
    vi.mocked(replaceSegments).mockResolvedValue({ segments: [], text: "" } as never);
    mockYjs({ hasCollab: false });
    // 5 Anzeige-Segmente (re-segmentiert) — Treffer im letzten (Index 4)
    const segs = [
      mkSeg(0, 1, ["x0"]),
      mkSeg(1, 2, ["x1"]),
      mkSeg(2, 3, ["x2"]),
      mkSeg(3, 4, ["x3"]),
      mkSeg(4, 6, ["ziel", "x4"]),
    ];
    const { rerender } = renderList({ segments: segs });
    rerender(
      <LocaleProvider>
        <SegmentList
          segments={segs}
          activeIdx={0}
          onActiveChange={() => {}}
          onSplitSegment={vi.fn()}
          recordingId="r1"
          onSeekTo={() => {}}
          onEdited={vi.fn()}
          onBoundaryDragEnd={vi.fn()}
          onSegmentDelete={vi.fn()}
          replaceRequest={{ query: "ziel", replace: "Y", one: true, nonce: 1 }}
        />
      </LocaleProvider>,
    );
    await waitFor(() => {
      expect(replaceSegments).toHaveBeenCalledTimes(1);
      expect(updateSegment).not.toHaveBeenCalled();
      const sent = vi.mocked(replaceSegments).mock.calls[0][1] as { text: string }[];
      expect(sent).toHaveLength(5);
      expect(sent[4].text).toBe("Y x4");
    });
  });
});
