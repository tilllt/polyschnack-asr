/** Change 137: TimingEditor (Timing-Tab) — Wortliste read-only, Klick lädt
 *  das Wort, Kopfzeile zeigt Start/Ende/Länge + Override + Reset. */
import { fireEvent, render, waitFor } from "@testing-library/react";
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
import { TimingEditor } from "./TimingEditor";

type W = { word: string; start: number; end: number; override?: boolean };
type Seg = { start: number; end: number; text: string; words: W[]; speaker?: string };

const words: W[] = [
  { word: "Hallo", start: 0.0, end: 1.0 },
  { word: "Welt", start: 1.0, end: 2.0 },
  { word: "zweiter", start: 2.0, end: 3.0 },
  { word: "Satz", start: 3.0, end: 4.0, override: true },
];
const segs: Seg[] = [
  { start: 0, end: 2, text: "Hallo Welt", words: words.slice(0, 2), speaker: "SPEAKER_00" },
  { start: 2, end: 4, text: "zweiter Satz", words: words.slice(2), speaker: "SPEAKER_01" },
];

function renderEditor(props: Partial<Parameters<typeof TimingEditor>[0]> = {}) {
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
      <TimingEditor
        segments={segs as never}
        activeIdx={-1}
        onActiveChange={() => {}}
        onWordClick={vi.fn()}
        {...props}
      />
    </LocaleProvider>,
  );
}

describe("TimingEditor (Change 137)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("ohne geladenes Wort: Hinweis statt Timing-Kopfzeile", () => {
    const { getByText } = renderEditor();
    // Default-Locale = en (LocaleProvider) → echter Text, 💡-Präfix → Regex
    expect(getByText(/Click a word to load it into the waveform/)).toBeTruthy();
  });

  it("mit geladenem Wort: Start/Ende/Länge + Worttext sichtbar", () => {
    const { getByText } = renderEditor({
      timing: { segIdx: 0, wordIdx: 1, start: 1.2, end: 1.9 },
      override: true,
    });
    expect(getByText(/„Welt"/)).toBeTruthy();
    // Zeitcodes folgen dem Label im selben Span → Regex über den Text
    expect(getByText(/Start/)).toBeTruthy();
    expect(getByText(/End/)).toBeTruthy();
    expect(getByText(/Length/)).toBeTruthy();
  });

  it("Override-Badge + Reset-Button nur bei override=true", () => {
    const onReset = vi.fn();
    const { getByText, queryByText, rerender } = renderEditor({
      timing: { segIdx: 0, wordIdx: 1, start: 1.2, end: 1.9 },
      override: true,
      onResetOverride: onReset,
    });
    const reset = getByText("Reset to alignment");
    fireEvent.click(reset);
    expect(onReset).toHaveBeenCalledTimes(1);

    rerender(
      <LocaleProvider>
        <TimingEditor
          segments={segs as never}
          activeIdx={-1}
          onActiveChange={() => {}}
          onWordClick={vi.fn()}
          timing={{ segIdx: 0, wordIdx: 1, start: 1.2, end: 1.9 }}
          override={false}
          onResetOverride={onReset}
        />
      </LocaleProvider>,
    );
    expect(queryByText("Reset to alignment")).toBeNull();
  });

  it("Wort-Klick ruft onWordClick(segIdx, wordIdx) — readOnly-Modus", async () => {
    const onWordClick = vi.fn();
    const { getByText } = renderEditor({ onWordClick });
    fireEvent.click(getByText("Hallo"));
    // Change 091: Wort-Klick läuft durch den 280-ms-Doppelklick-Schutz
    // (scheduleClick) → asynchron.
    await waitFor(() => expect(onWordClick).toHaveBeenCalledWith(0, 0));
    fireEvent.click(getByText("Satz"));
    await waitFor(() => expect(onWordClick).toHaveBeenCalledWith(1, 1));
  });

  it("readOnly: kein Sprecher-Rename-Stift sichtbar", () => {
    const { queryByLabelText } = renderEditor();
    // Das ✎-Icon hat aria-label rename_speaker_placeholder (i18n-Fallback)
    expect(queryByLabelText("rename_speaker_placeholder")).toBeNull();
  });
});
