import { describe, expect, test } from "vitest";
import { parseBenchmarkPath } from "./benchmark";

describe("parseBenchmarkPath", () => {
  test("erkennt /benchmark", () => {
    expect(parseBenchmarkPath("/benchmark")).toBe(true);
  });
  test("erkennt /benchmark/ mit trailing slash", () => {
    expect(parseBenchmarkPath("/benchmark/")).toBe(true);
  });
  test("erkennt /benchmark/xyz", () => {
    expect(parseBenchmarkPath("/benchmark/xyz")).toBe(true);
  });
  test("erkennt /benchmark?lang=de", () => {
    expect(parseBenchmarkPath("/benchmark?lang=de")).toBe(true);
  });
  test("lehnt / ab", () => {
    expect(parseBenchmarkPath("/")).toBe(false);
  });
  test("lehnt /settings ab", () => {
    expect(parseBenchmarkPath("/settings")).toBe(false);
  });
  test("lehnt /benchmarking ab (kein Präfix-Fehlmatch)", () => {
    expect(parseBenchmarkPath("/benchmarking")).toBe(false);
  });
});
