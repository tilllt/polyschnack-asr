/** Change 208/209 (Timing-Tab, User-Vorgaben 19.09.2026):
 *
 *  208: Der Klick auf ein Wort spielt NUR die Wortspanne (danach hält der
 *       Player an, der Cursor steht am Wortanfang) — nicht die ganze Aufnahme.
 *  209: Neben dem aktiven Wort zeigen wir die Range-Marker von n-1 und n+1.
 *       Zieht man eine Kante über einen Nachbarn, schrumpft dessen berührte
 *       Kante mit; ein Klick auf einen Nachbar-Marker macht ihn aktiv.
 *
 * Der Test rendert die Karte mit dem ECHTEN SegmentList (nur der Player ist
 * nachgebildet, mit Ref-Schnittstelle und Prop-Mitschnitt).
 */
import { forwardRef, useImperativeHandle } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";

const playRange = vi.fn();
const seekTo = vi.fn();
const seekToPaused = vi.fn();

/** Mitschnitt der Player-Props (Change 209: Nachbar-Marker, Gesten-Callbacks). */
let wsProps: any = null;

vi.mock("./WaveformPlayer", () => ({
  WaveformPlayer: forwardRef(function MockPlayer(_props: unknown, ref: unknown) {
    wsProps = _props;
    useImperativeHandle(ref as never, () => ({
      playRange,
      seekTo,
      seekToPaused,
      playPause: vi.fn(),
      getCurrentTime: () => 0,
      isPlaying: () => false,
      setPlaybackRate: vi.fn(),
      getPlaybackRate: () => 1,
    }));
    return null;
  }),
}));

vi.mock("./SegmentSearch", () => ({ SegmentSearch: () => null }));
vi.mock("./FeatureToggles", () => ({
  FeatureToggles: () => null,
  diarSensToMinDurationOff: () => undefined,
}));
vi.mock("./VersionDiff", () => ({ VersionDiff: () => null }));
vi.mock("./Toasts", () => ({ useToast: () => ({ toast: vi.fn() }) }));

vi.mock("../hooks/useYjsTranscription", () => ({
  useYjsTranscription: () => ({
    conn: null,
    activeEditors: [],
    editLock: null,
    hasCollab: false,
    setSegmentText: () => {},
    getSegmentTexts: () => [],
    save: () => {},
    saving: false,
    setEditingActive: () => {},
  }),
}));

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    fetchModelsMatrix: vi.fn().mockResolvedValue([]),
    fetchModelStatus: vi.fn().mockResolvedValue({
      vad_available: true,
      diarize_available: true,
      diar_service: "",
      asr_device: "cpu",
      downloading: {},
      download_progress: {},
    }),
    fetchTemplates: vi.fn().mockResolvedValue([]),
    fetchTargets: vi.fn().mockResolvedValue([]),
    fetchLlmEndpoints: vi.fn().mockResolvedValue([]),
    fetchExportTemplates: vi.fn().mockResolvedValue([]),
    fetchShares: vi.fn().mockResolvedValue([]),
    fetchVersions: vi.fn().mockResolvedValue([]),
    transcribeRange: vi.fn(),
    startTranscription: vi.fn(),
    createShare: vi.fn(),
    deleteShare: vi.fn(),
    fetchVersionDiff: vi.fn(),
    restoreVersion: vi.fn(),
    toggleAnonLink: vi.fn(),
    replaceSegments: vi.fn(),
    updateRecordingTitle: vi.fn(),
    updateWordTiming: vi.fn(),
  };
});

vi.mock("../hooks", () => ({
  useDelete: () => ({ mutate: vi.fn(), isPending: false }),
  useRetranscribe: () => ({ mutate: vi.fn(), isPending: false }),
  useRealign: () => ({ mutate: vi.fn(), isPending: false }),
  useRediarize: () => ({ mutate: vi.fn(), isPending: false }),
  useCancelRecording: () => ({ mutate: vi.fn(), isPending: false }),
  useNearViewport: () => ({ ref: { current: null }, near: true }),
  useRecordingDetail: () => ({ data: undefined, isLoading: false, isFetching: false }),
  detailEnabled: (s: string | undefined) =>
    s === "done" || s === "processing" || s === "queued",
  shouldPollDetail: (s: string | undefined) => s === "processing" || s === "queued",
}));

vi.mock("@tanstack/react-query", () => ({
  // handleEdited schreibt in den Cache (Aufnahmen-Liste + Detail) — die
  // Methoden müssen existieren, sonst läuft der Commit in den Rollback.
  useQueryClient: () => ({
    invalidateQueries: vi.fn(),
    setQueriesData: vi.fn(),
    setQueryData: vi.fn(),
  }),
  useQuery: () => ({ data: [], isLoading: false, isError: false, error: null }),
}));

import { updateWordTiming, type Recording } from "../api";
import { LocaleProvider } from "../useLocale";
import { RecordingCard } from "./RecordingCard";

const SEGMENTS = [
  {
    start: 0,
    end: 2,
    text: "Hallo Welt",
    words: [
      { word: "Hallo", start: 0, end: 1 },
      { word: "Welt", start: 1, end: 2 },
    ],
  },
  {
    start: 2,
    end: 4,
    text: "zweiter Satz",
    words: [
      { word: "zweiter", start: 2, end: 3 },
      { word: "Satz", start: 3, end: 4 },
    ],
  },
];

const rec = {
  id: "1",
  uid: "r1",
  original_name: "aufnahme.wav",
  mime: "audio/wav",
  size_bytes: 1000,
  duration_s: 10,
  status: "done",
  text: "Hallo Welt zweiter Satz",
  error: null,
  processing_ms: null,
  created_at: "2026-08-01T00:00:00Z",
  language: "de",
  segments: SEGMENTS,
  segments_manual: false,
  audio_url: "/api/audio/r1",
  audio_preview_url: null,
  download_url: "",
  backup_url: "",
  batch_id: null,
  recorded_at: null,
  source: null,
  enable_vad: false,
  enable_diarize: false,
  enable_streaming: false,
  enable_noise_reduce: false,
  enable_enhance: "none",
  waveform_peaks: null,
  progress_pct: 0,
  access_level: "owner",
} as unknown as Recording;

/** Karte im Timing-Tab rendern; das eine Wort ist geladen. */
async function renderTimingWithWeltLoaded() {
  render(
    <LocaleProvider>
      <RecordingCard recording={rec} compact defaultCollapsed={false} />
    </LocaleProvider>,
  );
  screen.getByTestId("editor-tab-timing").click();
  // Erst wenn der Timing-Tab wirklich aktiv ist, ist der Wortklick der
  // richtige (read-only) Pfad — sonst klickt der Test in die Transkription.
  await waitFor(() =>
    expect(screen.getByText(/Click a word to load it into the waveform/)).toBeTruthy(),
  );
  const wort = await screen.findByText("Welt");
  fireEvent.click(wort);
  // Der Klick läuft durch den 280-ms-Doppelklick-Schutz → abwarten.
  await waitFor(() => expect(playRange).toHaveBeenCalledWith(1, 2), { timeout: 2000 });
}

describe("Change 208/209: Wortklick und Nachbar-Marker im Timing-Tab", () => {
  beforeEach(() => {
    // jsdom kennt Element.scrollTo nicht — der echte SegmentList zentriert die
    // aktive Zeile damit (centerWord). Ohne Polyfill endet der Lauf mit einem
    // unbehandelten Fehler.
    HTMLElement.prototype.scrollTo = vi.fn();
    playRange.mockClear();
    seekTo.mockClear();
    seekToPaused.mockClear();
    vi.mocked(updateWordTiming).mockReset();
  });

  test("Change 208: spielt genau die Wortspanne des geklickten Wortes", async () => {
    await renderTimingWithWeltLoaded();
    // Kein „ganze Aufnahme abspielen" mehr.
    expect(seekTo).not.toHaveBeenCalled();
  });

  test("Change 209: zeigt die Range-Marker von n-1 und n+1", async () => {
    await renderTimingWithWeltLoaded();
    expect(wsProps.timingWord.segIdx).toBe(0);
    expect(wsProps.timingWord.wordIdx).toBe(1);
    expect(wsProps.timingNeighbors.prev.text).toBe("Hallo");
    expect(wsProps.timingNeighbors.next.text).toBe("zweiter"); // Segment 2
    // Zieh-Grenzen reichen bis an die RÄNDER der Nachbarn (nicht mehr bis zu
    // ihrer Innenkante) — dort schrumpfen sie mit: Vorgänger [0;1] → ab 0.02,
    // Nachfolger [2;3] → bis 2.98.
    expect(wsProps.timingWord.minStart).toBeCloseTo(0 + 0.02, 6);
    expect(wsProps.timingWord.maxEnd).toBeCloseTo(3 - 0.02, 6);
  });

  test("Change 209: Ziehen schrumpft den Nachbar-Marker live", async () => {
    await renderTimingWithWeltLoaded();
    act(() => wsProps.onTimingChange(0.5, 2));
    // Vorgänger endet jetzt am neuen Wortanfang, der Nachfolger bleibt.
    expect(wsProps.timingNeighbors.prev.end).toBeCloseTo(0.5, 6);
    expect(wsProps.timingNeighbors.next.start).toBeCloseTo(2, 6);
    // Zurückziehen stellt den alten Rand wieder her (Rechnung aus dem
    // Ausgangsstand, nicht aus dem geschrumpften Zwischenstand).
    act(() => wsProps.onTimingChange(1, 2));
    expect(wsProps.timingNeighbors.prev.end).toBeCloseTo(1, 6);
    // GANZE Markierung ziehen (Körper-Zug: start UND end wandern) → nach
    // rechts rückt der Nachfolger nach, der Vorgänger bleibt stehen.
    act(() => wsProps.onTimingChange(1.5, 2.5));
    expect(wsProps.timingNeighbors.next.start).toBeCloseTo(2.5, 6);
    expect(wsProps.timingNeighbors.prev.end).toBeCloseTo(1, 6);
  });

  test("Change 209: Speichern schickt shrink_neighbors und übernimmt die Antwort", async () => {
    await renderTimingWithWeltLoaded();
    const shrunk = JSON.parse(JSON.stringify(SEGMENTS));
    shrunk[0].words[0].end = 0.5;
    shrunk[0].words[0].override = true;
    vi.mocked(updateWordTiming).mockResolvedValue({ segments: shrunk, text: "x" });

    await act(async () => {
      await wsProps.onTimingCommit(0.5, 2);
    });

    expect(vi.mocked(updateWordTiming)).toHaveBeenCalledWith("r1", 0, 1, {
      start: 0.5,
      end: 2,
      shrink_neighbors: true,
    });
    // Die Anzeige folgt dem Server (der Vorgänger ist geschrumpft).
    expect(wsProps.timingNeighbors.prev.end).toBeCloseTo(0.5, 6);
  });

  test("Change 209: Klick auf einen Nachbar-Marker macht ihn aktiv", async () => {
    await renderTimingWithWeltLoaded();
    await act(async () => {
      wsProps.onTimingSelectWord(1, 0); // „zweiter"
    });
    expect(wsProps.timingWord.segIdx).toBe(1);
    expect(wsProps.timingWord.wordIdx).toBe(0);
    expect(playRange).toHaveBeenLastCalledWith(2, 3);
    // Seine Nachbarn sind jetzt „Welt" (davor) und „Satz" (danach).
    expect(wsProps.timingNeighbors.prev.text).toBe("Welt");
    expect(wsProps.timingNeighbors.next.text).toBe("Satz");
  });
});
