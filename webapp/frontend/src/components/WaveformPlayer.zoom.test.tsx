/**
 * Change 219 (Nutzer-Vorgabe 20.09.2026, wörtlich):
 *   „wenn man an ein Wort ranzoomt und es bearbeitet, danach auf Zoom Out
 *    drückt, zoomt die Ansicht komplett raus, nicht ‚ein bisschen' von der
 *    letzten Zoom Stufe. Plus und minus müssen immer relativ zur letzten
 *    Zoomstufe sein."
 *
 * BELEGTE URSACHE (alter Code, WaveformPlayer.tsx):
 *   „+“  → `doZoom(w, Math.min(ZOOM_STEPS.length - 1, zoomIdx + 1))`
 *   „−“  → im Timing-Modus `setTimingZoom(false); doZoom(w, ZOOM_STEPS.length - 1)`
 *          sonst       `doZoom(w, Math.max(0, zoomIdx - 1))`
 * Beide Knöpfe setzten also eine STUFE der festen Liste [1,2,4,6,10,20,50]
 * (absolute px/s). Aus dem Wort-Zoom (dort oft mehrere hundert px/s) sprang „−“
 * über den Sonderzweig auf 20 px/s — praktisch die Gesamtansicht. Jetzt rechnen
 * beide relativ zur aktuell angezeigten px/s (ZOOM_FACTOR aus waveformTime.ts).
 *
 * Geprüft wird an den echten Aufrufen von `ws.zoom(px/s)` — das ist der Wert,
 * der die Ansicht tatsächlich setzt.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, act, fireEvent, screen } from "@testing-library/react";
import { LocaleProvider } from "../useLocale";
import { WaveformPlayer } from "./WaveformPlayer";
import { MAX_TIMING_PPS, ZOOM_FACTOR, fitPps } from "../waveformTime";

// ── WaveSurfer-Mock ─────────────────────────────────────────────────────
const createMock = vi.fn();
const onMock = vi.fn();
const zoomMock = vi.fn();
const getDurationMock = vi.fn(() => 10);

function makeWs() {
  return {
    load: vi.fn(),
    on: onMock,
    destroy: vi.fn(),
    setTime: vi.fn(),
    play: vi.fn(),
    pause: vi.fn(),
    playPause: vi.fn(),
    getDuration: getDurationMock,
    getCurrentTime: vi.fn(() => 0),
    isPlaying: vi.fn(() => false),
    getDecodedData: vi.fn(() => null),
    setPlaybackRate: vi.fn(),
    setOptions: vi.fn(),
    getScroll: vi.fn(() => 0),
    setScroll: vi.fn(),
    zoom: zoomMock,
  };
}

vi.mock("wavesurfer.js", () => ({
  __esModule: true,
  default: { create: () => createMock.mockReturnValue(makeWs())() },
}));
vi.mock("wavesurfer.js/dist/plugins/regions.js", () => ({
  __esModule: true,
  default: {
    create: () => ({
      on: vi.fn(),
      // Etwas mehr als ein nackter vi.fn(): die Komponente hängt an der
      // Region Listener und ein Element (Wort-Markierung). Ohne Element
      // bräche der Region-Effekt ab, bevor der Zoom geprüft werden kann.
      addRegion: (opts: { start: number; end: number; resize?: boolean }) => {
        const element = document.createElement("div");
        element.dataset.fakeRegion = "1";
        document.body.appendChild(element);
        return {
          element,
          start: opts.start,
          end: opts.end,
          on: vi.fn(),
          setOptions: vi.fn(),
          remove: () => element.remove(),
        };
      },
    }),
  },
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

/** jsdom liefert für clientWidth immer 0 — der Zoom rechnet aber mit der
 *  echten Breite (fitPps(800, 10) = 80 px/s). Ohne diese Messung wäre die
 *  Untergrenze MIN_PPS (0,05) und die Zahlen wären nicht aussagekräftig. */
function mitContainerBreite(px: number) {
  Object.defineProperty(window.HTMLElement.prototype, "clientWidth", {
    configurable: true,
    get: () => px,
  });
}

const BREITE = 800;
const DAUER = 10;
const FIT = fitPps(BREITE, DAUER); // 80 px/s

const WORT = { segIdx: 0, wordIdx: 1, start: 5, end: 6 };

type Props = {
  timingWord?: typeof WORT | null;
  timingNeighbors?: { prev: null; next: null } | null;
};

function setup(p: Props = {}) {
  const tree = (
    <LocaleProvider>
      <WaveformPlayer
        audioUrl="/a.mp3"
        peaks={[1, 2, 3]}
        durationHint={DAUER}
        timingWord={p.timingWord ?? null}
        timingNeighbors={p.timingNeighbors ?? null}
      />
    </LocaleProvider>
  );
  const r = render(tree);
  act(() => FakeIntersectionObserver.instances[0].fire(true));
  const ready = onMock.mock.calls.find((c) => c[0] === "ready")?.[1];
  expect(ready).toBeTypeOf("function");
  act(() => ready());
  return r;
}

const letztePps = () => {
  const calls = zoomMock.mock.calls;
  return calls[calls.length - 1][0] as number;
};
const zoomOut = () => screen.getByTitle("Zoom out") as HTMLButtonElement;
const zoomIn = () => screen.getByTitle("Zoom in") as HTMLButtonElement;
const label = () =>
  document.querySelector<HTMLElement>("[class*='min-w-']")?.textContent ?? "";

beforeEach(() => {
  vi.clearAllMocks();
  FakeIntersectionObserver.instances = [];
  (globalThis as Record<string, unknown>).IntersectionObserver = FakeIntersectionObserver;
  getDurationMock.mockReturnValue(DAUER);
  mitContainerBreite(BREITE);
});

afterEach(() => {
  delete (globalThis as Record<string, unknown>).IntersectionObserver;
});

describe("Zoom-Knöpfe: relativ zur letzten Stufe (Change 219)", () => {
  it("Startzustand: Gesamtansicht (fit) — „−“ ist wirkungslos und deshalb aus", () => {
    setup();
    // Initial-Zoom = fit
    expect(letztePps()).toBeCloseTo(FIT, 6);
    expect(label()).toBe("fit");
    expect(zoomOut().disabled).toBe(true);
    expect(zoomIn().disabled).toBe(false);
  });

  it("„+“ ist GENAU eine Stufe (×1,5), „−“ geht genau eine Stufe zurück — nicht auf fit", () => {
    setup();
    const fitCalls = zoomMock.mock.calls.length;

    act(() => {
      fireEvent.click(zoomIn());
    });
    expect(letztePps()).toBeCloseTo(FIT * ZOOM_FACTOR, 6); // 120 px/s
    expect(label()).toBe("1.5×");
    expect(zoomOut().disabled).toBe(false);

    // Zurück: px/s = vorheriger Wert / Faktor — und NICHT die Gesamtansicht
    act(() => {
      fireEvent.click(zoomOut());
    });
    expect(letztePps()).toBeCloseTo(FIT, 6);
    expect(letztePps()).not.toBeCloseTo(0.05, 6); // nicht MIN_PPS
    expect(label()).toBe("fit");
    // an der Untergrenze: Knopf aus, kein weiterer zoom()-Aufruf
    expect(zoomOut().disabled).toBe(true);
    const vorher = zoomMock.mock.calls.length;
    act(() => {
      fireEvent.click(zoomOut());
    });
    expect(zoomMock.mock.calls.length).toBe(vorher);
    expect(zoomMock.mock.calls.length).toBe(fitCalls + 2);
  });

  it("mehrere Stufen sind zueinander umkehrbar (×1,5 dreimal, dann zweimal ÷1,5)", () => {
    setup();
    act(() => {
      fireEvent.click(zoomIn());
      fireEvent.click(zoomIn());
      fireEvent.click(zoomIn());
    });
    expect(letztePps()).toBeCloseTo(FIT * ZOOM_FACTOR ** 3, 6);
    act(() => {
      fireEvent.click(zoomOut());
      fireEvent.click(zoomOut());
    });
    expect(letztePps()).toBeCloseTo(FIT * ZOOM_FACTOR, 6);
    expect(label()).toBe("1.5×");
  });

  it("im Timing-Modus (Wort-Zoom) ist „−“ EINE Stufe zurück — nicht die Gesamtansicht", async () => {
    // Der gemeldete Fall: an ein Wort ranzoomen, bearbeiten, dann Zoom Out.
    setup({ timingWord: WORT, timingNeighbors: { prev: null, next: null } });
    // Die weiche Fahrt (Change 217) läuft ~260 ms über rAF — abwarten, damit
    // die Basis für den nächsten Schritt feststeht (das ist der „danach“-Fall).
    await act(async () => {
      await new Promise((r) => setTimeout(r, 400));
    });
    const wortPps = letztePps();
    expect(wortPps).toBeGreaterThan(FIT * 2); // deutlich im Wort-Zoom
    expect(label()).not.toBe("fit");

    act(() => {
      fireEvent.click(zoomOut());
    });
    expect(letztePps()).toBeCloseTo(wortPps / ZOOM_FACTOR, 4);
    // ausdrücklich NICHT die Gesamtansicht
    expect(letztePps()).toBeGreaterThan(FIT * 1.5);
    expect(label()).not.toBe("fit");
    expect(zoomOut().disabled).toBe(false);
  });

  it("Obergrenze: „+“ bleibt am effektiven Deckel stehen und wird dort deaktiviert", () => {
    setup();
    // Bei 10 s Dauer ist MAX_TIMING_PPS die Grenze (2^25/10 wäre größer).
    let schritte = 0;
    while (!zoomIn().disabled && schritte < 60) {
      act(() => {
        fireEvent.click(zoomIn());
      });
      schritte += 1;
    }
    expect(zoomIn().disabled).toBe(true);
    expect(letztePps()).toBe(MAX_TIMING_PPS);
    // kein wirkungsloser Klick mehr
    const vorher = zoomMock.mock.calls.length;
    act(() => {
      fireEvent.click(zoomIn());
    });
    expect(zoomMock.mock.calls.length).toBe(vorher);
    // und der erste Schritt zurück ist wieder eine Stufe
    act(() => {
      fireEvent.click(zoomOut());
    });
    expect(letztePps()).toBeCloseTo(MAX_TIMING_PPS / ZOOM_FACTOR, 6);
    expect(zoomIn().disabled).toBe(false);
  });
});
