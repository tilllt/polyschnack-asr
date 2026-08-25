/**
 * Change 054 — Sort-Badge-Zyklus + Tag-Aggregation (pure Logik).
 */
import { describe, expect, it } from "vitest";

import { aggregateTags, mergeChipTags, nextSortState, sortParams } from "./sortState";

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

describe("mergeChipTags (Change 122: aktive Tags bleiben abwählbar)", () => {
  it("aktive Tags ohne Treffer werden als Chips (count 0) ergänzt", () => {
    // 0-Treffer-Fall: tagList ist leer, aber der User hat einen Filter aktiv
    expect(mergeChipTags([], ["arbeit"])).toEqual([{ tag: "arbeit", count: 0 }]);
  });

  it("aktive Tags mit Treffern bleiben unverändert (keine Duplikate)", () => {
    const tagList = [
      { tag: "arbeit", count: 4 },
      { tag: "interview", count: 1 },
    ];
    expect(mergeChipTags(tagList, ["arbeit"])).toEqual(tagList);
  });

  it("mehrere aktive Tags ohne Treffer → alle sichtbar", () => {
    expect(mergeChipTags([], ["a", "b"])).toEqual([
      { tag: "a", count: 0 },
      { tag: "b", count: 0 },
    ]);
  });

  it("Mischung: Treffer-Tags + aktive ohne Treffer", () => {
    const tagList = [{ tag: "arbeit", count: 4 }];
    expect(mergeChipTags(tagList, ["arbeit", "gibtsnicht"])).toEqual([
      { tag: "arbeit", count: 4 },
      { tag: "gibtsnicht", count: 0 },
    ]);
  });
});
