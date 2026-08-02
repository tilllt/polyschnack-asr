import { describe, expect, it } from "vitest";
import { diarSensToMinDurationOff } from "./components/FeatureToggles";

describe("diarSensToMinDurationOff", () => {
  it("less → 0.4 s (weniger Sprecherwechsel)", () => {
    expect(diarSensToMinDurationOff("less")).toBe(0.4);
  });

  it("more → 0.05 s (mehr Detail)", () => {
    expect(diarSensToMinDurationOff("more")).toBe(0.05);
  });

  it("std → undefined (Pipeline-Default)", () => {
    expect(diarSensToMinDurationOff("std")).toBeUndefined();
  });
});
