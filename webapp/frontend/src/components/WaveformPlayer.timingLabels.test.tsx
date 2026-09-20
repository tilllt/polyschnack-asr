import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, act } from "@testing-library/react";
import { LocaleProvider } from "../useLocale";
import { WaveformPlayer, type TimingWord } from "./WaveformPlayer";
import type { TimingNeighbor } from "../timingNeighbors";

/**
 * Fix 2026-09-20 — Nutzer-Befund (wörtlich): „Aktuelle zeigen die Labels nicht
 * immer das aktuelle Wort und die beiden Nachbarwörter".
 *
 * Ursache: Die Beschriftungen hingen an der IDENTITÄT des Wort-Objekts und an
 * der ERZEUGUNG der Nachbar-Fläche — nicht am Text bzw. an den Nachbardaten.
 *
 *   1. Der Effekt, der die aktive Fläche (und ihr Label) anlegt, hatte die
 *      Abhängigkeiten [timingWord, ready]. Der Worttext kam über eine Ref
 *      (timingWordTextRef) — ohne Abhängigkeit. Änderte sich nur der Text
 *      (Korrektur, nachgelieferte Segmentliste), lief der Effekt nicht neu und
 *      das Label behielt den alten Text.
 *   2. Bei den Nachbarflächen wurde das Label nur beim ERZEUGEN der Fläche
 *      gesetzt. Die Fläche wird beim Wortwechsel aber wiederverwendet
 *      (setOptions) → das Label zeigte weiter den VORHERIGEN Nachbarn.
 *
 * Diese Tests decken genau diese Fälle ab: Text und Nachbarn ändern sich, OHNE
 * dass das Wort-Objekt ein neues ist (bzw. OHNE dass die Fläche neu entsteht) —
 * nicht nur den trivialen Fall „anderes Wort ausgewählt".
 */

// ── WaveSurfer-Mock ─────────────────────────────────────────────────────
const createMock = vi.fn();
const loadMock = vi.fn();
const onMock = vi.fn();
const getDurationMock = vi.fn(() => 20);

function makeWs() {
  return {
    load: loadMock,
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
    getPlaybackRate: vi.fn(() => 1),
    zoom: vi.fn(),
    getScroll: vi.fn(() => 0),
  };
}

vi.mock("wavesurfer.js", () => ({
  __esModule: true,
  default: { create: () => createMock.mockReturnValue(makeWs())() },
}));

// ── Regions-Plugin-Mock: echte DOM-Elemente, damit Labels prüfbar sind ──
interface FakeRegion {
  element: HTMLElement;
  start: number;
  end: number;
  options: Record<string, unknown>;
  on: (ev: string, cb: (...a: unknown[]) => void) => void;
  setOptions: (o: { start?: number; end?: number }) => void;
  remove: () => void;
}

/** Alle in diesem Test erzeugten Flächen (Reihenfolge = Erzeugung). */
let regions: FakeRegion[] = [];

function makeRegionsPlugin() {
  const mine: FakeRegion[] = [];
  regions = mine;
  return {
    on: vi.fn(),
    addRegion: (opts: { start: number; end: number }): FakeRegion => {
      const element = document.createElement("div");
      element.dataset.fakeRegion = "1";
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

// ── Testdaten ───────────────────────────────────────────────────────────
type Neighbors = { prev: TimingNeighbor | null; next: TimingNeighbor | null };

/** Das aktive Wort — als CONST, damit die Objekt-Identität über Rerenders
 *  gleich bleibt (genau der Produktionsfall: neue Texte/Segmente, aber der
 *  State `timingWord` wurde nicht neu gesetzt). */
const WORD: TimingWord = { segIdx: 0, wordIdx: 1, start: 5, end: 6 };
const NB: Neighbors = {
  prev: { segIdx: 0, wordIdx: 0, text: "Eins", start: 3, end: 4.5 },
  next: { segIdx: 0, wordIdx: 2, text: "Drei", start: 6.5, end: 8 },
};

/** Zweites Wort (anderer Nachbar-Kontext) — die Flächen existieren dann schon. */
const WORD2: TimingWord = { segIdx: 1, wordIdx: 1, start: 12, end: 13 };
const NB2: Neighbors = {
  prev: { segIdx: 1, wordIdx: 0, text: "Zwei", start: 10, end: 11.5 },
  next: { segIdx: 1, wordIdx: 2, text: "Vier", start: 13.5, end: 15 },
};

interface PlayerProps {
  timingWord?: TimingWord | null;
  timingWordText?: string;
  timingNeighbors?: Neighbors | null;
}

function tree(p: PlayerProps) {
  return (
    <LocaleProvider>
      <WaveformPlayer
        audioUrl="/a.mp3"
        peaks={[1, 2, 3]}
        durationHint={20}
        timingWord={p.timingWord ?? null}
        timingWordText={p.timingWordText}
        timingNeighbors={p.timingNeighbors ?? null}
      />
    </LocaleProvider>
  );
}

/** Rendert den Player und bringt ihn in den Zustand „sichtbar + ready". */
function setup(p: PlayerProps) {
  const r = render(tree(p));
  act(() => FakeIntersectionObserver.instances[0].fire(true));
  const ready = onMock.mock.calls.find((c) => c[0] === "ready")?.[1];
  expect(ready).toBeTypeOf("function");
  act(() => ready());
  const update = (next: PlayerProps) => {
    act(() => r.rerender(tree(next)));
  };
  return { ...r, update };
}

/** Beschriftung des aktiven Wortes. */
const activeLabel = () => document.querySelector<HTMLElement>(".ps-timing-word-active");
/** Beschriftungen der Nachbarwörter (prev, next — in DOM-Reihenfolge). */
const neighborLabels = () =>
  Array.from(document.querySelectorAll<HTMLElement>(".ps-timing-word-neighbor")).map(
    (el) => el.textContent,
  );
const allLabels = () => Array.from(document.querySelectorAll<HTMLElement>(".ps-timing-word"));

beforeEach(() => {
  vi.clearAllMocks();
  regions = [];
  FakeIntersectionObserver.instances = [];
  (globalThis as Record<string, unknown>).IntersectionObserver = FakeIntersectionObserver;
  getDurationMock.mockReturnValue(20);
});

afterEach(() => {
  delete (globalThis as Record<string, unknown>).IntersectionObserver;
  // Fake-Region-Elemente des Mocks aus dem DOM räumen.
  document.querySelectorAll("[data-fake-region]").forEach((el) => el.remove());
});

describe("WaveformPlayer Timing-Labels (Fix 2026-09-20)", () => {
  it("aktives Wort: der Grundfall zeigt Wort + beide Nachbarn", () => {
    setup({ timingWord: WORD, timingWordText: "Hallo", timingNeighbors: NB });

    expect(activeLabel()?.textContent).toBe("Hallo");
    expect(neighborLabels().sort()).toEqual(["Drei", "Eins"]);
  });

  it("Worttext ändert sich OHNE neues Wort-Objekt (Korrektur/Nachlieferung)", () => {
    // Genau der gemeldete Fehler: `timingWord` bleibt dasselbe Objekt (State
    // wurde nicht neu gesetzt), nur der Text kommt nach. Vor dem Fix hingen
    // die Label-Effekte an [timingWord, ready] → der Text blieb „Hallo".
    const { update } = setup({ timingWord: WORD, timingWordText: "Hallo", timingNeighbors: NB });
    expect(activeLabel()?.textContent).toBe("Hallo");

    update({ timingWord: WORD, timingWordText: "Hallo Welt", timingNeighbors: NB });

    expect(activeLabel()?.textContent).toBe("Hallo Welt");
  });

  it("Worttext ändert sich OHNE Neuaufbau der Fläche (Position bleibt)", () => {
    // Kein Neuaufbau des Blocks: dieselbe Fläche (gleiches DOM-Element),
    // dieselben Zeiten — nur der Text wird getauscht.
    const { update } = setup({ timingWord: WORD, timingWordText: "Hallo", timingNeighbors: NB });
    const regionBefore = document.querySelector<HTMLElement>(".ps-timing-region-active");
    expect(regionBefore).toBeTruthy();

    update({ timingWord: WORD, timingWordText: "Korrigiert", timingNeighbors: NB });

    const regionAfter = document.querySelector<HTMLElement>(".ps-timing-region-active");
    expect(regionAfter).toBe(regionBefore);
    expect(regions.find((r) => r.element === regionAfter)?.options.start).toBe(WORD.start);
    expect(regions.find((r) => r.element === regionAfter)?.options.end).toBe(WORD.end);
  });

  it("Nachbar-Texte ändern sich OHNE neues Wort-Objekt", () => {
    const { update } = setup({ timingWord: WORD, timingWordText: "Hallo", timingNeighbors: NB });
    expect(neighborLabels().sort()).toEqual(["Drei", "Eins"]);

    // Neue Nachbar-Daten (gleiche Zeiten, neuer Text) — vor dem Fix wurde nur
    // setOptions(start/end) gerufen, das Label blieb auf dem alten Text.
    update({
      timingWord: WORD,
      timingWordText: "Hallo",
      timingNeighbors: {
        prev: { ...NB.prev!, text: "Eins!" },
        next: { ...NB.next!, text: "Drei!" },
      },
    });

    expect(neighborLabels().sort()).toEqual(["Drei!", "Eins!"]);
  });

  it("andere Nachbarwörter bei WIEDERVERWENDETEN Flächen (Wortwechsel)", () => {
    // Produktionsfall: Vorheriges Wort ist aktiv, die Nachbarflächen existieren
    // bereits. Beim Wechsel werden sie nur verschoben — das Label muss den
    // NEUEN Nachbarn zeigen, nicht den alten.
    const { update } = setup({ timingWord: WORD, timingWordText: "Hallo", timingNeighbors: NB });
    expect(neighborLabels().sort()).toEqual(["Drei", "Eins"]);

    update({ timingWord: WORD2, timingWordText: "Mitte", timingNeighbors: NB2 });

    expect(activeLabel()?.textContent).toBe("Mitte");
    expect(neighborLabels().sort()).toEqual(["Vier", "Zwei"]);
  });

  it("Nachbarn kommen NACH dem Wort nach (kein Wortwechsel)", () => {
    const { update } = setup({ timingWord: WORD, timingWordText: "Hallo", timingNeighbors: null });
    expect(neighborLabels()).toEqual([]);

    update({ timingWord: WORD, timingWordText: "Hallo", timingNeighbors: NB });

    expect(neighborLabels().sort()).toEqual(["Drei", "Eins"]);
  });

  it("kein aktives Wort → keine Beschriftung bleibt stehen", () => {
    const { update } = setup({ timingWord: WORD, timingWordText: "Hallo", timingNeighbors: NB });
    expect(allLabels().length).toBe(3);

    update({ timingWord: null, timingWordText: "", timingNeighbors: null });

    // Ausdrücklich entfernt — keine Reste des vorherigen Wortes.
    expect(document.querySelector(".ps-timing-word-active")).toBeNull();
    expect(neighborLabels()).toEqual([]);
    expect(allLabels()).toEqual([]);
  });

  it("Nachbar wird null → nur seine Beschriftung verschwindet, die andere bleibt", () => {
    const { update } = setup({ timingWord: WORD, timingWordText: "Hallo", timingNeighbors: NB });

    update({
      timingWord: WORD,
      timingWordText: "Hallo",
      timingNeighbors: { prev: NB.prev, next: null },
    });

    expect(neighborLabels()).toEqual(["Eins"]);
    expect(activeLabel()?.textContent).toBe("Hallo");
  });
});
