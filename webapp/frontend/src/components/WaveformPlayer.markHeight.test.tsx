/**
 * Change 219 (Nutzer-Vorgabe 20.09.2026, wörtlich):
 *   „Wenn ein langes Wort die ganze Waveserver area ausfüllt, kann man
 *    nirgendwo mehr anfassen zum scrollen. Können wir die Markierungen nur von
 *    oben bis zur Hälfte der Timeline anzeigen, so das man den unteren Teil
 *    fürs scrollen anfassen könnte?" + „Die seitlichen Start/end Marker können
 *    über die ganze Höhe gehen."
 *
 * Warum HIER das gerenderte DOM geprüft wird (und nicht nur der Quelltext):
 * Das RegionsPlugin setzt die Größe INLINE —
 *   initElement():        am Flächen-Element `top: 0`, `height: 100 %`
 *   addResizeHandles():   an beiden Handles   `top: 0`, `height: 100 %`
 * (regions.js 7.12, belegt im Bundle). Ein Inline-Stil schlägt jede normale
 * Klassenregel — deshalb muss die Komponente die Werte selbst INLINE setzen
 * (applyMarkGeometry). Genau das kann die Attrappe nachstellen: sie erzeugt die
 * Region mit denselben Inline-Startwerten wie die Bibliothek und mit
 * Handle-Kindern (part="region-handle-left/-right"), sodass prüfbar ist, dass
 * unsere Werte den Bibliothekswerten tatsächlich überschreiben.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, act } from "@testing-library/react";
import { LocaleProvider } from "../useLocale";
import {
  TIMING_HANDLE_HEIGHT,
  TIMING_MARK_HEIGHT,
  WaveformPlayer,
  applyMarkGeometry,
} from "./WaveformPlayer";

// ── WaveSurfer-Mock ─────────────────────────────────────────────────────
const onMock = vi.fn();
const getDurationMock = vi.fn(() => 20);

vi.mock("wavesurfer.js", () => ({
  __esModule: true,
  default: {
    create: () => ({
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
      zoom: vi.fn(),
    }),
  },
}));

// ── Regions-Plugin-Attrappe mit den INLINE-Startwerten der Bibliothek ────
interface FakeRegion {
  element: HTMLElement;
  start: number;
  end: number;
  options: Record<string, unknown>;
  on: (ev: string, cb: (...a: unknown[]) => void) => void;
  setOptions: (o: { start?: number; end?: number }) => void;
  remove: () => void;
}

let regions: FakeRegion[] = [];

function makeRegionsPlugin() {
  const mine: FakeRegion[] = [];
  regions = mine;
  return {
    on: vi.fn(),
    addRegion: (opts: { start: number; end: number; resize?: boolean }): FakeRegion => {
      const element = document.createElement("div");
      element.dataset.fakeRegion = "1";
      // exakt die Inline-Werte aus RegionsPlugin.initElement()
      element.style.position = "absolute";
      element.style.top = "0";
      element.style.height = "100%";
      element.style.backgroundColor = "rgba(46,160,67,0.30)";
      element.style.pointerEvents = "all";
      if (opts.resize) {
        for (const part of ["region-handle-left", "region-handle-right"]) {
          const h = document.createElement("div");
          h.setAttribute("part", `region-handle ${part}`);
          // exakt die Inline-Werte aus RegionsPlugin.addResizeHandles()
          h.style.position = "absolute";
          h.style.top = "0";
          h.style.height = "100%";
          h.style.width = "6px";
          element.appendChild(h);
        }
      }
      document.body.appendChild(element);
      const region: FakeRegion = {
        element,
        start: opts.start,
        end: opts.end,
        options: { ...opts },
        on: vi.fn(),
        setOptions: (o) => {
          Object.assign(region.options, o);
          if (typeof o.start === "number") region.start = o.start;
          if (typeof o.end === "number") region.end = o.end;
        },
        remove: () => {
          element.remove();
          const i = mine.indexOf(region);
          if (i >= 0) mine.splice(i, 1);
        },
      };
      mine.push(region);
      return region;
    },
  };
}

vi.mock("wavesurfer.js/dist/plugins/regions.js", () => ({
  __esModule: true,
  default: { create: () => makeRegionsPlugin() },
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

const WORT = { segIdx: 0, wordIdx: 1, start: 5, end: 6 };
const NACHBARN = {
  prev: { segIdx: 0, wordIdx: 0, text: "Eins", start: 3, end: 4.5 },
  next: { segIdx: 0, wordIdx: 2, text: "Drei", start: 6.5, end: 8 },
};

type Props = {
  timingWord?: typeof WORT | null;
  timingNeighbors?: typeof NACHBARN | null;
};

function setup(p: Props = {}) {
  render(
    <LocaleProvider>
      <WaveformPlayer
        audioUrl="/a.mp3"
        peaks={[1, 2, 3]}
        durationHint={20}
        timingWord={p.timingWord ?? null}
        timingNeighbors={p.timingNeighbors ?? null}
      />
    </LocaleProvider>,
  );
  act(() => FakeIntersectionObserver.instances[0].fire(true));
  const ready = onMock.mock.calls.find((c) => c[0] === "ready")?.[1];
  expect(ready).toBeTypeOf("function");
  act(() => ready());
}

const aktiv = () => document.querySelector<HTMLElement>(".ps-timing-region-active");
const nachbarn = () =>
  Array.from(document.querySelectorAll<HTMLElement>(".ps-timing-region-neighbor"));
const handles = (el: HTMLElement) =>
  Array.from(el.querySelectorAll<HTMLElement>('[part~="region-handle-left"], [part~="region-handle-right"]'));

beforeEach(() => {
  vi.clearAllMocks();
  regions = [];
  FakeIntersectionObserver.instances = [];
  (globalThis as Record<string, unknown>).IntersectionObserver = FakeIntersectionObserver;
  getDurationMock.mockReturnValue(20);
});

afterEach(() => {
  delete (globalThis as Record<string, unknown>).IntersectionObserver;
  document.querySelectorAll("[data-fake-region]").forEach((el) => el.remove());
});

describe("Change 219 — Flächen belegen nur die obere Hälfte", () => {
  it("die Konstanten sind 50 % (Fläche) und 200 % davon (Kanten)", () => {
    expect(TIMING_MARK_HEIGHT).toBe("50%");
    expect(TIMING_HANDLE_HEIGHT).toBe("200%");
  });

  it("aktives Wort: Fläche wird INLINE auf 50 % überschrieben (Plugin setzt 100 %)", () => {
    setup({ timingWord: WORT, timingNeighbors: NACHBARN });
    const el = aktiv();
    expect(el).toBeTruthy();
    // Die Attrappe startet wie die Bibliothek mit height:100%
    expect(el!.style.top).toMatch(/^0(px)?$/);
    expect(el!.style.height).toBe("50%");
    expect(el!.classList.contains("ps-mark-half")).toBe(true);
    // Oberkante bleibt bei 0 → Fläche reicht von oben bis zur halben Höhe
    expect(el!.style.bottom || "").toBe("");
  });

  it("auch die Nachbarflächen stehen nur in der oberen Hälfte", () => {
    setup({ timingWord: WORT, timingNeighbors: NACHBARN });
    const nb = nachbarn();
    expect(nb.length).toBe(2);
    for (const el of nb) {
      expect(el.style.height).toBe("50%");
      expect(el.style.top).toMatch(/^0(px)?$/);
      expect(el.classList.contains("ps-mark-half")).toBe(true);
      // die gerade wiederhergestellten gestrichelten Seitenkanten bleiben
      expect(el.style.borderLeft).toContain("dashed");
      expect(el.style.borderRight).toContain("dashed");
    }
  });

  it("ohne aktives Wort: auch die Crop-Auswahlfläche ist halb hoch", () => {
    setup(); // kein timingWord → es entsteht die ✂-Crop-Region
    const crop = regions[0]?.element;
    expect(crop).toBeTruthy();
    expect(crop!.style.height).toBe("50%");
    expect(crop!.classList.contains("ps-mark-half")).toBe(true);
  });

  it("die untere Hälfte wird NICHT abgedeckt — keine Zeigerfalle am Flächenelement", () => {
    setup({ timingWord: WORT, timingNeighbors: NACHBARN });
    const el = aktiv()!;
    // Die Fläche fängt Zeigerereignisse ab — aber nur dort, wo sie steht
    // (obere Hälfte). Der untere Bereich ist gar nicht Teil des Elements/Treffers.
    expect(el.style.pointerEvents).not.toBe("none");
    expect(el.style.height).toBe("50%");
    // Kein Blockieren des Scrollens: kein touch-action am Element (weder
    // inline noch über unsere Klasse — s. index.css-Test in timingMark).
    expect(el.style.touchAction || "").toBe("");
  });
});

describe("Change 219 — seitliche Start/End-Kanten über die VOLLE Höhe", () => {
  it("aktives Wort: beide Greifkanten überschreiben die 100 % der Bibliothek mit 200 %", () => {
    setup({ timingWord: WORT, timingNeighbors: NACHBARN });
    const hs = handles(aktiv()!);
    expect(hs.length).toBe(2); // Start und Ende
    for (const h of hs) {
      expect(h.style.height).toBe("200%"); // 200 % von 50 % = volle Höhe
      expect(h.style.top).toMatch(/^0(px)?$/);
      // greifbar und sichtbar: Breite/Cursor kommen weiter von der Bibliothek
      expect(h.style.width).toBe("6px");
    }
  });

  it("applyMarkGeometry: 50 % Fläche, 200 % Kanten, sonst nichts", () => {
    const el = document.createElement("div");
    el.style.top = "0";
    el.style.height = "100%";
    const links = document.createElement("div");
    links.setAttribute("part", "region-handle region-handle-left");
    links.style.height = "100%";
    const rechts = document.createElement("div");
    rechts.setAttribute("part", "region-handle region-handle-right");
    rechts.style.height = "100%";
    el.append(links, rechts);

    applyMarkGeometry(el);

    expect(el.style.height).toBe("50%");
    expect(el.style.top).toMatch(/^0(px)?$/);
    expect(links.style.height).toBe("200%");
    expect(rechts.style.height).toBe("200%");
    expect(links.style.top).toMatch(/^0(px)?$/);
    expect(rechts.style.top).toMatch(/^0(px)?$/);
    expect(links.style.width || "").toBe("");
    expect(el.style.touchAction || "").toBe("");
  });

  it("robust: ohne Element passiert nichts (kein Wurf)", () => {
    expect(() => applyMarkGeometry(null)).not.toThrow();
    expect(() => applyMarkGeometry(undefined)).not.toThrow();
  });
});
