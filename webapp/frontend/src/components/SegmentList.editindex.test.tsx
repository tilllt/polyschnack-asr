/** Change 129: Edit-Save trifft das richtige Server-Segment.
 *
 * Real-Fall 2026-08-25: Die Anzeige re-segmentiert lange ASR-Segmente in
 * 25-s-Buckets (deriveSegments). handleSave sendete PATCH /segments/{idx}
 * mit dem ANZEIGE-Index — ab dem ersten Split traf der Edit das falsche
 * Server-Segment (Textverlust inkl. Passage im Teamtreffen).
 */
import { fireEvent, render } from "@testing-library/react";
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
import { deriveSegments } from "../resegment";
import { updateSegment } from "../api";

type W = { word: string; start: number; end: number };
type Seg = { start: number; end: number; text: string; words: W[] };

// Server-Wahrheit: EIN Riesen-Segment 0–84 s (24 Wörter à ~3,5 s) —
// die Anzeige teilt es in 25-s-Buckets (4 Stücke).
const words: W[] = Array.from({ length: 24 }, (_, i) => ({
  word: `w${i}`,
  start: Math.round(i * 3.5 * 10) / 10,
  end: Math.round(i * 3.5 * 10) / 10 + 1,
}));
const serverSegs: Seg[] = [
  { start: 0, end: 84, text: words.map((w) => w.word).join(" "), words },
];

function renderList() {
  const display = deriveSegments(serverSegs, 25) as unknown as Seg[];
  vi.mocked(useYjsTranscription).mockReturnValue({
    conn: null,
    activeEditors: [],
    editLock: null,
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
        segments={display}
        persistBase={serverSegs}
        activeIdx={0}
        onActiveChange={() => {}}
        onSplitSegment={vi.fn()}
        recordingId="r1"
        onSeekTo={() => {}}
        onEdited={() => {}}
        onBoundaryDragEnd={() => {}}
        onSegmentDelete={vi.fn()}
      />
    </LocaleProvider>,
  );
}

function typeInTextarea(ta: HTMLTextAreaElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(
    window.HTMLTextAreaElement.prototype,
    "value",
  )!.set!;
  setter.call(ta, value);
  fireEvent.input(ta, { target: { value } });
}

describe("SegmentList — Edit-Save Server-Index (Change 129)", () => {
  beforeEach(() => {
    HTMLElement.prototype.scrollTo = vi.fn();
    vi.mocked(updateSegment).mockReset();
    vi.mocked(updateSegment).mockResolvedValue({
      segments: serverSegs,
      text: serverSegs[0].text,
    } as never);
  });

  it("Anzeige teilt das Riesen-Segment in mehrere Buckets", () => {
    const { container } = renderList();
    const buckets = container.querySelectorAll("[data-split-container]");
    expect(buckets.length).toBeGreaterThan(1);
  });

  it("Edit im 2. Bucket patcht das SERVER-Segment 0 mit dem vollständigen Text", () => {
    const { container } = renderList();
    const buckets = container.querySelectorAll("[data-split-container]");
    const display = deriveSegments(serverSegs, 25) as unknown as Seg[];

    // 2. Anzeige-Bucket (die Passage) doppelklicken → Edit-Box öffnet sich.
    fireEvent.doubleClick(buckets[1]);
    const ta = container.querySelector("textarea");
    expect(ta).toBeTruthy();
    if (!ta) return;

    const neu = "PASSAGE-NEU";
    typeInTextarea(ta as HTMLTextAreaElement, neu);
    fireEvent.keyDown(ta as HTMLTextAreaElement, { key: "Enter", ctrlKey: true });

    // Erwartung: Server-Index 0 (nicht Anzeige-Index 1) + vollständiger
    // Server-Segment-Text = alle Buckets, das editierte ersetzt.
    const expected = [
      display[0].text,
      neu,
      display[2].text,
      display[3].text,
    ].join(" ");
    expect(vi.mocked(updateSegment)).toHaveBeenCalledTimes(1);
    expect(vi.mocked(updateSegment).mock.calls[0][0]).toBe("r1");
    expect(vi.mocked(updateSegment).mock.calls[0][1]).toBe(0); // Server-Index!
    expect(vi.mocked(updateSegment).mock.calls[0][2]).toBe(expected);
  });
});
