import { describe, expect, it } from "vitest";
import { buildDiffModel, wordDiff } from "./versionDiff";

describe("wordDiff", () => {
  it("erkennt unveränderte Zeilen als gleich", () => {
    expect(wordDiff("Hallo Welt", "Hallo Welt")).toEqual([
      { text: "Hallo Welt", type: "same" },
    ]);
  });

  it("markiert geänderte Wörter inline", () => {
    const d = wordDiff("Hallo Du Welt", "Hallo Du schöne Welt");
    expect(d.some((w) => w.type === "add" && w.text.includes("schöne"))).toBe(true);
    expect(d.filter((w) => w.type === "same").length).toBeGreaterThan(0);
  });

  it("leere Zeilen ergeben leeren Diff", () => {
    expect(wordDiff("", "")).toEqual([]);
  });

  it("vollständig neue Zeile ist alles add", () => {
    const d = wordDiff("", "neu");
    expect(d.every((w) => w.type === "add")).toBe(true);
  });
});

describe("buildDiffModel", () => {
  it("identische Texte → identical, keine Hunks mit Änderung", () => {
    const m = buildDiffModel([
      { type: "same", text: "A" },
      { type: "same", text: "B" },
    ]);
    expect(m.identical).toBe(true);
    expect(m.stats).toEqual({ add: 0, del: 0 });
  });

  it("zählt Statistik und vergibt Zeilennummern", () => {
    const m = buildDiffModel([
      { type: "same", text: "A" },
      { type: "del", text: "B" },
      { type: "add", text: "C" },
      { type: "same", text: "D" },
    ]);
    expect(m.stats).toEqual({ add: 1, del: 1 });
    const rows = m.hunks.flatMap((h) => h.rows);
    const delRow = rows.find((r) => r.type === "del");
    expect(delRow?.aLine).toBe(2);
    const addRow = rows.find((r) => r.type === "add");
    expect(addRow?.bLine).toBe(2);
  });

  it("paart gleichlange del/add-Blöcke mit Inline-Wort-Diff", () => {
    const m = buildDiffModel([
      { type: "same", text: "A" },
      { type: "del", text: "Hallo Du Welt" },
      { type: "add", text: "Hallo Du Weltall" },
      { type: "same", text: "B" },
    ]);
    const rows = m.hunks.flatMap((h) => h.rows);
    const delRow = rows.find((r) => r.type === "del");
    expect(delRow?.words).toBeDefined();
    // „Welt" wurde zu „Weltall": del-Wort + add-Wort inline markiert
    expect(delRow?.words?.some((w) => w.type === "del" && w.text.includes("Welt"))).toBe(true);
    const addRow = rows.find((r) => r.type === "add");
    expect(addRow?.words?.some((w) => w.type === "add" && w.text.includes("Weltall"))).toBe(true);
  });

  it("klappt lange unveränderte Strecken ein", () => {
    const same = Array.from({ length: 20 }, (_, i) => ({ type: "same" as const, text: `Z${i}` }));
    const m = buildDiffModel([
      { type: "same", text: "A" },
      ...same,
      { type: "add", text: "X" },
      { type: "same", text: "B" },
    ]);
    const allRows = m.hunks.flatMap((h) => h.rows);
    expect(allRows.some((r) => r.skipped !== undefined)).toBe(true);
    // Nicht alle 20 Kontextzeilen tauchen auf
    expect(allRows.filter((r) => r.text.startsWith("Z")).length).toBeLessThan(20);
  });
});
