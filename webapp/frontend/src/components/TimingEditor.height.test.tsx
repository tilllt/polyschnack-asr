/** Change 210 (User-Befund 19.09.2026): Im Timing-Tab waren nur die ersten
 *  Zeilen der Wortliste erreichbar (260px-Kasten) — jetzt ist die Liste hoch,
 *  und die Farblegende erklärt aktives Wort vs. Nachbar-Marker. */
import { render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

// SegmentList (echt gerendert) zieht Yjs-Hook, API und Toasts — wie in den
// übrigen SegmentList-Tests nachbilden, sonst läuft der Render in echte
// Aufrufe.
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
  return { ...actual, updateSegment: vi.fn(), renameSpeaker: vi.fn() };
});
vi.mock("./Toasts", () => ({ useToast: () => ({ toast: vi.fn() }) }));

import type { Segment } from "../api";
import { LocaleProvider } from "../useLocale";
import { TimingEditor } from "./TimingEditor";

const SEGS = [
  {
    start: 0,
    end: 2,
    text: "Hallo Welt",
    words: [
      { word: "Hallo", start: 0, end: 1 },
      { word: "Welt", start: 1, end: 2 },
    ],
  },
] as unknown as Segment[];

const props = {
  segments: SEGS,
  activeIdx: 0,
  onActiveChange: () => {},
  onWordClick: vi.fn(),
  timing: { segIdx: 0, wordIdx: 0, start: 0, end: 1 },
};

describe("TimingEditor — Höhe der Wortliste und Legende (Change 210)", () => {
  test("Wortliste nutzt die hohe Variante statt max-h-[260px]", () => {
    const { container } = render(
      <LocaleProvider>
        <TimingEditor {...props} />
      </LocaleProvider>,
    );
    const box = container.querySelector(".overflow-y-auto") as HTMLElement;
    expect(box).toBeTruthy();
    expect(box.className).toContain("max-h-[62vh]");
    expect(box.className).not.toContain("max-h-[260px]");
  });

  test("Farblegende zeigt aktives Wort und Nachbar", () => {
    const { container } = render(
      <LocaleProvider>
        <TimingEditor {...props} />
      </LocaleProvider>,
    );
    const legend = container.querySelector('[data-testid="timing-legend"]') as HTMLElement;
    expect(legend).toBeTruthy();
    // Zwei Farbfelder: kräftiges Grün (aktiv) und Bernstein (Nachbar).
    const felder = Array.from(legend.querySelectorAll("span")).map(
      (s) => (s as HTMLElement).style.background,
    );
    expect(felder.some((f) => f.includes("46, 160, 67") || f.includes("46,160,67"))).toBe(true);
    expect(felder.some((f) => f.includes("210, 153, 34") || f.includes("210,153,34"))).toBe(true);
    expect(screen.getByText("Hallo")).toBeTruthy(); // Kopfzeile zeigt das Wort
  });

  test("Vollbild: Liste füllt die Höhe (fillHeight statt 62vh)", () => {
    const { container } = render(
      <LocaleProvider>
        <TimingEditor {...props} listFillHeight />
      </LocaleProvider>,
    );
    const box = container.querySelector(".overflow-y-auto") as HTMLElement;
    expect(box.className).toContain("h-full");
  });
});
