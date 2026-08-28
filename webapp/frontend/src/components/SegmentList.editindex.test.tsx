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
  replaceSegments: vi.fn(),
}));
vi.mock("./Toasts", () => ({ useToast: () => ({ toast: vi.fn() }) }));

import { useYjsTranscription } from "../hooks/useYjsTranscription";
import { LocaleProvider } from "../useLocale";
import { SegmentList } from "./SegmentList";
import { deriveSegments } from "../resegment";
import { updateSegment, replaceSegments } from "../api";

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

function renderList(onEdited?: (segs: never, text: string) => void) {
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
        onEdited={(onEdited as never) ?? (() => {})}
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

describe("SegmentList — Edit-Save Sync (Change 139, ersetzt 129-PATCH)", () => {
  beforeEach(() => {
    HTMLElement.prototype.scrollTo = vi.fn();
    vi.mocked(updateSegment).mockReset();
    vi.mocked(replaceSegments).mockReset();
    vi.mocked(replaceSegments).mockImplementation(async (_rid, segs) => ({
      segments: segs as never,
      text: (segs as unknown as { text?: string }[]).map((s) => s.text ?? "").join(" "),
      segments_manual: true,
    } as never));
  });

  it("Anzeige teilt das Riesen-Segment in mehrere Buckets", () => {
    const { container } = renderList();
    const buckets = container.querySelectorAll("[data-split-container]");
    expect(buckets.length).toBeGreaterThan(1);
  });

  it("Edit persistiert die VOLLE Anzeige-Liste per PUT (kein PATCH mehr)", () => {
    const { container } = renderList();
    const buckets = container.querySelectorAll("[data-split-container]");
    const display = deriveSegments(serverSegs, 25) as unknown as Seg[];

    // 2. Anzeige-Bucket doppelklicken → Edit-Box öffnet sich.
    fireEvent.doubleClick(buckets[1]);
    const ta = container.querySelector("textarea");
    expect(ta).toBeTruthy();
    if (!ta) return;

    const neu = "PASSAGE-NEU";
    typeInTextarea(ta as HTMLTextAreaElement, neu);
    fireEvent.keyDown(ta as HTMLTextAreaElement, { key: "Enter", ctrlKey: true });

    // Change 139: voller Listen-PUT mit der ANZEIGE (editierter Bucket),
    // createVersion=false — KEIN updateSegment-PATCH mit Index-Mapping.
    expect(vi.mocked(updateSegment)).not.toHaveBeenCalled();
    expect(vi.mocked(replaceSegments)).toHaveBeenCalledTimes(1);
    const [rid, list, createVersion] = vi.mocked(replaceSegments).mock.calls[0];
    expect(rid).toBe("r1");
    expect(createVersion).toBe(false);
    const sent = list as unknown as Seg[];
    expect(sent[1].text).toBe(neu);
    // Rest der Anzeige unverändert mitgeschickt
    expect(sent[0].text).toBe(display[0].text);
    expect(sent[2].text).toBe(display[2].text);
  });

  it("Anzeige == Edit-Inhalt SOFORT (onEdited optimistisch, noch vor dem PUT)", () => {
    let captured: { segs: unknown; text: string } | null = null;
    const onEdited = (segs: never, text: string) => { captured = { segs, text }; };
    const { container } = renderList(onEdited);
    const buckets = container.querySelectorAll("[data-split-container]");
    fireEvent.doubleClick(buckets[1]);
    const ta = container.querySelector("textarea");
    if (!ta) return;
    typeInTextarea(ta as HTMLTextAreaElement, "PASSAGE-NEU");
    fireEvent.keyDown(ta as HTMLTextAreaElement, { key: "Enter", ctrlKey: true });

    // Der Cache-Update kam SOFORT mit dem lokalen Stand (erzwungener Sync) —
    // die Anzeige kann nie hinter dem Edit-Inhalt zurückbleiben.
    expect(captured).not.toBeNull();
    const segs = (captured as unknown as { segs: Seg[] }).segs;
    expect(segs[1].text).toBe("PASSAGE-NEU");
  });
});
