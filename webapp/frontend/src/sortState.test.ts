/**
 * Change 054 — Sort-Badge-Zyklus + Tag-Aggregation (pure Logik).
 */
import { describe, expect, it } from "vitest";

import { aggregateTags, nextSortState, sortParams } from "./sortState";

describe("nextSortState (Badge-Klick-Zyklus)", () => {
  it("1. Klick auf inaktives Badge → absteigend", () => {
    expect(nextSortState(null, "name")).toEqual({ key: "name", dir: "desc" });
    // Anderes Badge aktiv → neues Kriterium, wieder desc
    expect(nextSortState({ key: "date", dir: "desc" }, "length")).toEqual({
      key: "length",
      dir: "desc",
    });
  });

  it("2. Klick auf dasselbe Badge → aufsteigend", () => {
    expect(nextSortState({ key: "name", dir: "desc" }, "name")).toEqual({
      key: "name",
      dir: "asc",
    });
  });

  it("3. Klick auf dasselbe Badge → Default (null)", () => {
    expect(nextSortState({ key: "name", dir: "asc" }, "name")).toBeNull();
  });

  it("alle Kriterien unterstützt", () => {
    for (const key of ["date", "edited", "name", "filename", "length"] as const) {
      expect(nextSortState(null, key)).toEqual({ key, dir: "desc" });
    }
  });
});

describe("sortParams", () => {
  it("null → keine Parameter", () => {
    expect(sortParams(null)).toEqual({ sort: null });
  });
  it("aktiv → sort+dir", () => {
    expect(sortParams({ key: "edited", dir: "asc" })).toEqual({
      sort: "edited",
      dir: "asc",
    });
  });
});

describe("aggregateTags", () => {
  it("zählt und sortiert alphabetisch, nur existierende Tags", () => {
    const recs = [
      { tags: ["walzen", "review"] },
      { tags: ["walzen"] },
      { tags: [] },
      { tags: undefined },
    ];
    expect(aggregateTags(recs)).toEqual([
      { tag: "review", count: 1 },
      { tag: "walzen", count: 2 },
    ]);
  });

  it("leere Liste → keine Tags", () => {
    expect(aggregateTags([])).toEqual([]);
  });
});
