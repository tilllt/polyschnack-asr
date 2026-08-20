import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, act } from "@testing-library/react";
import { LocaleProvider } from "../useLocale";
import { WaveformPlayer } from "./WaveformPlayer";

/**
 * Change 052: Lazy-Loading — der Player lädt das Audio erst, wenn er in den
 * Viewport kommt (IntersectionObserver). Vorher fetchen beim Öffnen einer
 * Benchmark-Kategorie ALLE Player gleichzeitig (8× Preview-Request) — bei
 * langsamem Netz bleibt der Play-Klick wirkungslos, weil die Datei noch
 * lädt.
 *
 * Gemockt: wavesurfer.js (create/load/on) + IntersectionObserver (feuert
 * den Callback nur auf Anforderung) — jsdom selbst hat keinen IO.
 */

// ── WaveSurfer-Mock ─────────────────────────────────────────────────────
const createMock = vi.fn();
const loadMock = vi.fn();
const onMock = vi.fn();
const destroyMock = vi.fn();
const setTimeMock = vi.fn();
const playMock = vi.fn();
const pauseMock = vi.fn();
const playPauseMock = vi.fn();
const getDurationMock = vi.fn(() => 0);
const getCurrentTimeMock = vi.fn(() => 0);
const isPlayingMock = vi.fn(() => false);
const getDecodedDataMock = vi.fn(() => null);
const setPlaybackRateMock = vi.fn();
const zoomMock = vi.fn();

function makeWs() {
  return {
    load: loadMock,
    on: onMock,
    destroy: destroyMock,
    setTime: setTimeMock,
    play: playMock,
    pause: pauseMock,
    playPause: playPauseMock,
    getDuration: getDurationMock,
    getCurrentTime: getCurrentTimeMock,
    isPlaying: isPlayingMock,
    getDecodedData: getDecodedDataMock,
    setPlaybackRate: setPlaybackRateMock,
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
  /** Test-Helfer: Sichtbarkeit simulieren. */
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
});

afterEach(() => {
  delete (globalThis as Record<string, unknown>).IntersectionObserver;
});

describe("WaveformPlayer Lazy-Loading (Change 052)", () => {
  it("lädt das Audio NICHT, bevor der Player sichtbar ist", () => {
    render(
      <LocaleProvider>
        <WaveformPlayer audioUrl="/api/benchmark/preview/s_001" />
      </LocaleProvider>,
    );
    expect(FakeIntersectionObserver.instances.length).toBe(1);
    // kein ws.load ohne Sichtbarkeit
    expect(loadMock).not.toHaveBeenCalled();
  });

  it("lädt das Audio, sobald der Player in den Viewport kommt", () => {
    render(
      <LocaleProvider>
        <WaveformPlayer audioUrl="/api/benchmark/preview/s_001" />
      </LocaleProvider>,
    );
    const obs = FakeIntersectionObserver.instances[0];
    act(() => obs.fire(true)); // Sichtbarkeit → ws.load
    expect(loadMock).toHaveBeenCalledTimes(1);
    expect(loadMock.mock.calls[0][0]).toBe("/api/benchmark/preview/s_001");
  });

  it("beobachtet nach dem ersten Sichtbarwerden nicht weiter (disconnect)", () => {
    render(
      <LocaleProvider>
        <WaveformPlayer audioUrl="/api/benchmark/preview/s_001" />
      </LocaleProvider>,
    );
    const obs = FakeIntersectionObserver.instances[0];
    const disconnect = vi.spyOn(obs, "disconnect");
    act(() => obs.fire(true));
    expect(disconnect).toHaveBeenCalled();
  });
});
