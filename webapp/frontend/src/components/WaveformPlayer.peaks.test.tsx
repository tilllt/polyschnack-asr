import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, act, fireEvent, screen } from "@testing-library/react";
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
  static observed: (Element | null)[] = [];
  callback: IOCallback;
  constructor(cb: IOCallback) {
    this.callback = cb;
    FakeIntersectionObserver.instances.push(this);
  }
  observe(el: Element) {
    FakeIntersectionObserver.observed.push(el);
  }
  unobserve() {}
  disconnect() {}
  fire(intersecting: boolean) {
    this.callback([{ isIntersecting: intersecting }]);
  }
}

beforeEach(() => {
  vi.clearAllMocks();
  FakeIntersectionObserver.instances = [];
  FakeIntersectionObserver.observed = [];
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

describe("WaveformPlayer Change 072 — Deadlock (Observer auf hidden Container)", () => {
  it("beobachtet den ÄUSSEREN Wrapper, nicht den hidden Canvas-Container", () => {
    // Regression: Vor 072 beobachtete der Observer den Container, der bis
    // `ready` display:none (hidden) ist. display:none-Elemente liefern NIE
    // isIntersecting:true → inView blieb false → Init-Effekt lief nie →
    // „Loading waveform…" für immer. Der beobachtete Knoten muss also ein
    // SICHTBARER Vorfahre des Containers sein (nicht der Container selbst).
    const { container } = render(
      <LocaleProvider>
        <WaveformPlayer audioUrl="/a.mp3" peaks={[1, 2, 3]} durationHint={5} />
      </LocaleProvider>,
    );
    const observed = FakeIntersectionObserver.observed[0];
    expect(observed).toBeTruthy();

    const canvasContainer = container.querySelector(
      "[class*='hidden']",
    ) as HTMLElement | null;
    // Der Canvas-Container trägt vor ready die hidden-Klasse …
    expect(canvasContainer).toBeTruthy();
    // … und darf NICHT das beobachtete Element sein (sonst Deadlock).
    expect(observed).not.toBe(canvasContainer);
    // Der Wrapper ist ein Vorfahre des hidden Containers.
    expect(observed!.contains(canvasContainer)).toBe(true);
  });

  it("startet den Init auch, wenn der Container hidden bleibt (fire auf Wrapper)", () => {
    render(
      <LocaleProvider>
        <WaveformPlayer audioUrl="/a.mp3" peaks={[1, 2, 3]} durationHint={5} />
      </LocaleProvider>,
    );
    const obs = FakeIntersectionObserver.instances[0];
    act(() => obs.fire(true));
    // WaveSurfer wird trotz hidden-Container initialisiert (070-Fix greift)
    expect(createMock).toHaveBeenCalledTimes(1);
    expect(loadMock).toHaveBeenCalledTimes(1);
    expect(loadMock.mock.calls[0][1]).toEqual([[1, 2, 3]]);
  });
});

describe("WaveformPlayer Change 100 — Zoom bleibt bei späten Annotationen stabil", () => {
  it("resettet den User-Zoom NICHT, wenn annotations asynchron nachkommen", () => {
    // Change 059: Peaks/Annotations kommen über den Detail-Fetch NACH dem
    // Player-ready. Vor Change 100: updateMarkers (abhängig von
    // annotations) gab doZoom eine neue Referenz → der ready-Effekt lief
    // erneut → doZoom(0) → User-Zoom sprang sofort auf „fit" zurück.
    const { rerender } = render(
      <LocaleProvider>
        <WaveformPlayer audioUrl="/a.mp3" peaks={[1, 2, 3]} durationHint={10} annotations={[]} />
      </LocaleProvider>,
    );
    const obs = FakeIntersectionObserver.instances[0];
    act(() => obs.fire(true));

    // ready feuern → Initial-Zoom (fit) läuft genau einmal
    const readyHandler = onMock.mock.calls.find((c) => c[0] === "ready")?.[1];
    expect(readyHandler).toBeTypeOf("function");
    act(() => readyHandler());
    expect(zoomMock).toHaveBeenCalledTimes(1); // Initial-Fit

    // User zoomt rein → 2. zoom()-Aufruf, Zoom-Label „1×"
    fireEvent.click(screen.getByTitle("Zoom in"));
    expect(zoomMock).toHaveBeenCalledTimes(2);
    // Zoom-Label (min-w-[36px]) — NICHT der Speed-Button „1×"
    expect(screen.getByText("1×", { selector: "[class*='min-w-']" })).toBeTruthy();

    // Annotationen treffen asynchron ein (Detail-Fetch) → Re-Render
    act(() => {
      rerender(
        <LocaleProvider>
          <WaveformPlayer
            audioUrl="/a.mp3"
            peaks={[1, 2, 3]}
            durationHint={10}
            annotations={[{ id: 1, start_s: 5 }]}
          />
        </LocaleProvider>,
      );
    });

    // Change 100: KEIN erneuter doZoom(0) — der User-Zoom bleibt erhalten
    expect(zoomMock).toHaveBeenCalledTimes(2);
    expect(screen.getByText("1×", { selector: "[class*='min-w-']" })).toBeTruthy();
  });

  it("ruft ws.zoom NICHT auf, solange der neue ws nach Re-Init noch lädt (kein „No audio loaded“)", () => {
    // Firefox-Konsolenbefund 2026-08-23: ws.zoom() warf „Error: No audio
    // loaded“. Change 059 re-initialisiert den Player, wenn Peaks asynchron
    // nachkommen — der ready-STATE bleibt vom alten ws true, aber
    // wsRef.current ist der NEUE, noch ladende ws. doZoom muss in diesem
    // Fenster abbrechen (wsReadyRef-Gate), statt ws.zoom() zu werfen.
    const { rerender } = render(
      <LocaleProvider>
        <WaveformPlayer audioUrl="/a.mp3" />
      </LocaleProvider>,
    );
    const obs = FakeIntersectionObserver.instances[0];
    act(() => obs.fire(true));

    // Erstes ready → Initial-Fit läuft
    const ready1 = onMock.mock.calls.find((c) => c[0] === "ready")?.[1];
    act(() => ready1());
    expect(zoomMock).toHaveBeenCalledTimes(1);

    // Change 059: Peaks kommen asynchron nach → Re-Init (neuer ws lädt noch)
    act(() => {
      rerender(
        <LocaleProvider>
          <WaveformPlayer audioUrl="/a.mp3" peaks={[1, 2, 3]} durationHint={10} />
        </LocaleProvider>,
      );
    });
    expect(createMock).toHaveBeenCalledTimes(2);

    // Zoom-Klick im Re-Init-Fenster: neuer ws hat noch kein Audio →
    // doZoom bricht ab, KEIN ws.zoom()-Aufruf (vorher: Exception im Effekt)
    fireEvent.click(screen.getByTitle("Zoom in"));
    expect(zoomMock).toHaveBeenCalledTimes(1);

    // Neues ready → Zoom-Gate öffnet → Klick zoomt wieder
    const ready2 = onMock.mock.calls.filter((c) => c[0] === "ready").pop()?.[1];
    act(() => ready2());
    fireEvent.click(screen.getByTitle("Zoom in"));
    expect(zoomMock).toHaveBeenCalledTimes(2);
    expect(screen.getByText("1×", { selector: "[class*='min-w-']" })).toBeTruthy();
  });
});

describe("WaveformPlayer Poll-Referenz-Drehung (Change 112)", () => {
  it("neue peaks-Referenz mit GLEICHEM Inhalt startet KEINEN neuen Load", () => {
    // Produktions-Befund 23.08. (Android-Chrome): Die Karten-Polls liefern
    // bei jedem Fetch ein NEUES peaks-Array mit identischem Inhalt. Vor dem
    // Fix triggert die peaks-Dependency des Load-Effekts bei jeder
    // Referenz-Drehung einen Abbruch + Neu-Fetch/Neu-Decode: Kurve leer
    // 1–3 s („verschwindet/erscheint periodisch") + ~180 MB PCM-Allokation
    // pro Reload bei 95-min-Audios → kumuliert OOM „Aw, Snap".
    const { rerender } = render(
      <LocaleProvider>
        <WaveformPlayer audioUrl="/a.mp3" peaks={[1, 2, 3]} durationHint={12} />
      </LocaleProvider>,
    );
    const obs = FakeIntersectionObserver.instances[0];
    act(() => obs.fire(true));
    expect(createMock).toHaveBeenCalledTimes(1);
    expect(loadMock).toHaveBeenCalledTimes(1);

    // Poll #1: neue Referenz, identischer Inhalt
    act(() => {
      rerender(
        <LocaleProvider>
          <WaveformPlayer audioUrl="/a.mp3" peaks={[1, 2, 3]} durationHint={12} />
        </LocaleProvider>,
      );
    });
    // Poll #2
    act(() => {
      rerender(
        <LocaleProvider>
          <WaveformPlayer audioUrl="/a.mp3" peaks={[1, 2, 3]} durationHint={12} />
        </LocaleProvider>,
      );
    });

    // Kein Re-Init, kein Reload — Player bleibt stabil
    expect(createMock).toHaveBeenCalledTimes(1);
    expect(loadMock).toHaveBeenCalledTimes(1);
  });

  it("echter Inhalt-Wechsel re-initialisiert weiterhin (Change 059 bleibt)", () => {
    // Kontrollfall: Die Signatur darf NUR bei echten Peaks-Änderungen
    // feuern (async Nachlieferung) — nicht bei Referenz-Drehungen.
    const { rerender } = render(
      <LocaleProvider>
        <WaveformPlayer audioUrl="/a.mp3" peaks={[1, 2, 3]} durationHint={12} />
      </LocaleProvider>,
    );
    const obs = FakeIntersectionObserver.instances[0];
    act(() => obs.fire(true));
    expect(createMock).toHaveBeenCalledTimes(1);

    act(() => {
      rerender(
        <LocaleProvider>
          <WaveformPlayer audioUrl="/a.mp3" peaks={[9, 8, 7]} durationHint={12} />
        </LocaleProvider>,
      );
    });
    expect(createMock).toHaveBeenCalledTimes(2);
    expect(loadMock).toHaveBeenCalledTimes(2);
    expect(loadMock.mock.calls[1][1]).toEqual([[9, 8, 7]]);
  });
});
