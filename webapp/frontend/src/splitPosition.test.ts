import { describe, it, expect } from "vitest";
import { computeSplitPopover } from "./splitPosition";

const BTN = { left: 300, top: 200, width: 26, height: 26 };

describe("computeSplitPopover (Change 058)", () => {
  it("positioniert rechts neben dem Button, wenn Platz ist", () => {
    const pos = computeSplitPopover(BTN, 260, 200, 1200, 800);
    expect(pos.left).toBe(300 + 26 + 8); // 334
    expect(pos.top).toBe(200);
  });

  it("flippt nach links, wenn rechts kein Platz ist (schmaler Viewport)", () => {
    // Button bei x=500, Viewport nur 560 breit → rechts gäbe es nur 60px
    const btn = { left: 500, top: 100, width: 26, height: 26 };
    const pos = computeSplitPopover(btn, 260, 200, 560, 800);
    expect(pos.left).toBe(500 - 260 - 8); // 232
    expect(pos.top).toBe(100);
  });

  it("klemmt links auf Mindestabstand, wenn der Viewport enger ist als das Popover", () => {
    const btn = { left: 4, top: 100, width: 26, height: 26 };
    const pos = computeSplitPopover(btn, 260, 200, 200, 800);
    expect(pos.left).toBe(8); // nicht negativ
  });

  it("klemmt unten, damit das Popover nie unter den Viewport ragt", () => {
    const btn = { left: 300, top: 760, width: 26, height: 26 };
    const pos = computeSplitPopover(btn, 260, 200, 1200, 800);
    expect(pos.top).toBe(800 - 200 - 8); // 592
  });

  it("klemmt top auf Mindestabstand bei Button ganz oben", () => {
    const btn = { left: 300, top: 2, width: 26, height: 26 };
    const pos = computeSplitPopover(btn, 260, 200, 1200, 800);
    expect(pos.top).toBe(8);
  });
});
