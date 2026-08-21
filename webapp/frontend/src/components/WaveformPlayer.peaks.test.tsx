import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, act } from "@testing-library/react";
import { LocaleProvider } from "../useLocale";
import { WaveformPlayer } from "./WaveformPlayer";

/**
 * Change 059-Fix (User-Befund 2026-08-21): Seit der lite-Liste (059)
 * kommen die waveform_peaks ASYNCHRON über den Detail-Fetch nach. Der
 * WaveSurfer-Init-Effekt muss bei peaks-Änderung NEU laufen — sonst
 * startet der Player mit peaks=null (Browser-Decode der ganzen Datei)
 * und bleibt auf langsamen Verbindungen ewig in „Loading waveform…".
 */

// ── WaveSurfer-Mock ─────────────────────────────────────────────────────
const createMock = vi.fn();
const loadMock = vi.fn();
const onMock = vi.fn();
const destroyMock = vi.fn();
const getDurationMock = vi.fn(() => 0);
const getCurrentTimeMock = vi.fn(() => 0);
const isPlayingMock = vi.fn(() => false);
const getDecodedDataMock = vi.fn(() => null);
const zoomMock = vi.fn();
const playPauseMock = vi.fn();

function makeWs() {
  return {
    load: loadMock,
    on: onMock,
    destroy: destroyMock,
    setTime: vi.fn(),
    play: vi.fn(),
    pause: vi.fn(),
    playPause: playPauseMock,
    getDuration: getDurationMock,
    getCurrentTime: getCurrentTimeMock,
    isPlaying: isPlayingMock,
    getDecodedData: getDecodedDataMock,
    setPlaybackRate: vi.fn(),
    zoom: zoomMock,
  };
}

vi.mock("wavesurfer.js", () => ({
  __esModule: true,
  default: { create: () => createMock.mockReturnValue(makeWs())() },
}));
vi.mock("wavesurfer.js/dist/plugins/regions.js", () => ({
  __esModule: true,
  default: { create: () => ({ on: vi.fn(), addRegion: vi.fn() }) },
}));
vi.mock("wavesurfer.js/dist/plugins/timeline.js", () => ({
  __esModule: true,
  default: { create: () => ({}) },
}));
vi.mock("wavesurfer.js/dist/plugins/hover.js", () => ({
  __esModule: true,
  default: { create: () => ({}) },
}));

// ── IntersectionObserver-Mock ───────────────────────────────────────────
type IOCallback = (entries: Array<{ isIntersecting: boolean }>) => void;

class FakeIntersectionObserver {
  static instances: FakeIntersectionObserver[] = [];
  callback: IOCallback;
  constructor(cb: IOCallback) {
    this.callback = cb;
    FakeIntersectionObserver.instances.push(this);
  }
  observe() {}
  unobserve() {}
  disconnect() {}
  fire(intersecting: boolean) {
    this.callback([{ isIntersecting: intersecting }]);
  }
}

beforeEach(() => {
  vi.clearAllMocks();
  FakeIntersectionObserver.instances = [];
  (globalThis as Record<string, unknown>).IntersectionObserver =
    FakeIntersectionObserver;
  getDecodedDataMock.mockReturnValue(null);
  getDurationMock.mockReturnValue(10);
  getCurrentTimeMock.mockReturnValue(0);
});

afterEach(() => {
  delete (globalThis as Record<string, unknown>).IntersectionObserver;
});

describe("WaveformPlayer asynchrone Peaks (Change 059-Fix)", () => {
  it("startet OHNE Peaks mit undefined (Browser-Decode-Pfad)", () => {
    render(
      <LocaleProvider>
        <WaveformPlayer audioUrl="/a.mp3" />
      </LocaleProvider>,
    );
    const obs = FakeIntersectionObserver.instances[0];
    act(() => obs.fire(true));
    // kein peaks + kein durationHint → load(undefined, undefined)
    expect(loadMock).toHaveBeenCalledTimes(1);
    expect(loadMock.mock.calls[0][1]).toBeUndefined();
    expect(loadMock.mock.calls[0][2]).toBeUndefined();
  });

  it("startet MIT Peaks sofort mit [peaks] + durationHint", () => {
    render(
      <LocaleProvider>
        <WaveformPlayer audioUrl="/a.mp3" peaks={[1, 2, 3]} durationHint={12} />
      </LocaleProvider>,
    );
    const obs = FakeIntersectionObserver.instances[0];
    act(() => obs.fire(true));
    expect(loadMock).toHaveBeenCalledTimes(1);
    expect(loadMock.mock.calls[0][1]).toEqual([[1, 2, 3]]);
    expect(loadMock.mock.calls[0][2]).toBe(12);
  });

  it("RE-INITIALISIERT mit Peaks, wenn sie NACH dem ersten Load eintreffen", () => {
    // Change 059: lite-Liste liefert peaks=null; der Detail-Fetch kommt
    // später → peaks-Prop ändert sich → Effekt muss neu laufen (2. create
    // + 2. load MIT Peaks). Vor dem Fix: [audioUrl, backend, inView] —
    // peaks war keine Dependency → ewiges „Loading waveform…".
    const { rerender } = render(
      <LocaleProvider>
        <WaveformPlayer audioUrl="/a.mp3" />
      </LocaleProvider>,
    );
    const obs = FakeIntersectionObserver.instances[0];
    act(() => obs.fire(true));
    expect(createMock).toHaveBeenCalledTimes(1);
    expect(loadMock).toHaveBeenCalledTimes(1);

    // Peaks treffen asynchron ein → Re-Render mit peaks + durationHint
    act(() => {
      rerender(
        <LocaleProvider>
          <WaveformPlayer audioUrl="/a.mp3" peaks={[5, 4, 3, 2, 1]} durationHint={12} />
        </LocaleProvider>,
      );
    });

    expect(createMock).toHaveBeenCalledTimes(2); // neuer WaveSurfer
    expect(loadMock).toHaveBeenCalledTimes(2);
    expect(loadMock.mock.calls[1][1]).toEqual([[5, 4, 3, 2, 1]]);
    expect(loadMock.mock.calls[1][2]).toBe(12);
  });

  it("destroyed den alten Player beim Re-Init (kein Leak)", () => {
    const { rerender } = render(
      <LocaleProvider>
        <WaveformPlayer audioUrl="/a.mp3" />
      </LocaleProvider>,
    );
    const obs = FakeIntersectionObserver.instances[0];
    act(() => obs.fire(true));
    expect(destroyMock).toHaveBeenCalledTimes(0);

    act(() => {
      rerender(
        <LocaleProvider>
          <WaveformPlayer audioUrl="/a.mp3" peaks={[1]} durationHint={5} />
        </LocaleProvider>,
      );
    });
    // Cleanup des ersten Laufs destroyt den alten ws
    expect(destroyMock).toHaveBeenCalledTimes(1);
    expect(createMock).toHaveBeenCalledTimes(2);
  });
});
