import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, act } from "@testing-library/react";
import { LocaleProvider } from "../useLocale";
import { WaveformPlayer, LARGE_FILE_THRESHOLD_S } from "./WaveformPlayer";

/**
 * Change 198 — langer Aufnahme + langsame Leitung ergab eine korrupte
 * Wellenform OHNE Fehlermeldung.
 *
 * Ursache: der Worker-Fetch-Pfad prüfte den Backend-Modus nicht. Auch im
 * MediaElement-Modus (ab 30 min, eingeführt damit lange Dateien STREAMEN)
 * lud der Worker die komplette Datei (bei 98 min: 47 MB) und übergab
 * WaveSurfer eine blob:-URL. Ein Blob kennt keine Range-Requests — der
 * Streaming-Vorteil war aufgehoben. Brach die Verbindung ab, wurde der
 * abgeschnittene Puffer mangels Längenprüfung still zu einem KÜRZEREN
 * Audio dekodiert (gemessen: 3 MB von 47 MB → 1021 s statt 5868 s).
 *
 * Diese Tests sichern die Entscheidung ab: Worker NUR im WebAudio-Modus.
 */

// ── WaveSurfer-Mock ─────────────────────────────────────────────────────
const createMock = vi.fn();
const loadMock = vi.fn();

function makeWs() {
  return {
    load: loadMock,
    on: vi.fn(),
    destroy: vi.fn(),
    setTime: vi.fn(),
    play: vi.fn(),
    pause: vi.fn(),
    playPause: vi.fn(),
    getDuration: vi.fn(() => 0),
    getCurrentTime: vi.fn(() => 0),
    isPlaying: vi.fn(() => false),
    getDecodedData: vi.fn(() => null),
    setPlaybackRate: vi.fn(),
    zoom: vi.fn(),
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

// ── IntersectionObserver-Mock (Player ist lazy) ─────────────────────────
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

// ── Worker-Mock: zählt nur die Konstruktion ─────────────────────────────
class FakeWorker {
  static constructed = 0;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onerror: ((e: ErrorEvent) => void) | null = null;
  constructor() {
    FakeWorker.constructed += 1;
  }
  postMessage() {}
  terminate() {}
}

function renderPlayer(durationHint: number) {
  const { container } = render(
    <LocaleProvider>
      <WaveformPlayer
        audioUrl="/api/recordings/x/audio/preview"
        peaks={[1, 2, 3]}
        durationHint={durationHint}
      />
    </LocaleProvider>,
  );
  const obs = FakeIntersectionObserver.instances[0];
  act(() => obs.fire(true));
  return container;
}

beforeEach(() => {
  vi.clearAllMocks();
  FakeIntersectionObserver.instances = [];
  FakeWorker.constructed = 0;
  (globalThis as Record<string, unknown>).IntersectionObserver =
    FakeIntersectionObserver;
  (globalThis as Record<string, unknown>).Worker = FakeWorker;
});

afterEach(() => {
  delete (globalThis as Record<string, unknown>).IntersectionObserver;
  delete (globalThis as Record<string, unknown>).Worker;
});

describe("Change 198: Worker nur im WebAudio-Modus", () => {
  it("lange Aufnahme (MediaElement): KEIN Worker, rohe URL wird gestreamt", () => {
    renderPlayer(LARGE_FILE_THRESHOLD_S + 600);

    // Kern der Behebung: kein Voll-Download im Worker.
    expect(FakeWorker.constructed).toBe(0);
    expect(loadMock).toHaveBeenCalledTimes(1);
    // Die URL geht direkt an WaveSurfer → Browser streamt per Range-Request
    // (statt blob:, das die ganze Datei voraussetzt).
    expect(loadMock.mock.calls[0][0]).toBe(
      "/api/recordings/x/audio/preview",
    );
    // Wellenform kommt weiterhin sofort aus den Server-Peaks.
    expect(loadMock.mock.calls[0][1]).toEqual([[1, 2, 3]]);
    expect(loadMock.mock.calls[0][2]).toBe(LARGE_FILE_THRESHOLD_S + 600);
  });

  it("kurze Aufnahme (WebAudio): Worker wird weiter genutzt", () => {
    renderPlayer(60);

    expect(FakeWorker.constructed).toBe(1);
  });

  it("Grenze: exakt 30 min nutzt noch WebAudio, darüber MediaElement", () => {
    renderPlayer(LARGE_FILE_THRESHOLD_S);
    expect(FakeWorker.constructed).toBe(1);

    FakeWorker.constructed = 0;
    FakeIntersectionObserver.instances = [];
    vi.clearAllMocks();
    renderPlayer(LARGE_FILE_THRESHOLD_S + 1);
    expect(FakeWorker.constructed).toBe(0);
  });

  it("ohne Worker (z.B. Safari/jsdom): MediaElement streamt trotzdem roh", () => {
    delete (globalThis as Record<string, unknown>).Worker;
    renderPlayer(LARGE_FILE_THRESHOLD_S + 600);
    expect(loadMock.mock.calls[0][0]).toBe(
      "/api/recordings/x/audio/preview",
    );
  });
});
