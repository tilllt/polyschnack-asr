/** Change 208 (User-Vorgabe 19.09.2026): Im Timing-Tab spielt der Klick auf ein
 *  Wort NUR die Wortspanne (danach hält der Player an, der Cursor steht am
 *  Wortanfang) — er startet nicht die ganze Aufnahme.
 *
 *  Der Test rendert die Karte mit dem ECHTEN SegmentList (nur der Player ist
 *  nachgebildet) und klickt ein Wort im Timing-Tab.
 */
import { forwardRef, useImperativeHandle } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";

const playRange = vi.fn();
const seekTo = vi.fn();
const seekToPaused = vi.fn();

vi.mock("./WaveformPlayer", () => ({
  WaveformPlayer: forwardRef(function MockPlayer(_props: unknown, ref: unknown) {
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
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  useQuery: () => ({ data: [], isLoading: false, isError: false, error: null }),
}));

import type { Recording } from "../api";
import { LocaleProvider } from "../useLocale";
import { RecordingCard } from "./RecordingCard";

const rec = {
  id: "1",
  uid: "r1",
  original_name: "aufnahme.wav",
  mime: "audio/wav",
  size_bytes: 1000,
  duration_s: 10,
  status: "done",
  text: "Hallo Welt",
  error: null,
  processing_ms: null,
  created_at: "2026-08-01T00:00:00Z",
  language: "de",
  segments: [
    {
      start: 0,
      end: 2,
      text: "Hallo Welt",
      words: [
        { word: "Hallo", start: 0, end: 1 },
        { word: "Welt", start: 1, end: 2 },
      ],
    },
  ],
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

describe("Change 208: Wortklick im Timing-Tab", () => {
  beforeEach(() => {
    playRange.mockClear();
    seekTo.mockClear();
    seekToPaused.mockClear();
  });

  test("spielt genau die Wortspanne des geklickten Wortes", async () => {
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
    // Kein „ganze Aufnahme abspielen" mehr.
    expect(seekTo).not.toHaveBeenCalled();
  });
});
